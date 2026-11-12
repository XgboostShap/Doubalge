"""Plans nombreux : requêtes bornées, références conservées et reprises."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from fixtures import FakeClient,StubServer,make_pdf
from llm import Cancelled,InvalidResponseError,ModelError,Ollama,ResponseLimitError
from pipeline import Pipeline
from storage import defaults,read,write


def planning_data(count=181,groups_count=176):
    ideas=[{'id':f'PDF1-P2-I{n:03}','statement':f'Le phénomène {n} dépend des conditions expérimentales.',
        'explanation':'Les conditions doivent être précisées pour interpréter les résultats.',
        'document':'PDF1','pages':[n]} for n in range(1,count+1)]
    groups=[{'id':f'G{n+1}','title':('Thème '+str(n)+' — '+('notion scientifique '*10))[:160],
        'text':('Le texte complet est conservé dans le registre. '*200),
        'idea_ids':[i['id'] for i in ideas[n::groups_count]]} for n in range(min(groups_count,count))]
    return {'ideas':ideas,'groups':groups,'documents':[{'id':'PDF1','name':'Essai.pdf'}]}


class PlanContextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)
        write(self.project/'projet.json',{'settings':{**defaults(),'num_ctx':8192},'pdfs':[]})
    def tearDown(self):self.temp.cleanup()
    def prepare(self,data):write(self.project/'etapes/04.json',{'data':data})
    def check_coverage(self,value,data):
        seen=[i for c in value['chapters'] for i in c['idea_ids']]+[e['idea_id'] for e in value['exclusions']]
        self.assertEqual(set(seen),{i['id'] for i in data['ideas']});self.assertEqual(len(seen),len(data['ideas']))
        self.assertLessEqual(len(value['chapters']),20)
        self.assertTrue(all(1<=len(c['idea_ids'])<=24 for c in value['chapters']))

    def test_176_groups_and_181_ideas_fit_8192_context_without_modifying_stage4(self):
        data=planning_data();self.prepare(data);before=(self.project/'etapes/04.json').read_bytes()
        stub=StubServer()
        try:
            client=Ollama({**defaults(),'num_ctx':8192,'endpoint':stub.endpoint},self.project/'cache')
            Pipeline(self.project,client).run(5,5)
            result=read(self.project/'etapes/05.json')['data'];self.check_coverage(result,data)
            self.assertFalse(result['exclusions']);self.assertEqual(sum(c['target_words'] for c in result['chapters']),2900)
            self.assertEqual((self.project/'etapes/04.json').read_bytes(),before)
            self.assertTrue(stub.requests)
            for request in stub.requests:
                prompt=request['messages'][1]['content'];budget=request['options']['num_predict']
                self.assertLessEqual(len(prompt),max(2000,(8192-budget-1200)*3))
                self.assertNotIn('PDF1-P2-I',prompt)
                self.assertNotIn(data['groups'][0]['text'],prompt)
            assignments=[p for task,p in stub.calls if task=='plan_assignments']
            self.assertEqual(sum(len(p['groups']) for p in assignments),176)
            self.assertTrue(all(len(p['groups'])<=6 for p in assignments))
        finally:stub.close()

    def test_invalid_assignments_and_order_do_not_lose_source_ideas(self):
        data=planning_data(30,30);self.prepare(data)
        class Invalid(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='plan_assignments':
                    value={'assignments':{'I1':{'chapter':'C999','title':'Fantôme'},'I999':{'chapter':'C1','title':''}}}
                elif task=='plan_question':value={'central_question':'Comment relier ces notions ?','order':['C999','C1','C1']}
                else:return super().ask(task,payload,instructions,validate,budget)
                validate(value);return value
        Pipeline(self.project,Invalid()).run(5,5)
        result=read(self.project/'etapes/05.json')['data'];self.check_coverage(result,data)
        self.assertTrue(result['warnings']);self.assertFalse(result['exclusions'])

    def test_long_metadata_is_abbreviated_explicitly_without_cutting_audience_or_sources(self):
        data=planning_data(30,30)
        for g in data['groups']:g['title']+=' — '+('précision '*600)
        self.prepare(data);before=(self.project/'etapes/04.json').read_bytes()
        meta=read(self.project/'projet.json');meta['settings']['audience']='Public : '+('consigne '*248)
        write(self.project/'projet.json',meta);stub=StubServer()
        try:
            config={**meta['settings'],'endpoint':stub.endpoint}
            client=Ollama(config,self.project/'cache');Pipeline(self.project,client).run(5,5)
            self.assertEqual((self.project/'etapes/04.json').read_bytes(),before)
            for task,payload in stub.calls:
                self.assertEqual(payload['audience'],meta['settings']['audience'])
                for g in payload.get('groups',[]):
                    self.assertTrue(g['title_is_excerpt']);self.assertTrue(g['overview_is_excerpt'])
            self.check_coverage(read(self.project/'etapes/05.json')['data'],data)
        finally:stub.close()

    def test_invalid_or_truncated_generation_produces_an_explicit_provisional_plan(self):
        for error in (InvalidResponseError,ResponseLimitError):
            class Failed(FakeClient):
                def ask(self,*args,**kwargs):raise error('Réponse non concluante')
            folder=self.project/error.__name__;folder.mkdir()
            write(folder/'projet.json',{'settings':defaults(),'pdfs':[]})
            data=planning_data(4,4);write(folder/'etapes/04.json',{'data':data})
            Pipeline(folder,Failed()).run(5,5)
            result=read(folder/'etapes/05.json')['data'];self.check_coverage(result,data)
            self.assertTrue(result['warnings']);self.assertIn('Plan à relire',(folder/'etapes/05.md').read_text())

    def test_completed_assignment_batches_are_reused_after_a_network_failure(self):
        data=planning_data(18,18);self.prepare(data)
        class Interrupted(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if task=='plan_assignments':
                    self.seen+=1
                    if self.seen==2:raise ModelError('HTTP 500')
                return super().ask(task,payload,*args,**kwargs)
        client=Interrupted();client.seen=0
        with self.assertRaisesRegex(ModelError,'Étape 5/9.*500'):Pipeline(self.project,client).run(5,5)
        path=self.project/'etapes/parties/05-Placement1.md';before=path.read_bytes()
        self.assertFalse((self.project/'etapes/05.json').exists())
        client=FakeClient();Pipeline(self.project,client).run(5,5)
        calls=[p for task,p in client.calls if task=='plan_assignments']
        self.assertEqual(len(calls),2);self.assertTrue(calls[0]['groups'][0]['title'].startswith('Thème 6'))
        self.assertEqual(path.read_bytes(),before)

    def test_completed_chapter_survives_a_later_chapter_failure(self):
        data=planning_data(12,12);self.prepare(data)
        class Interrupted(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if task=='plan_chapter':
                    self.seen+=1
                    if self.seen==2:raise ModelError('HTTP 404')
                return super().ask(task,payload,*args,**kwargs)
        client=Interrupted();client.seen=0
        with self.assertRaisesRegex(ModelError,'404'):Pipeline(self.project,client).run(5,5)
        path=self.project/'etapes/parties/05-Chapitre1.md';before=path.read_bytes()
        client=FakeClient();Pipeline(self.project,client).run(5,5)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(len([p for t,p in client.calls if t=='plan_chapter']),11)

    def test_source_group_larger_than_one_chapter_is_split_with_exact_coverage(self):
        data=planning_data(60,1);self.prepare(data);Pipeline(self.project,FakeClient()).run(5,5)
        result=read(self.project/'etapes/05.json')['data'];self.check_coverage(result,data)
        self.assertFalse(result['exclusions'])

    def test_capacity_exclusions_are_explicit_and_all_sources_remain_in_the_dossier(self):
        data=planning_data(500,500);self.prepare(data)
        Pipeline(self.project,FakeClient()).run(5,5)
        result=read(self.project/'etapes/05.json')['data'];self.check_coverage(result,data)
        self.assertTrue(result['exclusions']);self.assertTrue(result['warnings'])
        self.assertTrue(all('Capacité du plan' in e['reason'] for e in result['exclusions']))
        self.assertEqual(len(read(self.project/'etapes/04.json')['data']['ideas']),500)

    def test_wrong_source_coverage_stops_before_any_model_request(self):
        data=planning_data(3,3);data['groups'][1]['idea_ids']=data['groups'][0]['idea_ids'][:]
        self.prepare(data);client=FakeClient()
        with self.assertRaisesRegex(ValueError,'identifiants'):Pipeline(self.project,client).run(5,5)
        self.assertFalse(client.calls)

    def test_model_connectivity_and_cancellation_are_never_turned_into_a_fallback_plan(self):
        data=planning_data(3,3);self.prepare(data)
        for error in (ModelError,Cancelled,OSError):
            class Failed(FakeClient):
                def ask(self,*args,**kwargs):raise error('Arrêt')
            with self.subTest(error=error),self.assertRaises(error):Pipeline(self.project,Failed()).run(5,5)
        self.assertFalse((self.project/'etapes/05.json').exists())

    def test_plan_warnings_reach_the_final_report(self):
        (self.project/'sources').mkdir();make_pdf(self.project/'sources/a.pdf')
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[{'file':'a.pdf','name':'Essai.pdf'}]})
        class Missing(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='plan_question':
                    value={'central_question':'Comment relier ces notions ?','order':[]};validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        Pipeline(self.project,Missing()).run(1,9)
        final=read(self.project/'exports/podcast.json')
        self.assertTrue(final['all_planned_ids_present'])
        self.assertTrue(any('Chapitres absents' in w for w in final['generation_warnings']))


if __name__=='__main__':unittest.main()
