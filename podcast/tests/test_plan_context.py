"""Sélection selon la durée, partitions du registre et contexte borné."""
from pathlib import Path
import tempfile
import unittest
import editorial
from fixtures import FakeClient,StubServer
from llm import Ollama,ModelError,InvalidResponseError
from pipeline import Pipeline
from storage import defaults,read,write

def planning_data(count=181,groups_count=176):
    ideas=[]
    for n in range(1,count+1):
        role=editorial.ROLES[(n-1)%6]
        idea={'id':f'PDF1-P2-I{n:03}','statement':f'Le phénomène {n} dépend des conditions expérimentales.',
              'explanation':'Les conditions doivent être précisées pour interpréter le résultat sans généralisation.',
              'document':'PDF1','pages':[n],'role':role,'importance':'essential','evidence':[]}
        idea['source_hash']=editorial.source_hash(idea);ideas.append(idea)
    return {'workflow_version':editorial.VERSION,'ideas':ideas,'groups':[
        {'id':f'G{n+1}','title':'Thème '+str(n),'text':'Texte intégral conservé. '*500,
         'idea_ids':[i['id'] for i in ideas[n::groups_count]]} for n in range(min(groups_count,count))],
        'documents':[{'id':'PDF1','name':'Essai.pdf','glossary':{}}]}

class PlanContextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)
        write(self.project/'projet.json',{'settings':{**defaults(),'num_ctx':8192},'pdfs':[]})
    def tearDown(self):self.temp.cleanup()
    def prepare(self,data):write(self.project/'etapes/04.json',{'data':data})
    def check_coverage(self,plan,data):
        seen=[i for c in plan['chapters'] for i in c['idea_ids']]+[e['idea_id'] for e in plan['exclusions']]
        self.assertEqual(set(seen),{i['id'] for i in data['ideas']});self.assertEqual(len(seen),len(data['ideas']))
        self.assertTrue(all(len(c['idea_ids'])<=5 for c in plan['chapters']))
        self.assertEqual(sum(c['target_words'] for c in plan['chapters']),plan['target_words'])
    def test_176_themes_never_become_one_large_planning_request(self):
        data=planning_data();self.prepare(data);before=(self.project/'etapes/04.json').read_bytes()
        stub=StubServer()
        try:
            client=Ollama({**defaults(),'num_ctx':8192,'endpoint':stub.endpoint},self.project/'cache')
            Pipeline(self.project,client).run(5,5)
            plan=read(self.project/'etapes/05.json')['data'];self.check_coverage(plan,data)
            self.assertLess(plan['selected_count'],181);self.assertTrue(plan['exclusions'])
            self.assertEqual((self.project/'etapes/04.json').read_bytes(),before)
            self.assertEqual(len(stub.requests),1)
            request=stub.requests[0];prompt=request['messages'][1]['content']
            self.assertNotIn(data['groups'][0]['text'],prompt)
            self.assertLess(len(prompt),(8192-request['options']['num_predict']-1200)*3)
        finally:stub.close()
    def test_selection_expands_with_duration_and_never_hides_exclusions(self):
        data=planning_data(100,100);counts=[]
        for minutes in (3,20,60):
            selected,excluded,_,_=editorial.selection(data,minutes);counts.append(len(selected))
            self.assertEqual({i['id'] for i in selected}|{i['idea_id'] for i in excluded},{i['id'] for i in data['ideas']})
        self.assertLess(counts[0],counts[1]);self.assertLess(counts[1],counts[2])
    def test_duplicate_and_unknown_source_ids_are_rejected(self):
        data=planning_data(3,3);data['ideas'][1]['id']=data['ideas'][0]['id'];self.prepare(data)
        with self.assertRaisesRegex(ValueError,'doublon'):Pipeline(self.project,FakeClient()).run(5,5)
    def test_exact_duplicate_excluded_but_changed_units_preserved(self):
        data=planning_data(3,3);data['ideas'][1].update(statement=data['ideas'][0]['statement'],explanation=data['ideas'][0]['explanation'])
        selected,excluded,_,_=editorial.selection(data,20)
        self.assertEqual(len(selected),2);self.assertIn('Redite exacte',excluded[0]['reason'])
        data['ideas'][1]['statement']='Une puissance de 1 mW est utilisée.'
        data['ideas'][0]['statement']='Une puissance de 1 MW est utilisée.'
        selected,excluded,_,_=editorial.selection(data,20);self.assertEqual(len(selected),3)
    def test_duplicate_generated_titles_are_replaced_by_distinct_roles(self):
        class Same(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='editorial_outline':
                    value={'central_question':'Comment comprendre ces notions ?','titles':{r:'Les notions pour comprendre' for r in payload['roles']}}
                    validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        self.prepare(planning_data(6,6));Pipeline(self.project,Same()).run(5,5)
        plan=read(self.project/'etapes/05.json')['data']
        self.assertEqual(len({c['title'] for c in plan['chapters']}),6);self.assertTrue(plan['warnings'])
        self.assertEqual([c['role'] for c in plan['chapters']],list(editorial.ROLES))
    def test_failed_outline_generation_is_explicit_but_network_errors_stop(self):
        self.prepare(planning_data(6,6))
        class Failed(FakeClient):
            def ask(self,*args,**kwargs):raise InvalidResponseError('Format invalide')
        Pipeline(self.project,Failed()).run(5,5)
        self.assertTrue(read(self.project/'etapes/05.json')['data']['warnings'])
        class Offline(FakeClient):
            def ask(self,*args,**kwargs):raise ModelError('HTTP 404')
        meta=read(self.project/'projet.json');meta['settings']['minutes']=21;write(self.project/'projet.json',meta)
        with self.assertRaisesRegex(ModelError,'404'):Pipeline(self.project,Offline()).run(5,5)
    def test_completed_outline_is_reused_without_reclassifying_sources(self):
        self.prepare(planning_data(6,6));client=FakeClient();pipe=Pipeline(self.project,client)
        pipe.run(5,5);count=len(client.calls);pipe.run(5,5);self.assertEqual(len(client.calls),count)
    def test_old_workflow_cannot_be_silently_reused(self):
        data=planning_data(6,6);data.pop('workflow_version');self.prepare(data)
        with self.assertRaisesRegex(ValueError,'Ancien texte commun'):Pipeline(self.project,FakeClient()).run(5,5)
    def test_document_identifiers_cannot_become_podcast_titles(self):
        class Meta(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='editorial_outline':
                    value={'central_question':'Comment utiliser PDF1 pour présenter le document ?',
                           'titles':{r:'Utilisation de PDF1 pour présenter le document' for r in payload['roles']}}
                    validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        self.prepare(planning_data(6,6));Pipeline(self.project,Meta()).run(5,5)
        plan=read(self.project/'etapes/05.json')['data']
        self.assertNotIn('PDF1',plan['central_question'])
        self.assertTrue(all('PDF1' not in c['title'] for c in plan['chapters']))
        self.assertTrue(plan['warnings'])
    def test_an_outline_cannot_invent_a_causal_premise_or_declarative_title(self):
        class Relation(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='editorial_outline':
                    value={'central_question':'Quel algorithme de quantification amplifie le signal ?',
                           'titles':{r:'Quantification introduit une amplification nécessaire' for r in payload['roles']}}
                    validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        self.prepare(planning_data(6,6));Pipeline(self.project,Relation()).run(5,5)
        plan=read(self.project/'etapes/05.json')['data']
        self.assertNotIn('amplifie',plan['central_question'])
        self.assertTrue(all('Quantification' not in c['title'] for c in plan['chapters']))

if __name__=='__main__':unittest.main()
