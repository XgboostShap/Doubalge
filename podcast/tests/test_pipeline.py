import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from app import App,Server,settings
from llm import Ollama,Cancelled,ModelError,endpoint_parts,models
from pdfs import extract,split_three
from pipeline import Pipeline,ids_exact,dialogue_valid,page_fragments
from storage import defaults,invalidate,read,write
from fixtures import FakeClient,StubServer,make_pdf


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.project=self.root/'projet';(self.project/'sources').mkdir(parents=True)
        a=make_pdf(self.project/'sources/a.pdf');b=make_pdf(self.project/'sources/b.pdf','Laser')
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[{'file':a.name,'name':'optique.pdf'},{'file':b.name,'name':'laser.pdf'}]})
    def tearDown(self):self.temp.cleanup()

    def test_three_parts_preserve_every_block_and_original_pages(self):
        blocks=[{'page':n,'text':'mot '*n} for n in range(1,20)]
        result=split_three(blocks)
        self.assertEqual(len(result),3);self.assertTrue(all(result));self.assertEqual([b for part in result for b in part],blocks)
        data=extract(self.project/'sources/a.pdf','PDF1','optique.pdf')
        self.assertEqual(data['page_count'],3);self.assertEqual([p['pages'] for p in data['parts']],[[1],[2],[3]])

    def test_nine_stages_sources_memory_and_exports(self):
        client=FakeClient();Pipeline(self.project,client).run()
        self.assertEqual(len(list((self.project/'etapes').glob('*.json'))),9)
        final=read(self.project/'exports/podcast.json');self.assertTrue(final['all_planned_ids_present']);self.assertTrue(final['word_count']>0)
        self.assertTrue((self.project/'exports/podcast.txt').exists())
        summaries=read(self.project/'etapes/02.json')['data']
        self.assertEqual(len(summaries['documents']),2)
        self.assertTrue(all(len(doc['parts'])==3 for doc in summaries['documents']))
        calls=[p for task,p in client.calls if task=='dialogue']
        self.assertEqual(len(calls),2)
        self.assertFalse(calls[0]['memory']['explained_ideas'])
        self.assertTrue(calls[1]['memory']['explained_ideas']);self.assertIn('C1',calls[1]['memory']['definitions'])
        self.assertTrue(calls[1]['memory']['last_turns']);self.assertEqual(len(list((self.project/'memoire').glob('*.json'))),2)
        old=(self.project/'etapes/04.json').read_bytes();invalidate(self.project,5)
        self.assertEqual((self.project/'etapes/04.json').read_bytes(),old)
        self.assertFalse((self.project/'etapes/05.json').exists());self.assertFalse((self.project/'exports/podcast.txt').exists())
        self.assertTrue(list((self.project/'versions').rglob('export-podcast.txt')))

    def test_unknown_duplicate_and_missing_idea_ids_are_rejected(self):
        for actual in [['a','a'],['a'],['a','c']]:
            with self.assertRaises(ValueError):ids_exact(actual,['a','b'])
        with self.assertRaises(ValueError):dialogue_valid({'opening_transition':'suite','turns':[{'speaker':'Autre','text':'texte','idea_ids':['a']}]},['Sophie','Emma'],['a'])

    def test_failed_stage_is_not_marked_complete_and_previous_steps_survive(self):
        client=FakeClient();pipeline=Pipeline(self.project,client);pipeline.run(1,4)
        class BadPlan(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='plan':validate({'central_question':'question','chapters':[],'exclusions':[]})
                return super().ask(task,payload,instructions,validate,budget)
        with self.assertRaises(ValueError):Pipeline(self.project,BadPlan()).run(5,9)
        self.assertTrue((self.project/'etapes/04.json').exists());self.assertFalse((self.project/'etapes/05.json').exists())

    def test_source_without_extractible_text_is_rejected(self):
        from pypdf import PdfWriter
        writer=PdfWriter();writer.add_blank_page(width=612,height=792)
        path=self.root/'scan.pdf';writer.write(path)
        with self.assertRaisesRegex(ValueError,'OCR'):extract(path,'PDF1','scan.pdf')

    def test_page_fragments_never_mix_pages_or_drop_blocks(self):
        blocks=[{'page':page,'text':'mot '*30} for page in (1,1,2,2,3,3)]
        chunks=list(page_fragments(blocks))
        self.assertEqual([page for page,_ in chunks],[1,2,3])
        self.assertEqual([b for _,chunk in chunks for b in chunk],blocks)
        self.assertTrue(all({b['page'] for b in chunk}=={page} for page,chunk in chunks))
        with self.assertRaises(ValueError):list(page_fragments([{'page':'1','text':'texte'}]))

    def test_source_pages_come_from_pdf_when_model_omits_or_invents_them(self):
        make_pdf(self.project/'sources/a.pdf',page_count=6)
        meta=read(self.project/'projet.json');meta['pdfs']=meta['pdfs'][:1];write(self.project/'projet.json',meta)
        for supplied in (None,{'pages':['p. 999',0]}, {'pages':'page inventée'}):
            class UnreliablePageModel(FakeClient):
                def ask(inner,task,payload,instructions,validate,budget=4000):
                    if task!='part_summary':return super().ask(task,payload,instructions,validate,budget)
                    inner.calls.append((task,copy.deepcopy(payload)))
                    value={'summary':'Un résumé lié au texte fourni.','ideas':[{'statement':'Une idée extraite.',
                           'explanation':'Son explication dans la page.' ,**(supplied or {})}]}
                    validate(value);return value
            client=UnreliablePageModel();Pipeline(self.project,client).run(1,2)
            result=read(self.project/'etapes/02.json')['data']['documents'][0]
            self.assertEqual(len(result['parts']),3)
            ideas=[i for part in result['parts'] for i in part['ideas']]
            self.assertEqual([i['pages'] for i in ideas],[[1],[2],[3],[4],[5],[6]])
            self.assertTrue(all(i['document']=='PDF1' for i in ideas))
            requests=[p for task,p in client.calls if task=='part_summary']
            self.assertEqual(len(requests),6)
            self.assertTrue(all({b['page'] for b in p['blocks']}=={p['source_page']} for p in requests))
            self.assertTrue(all('boundary_context' not in p for p in requests))

    def test_summary_still_rejects_missing_scientific_content(self):
        Pipeline(self.project,FakeClient()).run(1,1)
        class MissingExplanation(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='part_summary':validate({'summary':'Résumé','ideas':[{'statement':'Idée'}]})
                return super().ask(task,payload,instructions,validate,budget)
        with self.assertRaisesRegex(ValueError,'explanation'):Pipeline(self.project,MissingExplanation()).run(2,2)
        self.assertFalse((self.project/'etapes/02.json').exists())

    def test_cover_page_can_have_no_ideas_and_is_visible_for_review(self):
        class CoverPage(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='part_summary' and payload['source_page']==1:
                    value={'summary':'Page de couverture.','ideas':[]};validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        Pipeline(self.project,CoverPage()).run(1,2)
        doc=read(self.project/'etapes/02.json')['data']['documents'][0]
        self.assertEqual(doc['parts'][0]['ideas'],[])
        self.assertEqual(doc['parts'][0]['excerpts_without_ideas'],[{'page':1,'summary':'Page de couverture.'}])
        self.assertTrue(doc['parts'][1]['ideas'])
        self.assertIn('Extraits sans idée retenue',(self.project/'etapes/02.md').read_text())

    def test_no_ideas_stops_before_inventing_a_global_text(self):
        class EmptyDocument(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='part_summary':
                    value={'summary':'Extrait sans idée explicative.','ideas':[]};validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        client=EmptyDocument();pipeline=Pipeline(self.project,client);pipeline.run(1,3)
        with self.assertRaisesRegex(ValueError,'Aucune idée explicative'):pipeline.run(4,4)
        self.assertFalse(any(task=='global_groups' for task,_ in client.calls))
        self.assertFalse((self.project/'etapes/04.json').exists())


class ClientTests(unittest.TestCase):
    def setUp(self):self.stub=StubServer();self.temp=tempfile.TemporaryDirectory()
    def tearDown(self):self.stub.close();self.temp.cleanup()
    def client(self):return Ollama({**defaults(),'endpoint':self.stub.endpoint},Path(self.temp.name))
    def test_models_real_http_stream_and_validated_cache(self):
        self.assertEqual(models(self.stub.endpoint),['mistral:test'])
        client=self.client();payload={'ideas':[{'id':'PDF1-P1-I001','statement':'Un fait'}]}
        validate=lambda v:self.assertIn('[PDF1-P1-I001]',v['text'])
        a=client.ask('global_text',payload,'texte',validate)
        b=client.ask('global_text',payload,'texte',validate)
        self.assertEqual(a,b);self.assertEqual(len(self.stub.calls),1)

    def test_cancel_interrupts_stream_read(self):
        self.stub.stall=True;client=self.client();errors=[]
        def run():
            try:client.ask('global_text',{'ideas':[]},'texte',lambda v:None)
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=run);thread.start()
        self.assertTrue(self.stub.started.wait(3));client.cancel();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertTrue(any(isinstance(e,Cancelled) for e in errors))

    def test_external_model_endpoint_and_oversized_context_are_refused(self):
        for endpoint in ['http://example.com','http://127.0.0.1@evil.test','http://localhost/path','file:///tmp/test']:
            with self.assertRaises(ValueError):endpoint_parts(endpoint)
        with self.assertRaises(ModelError):self.client().ask('test',{'text':'x'*200000},'test',lambda v:None)
        self.assertFalse(self.stub.calls)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.app=App(self.root,FakeClient)
        self.server=Server(('127.0.0.1',0),self.app);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.app.close();self.thread.join();self.temp.cleanup()
    def request(self,path,body=None,headers=None,raw=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        h={'X-Podcast-Token':self.app.token,'Content-Type':'application/json'};h.update(headers or {})
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        conn.request('POST' if data is not None else 'GET',path,data,h);r=conn.getresponse();payload=r.read();status=r.status;conn.close()
        return status,json.loads(payload) if payload[:1] in (b'{',b'[') else payload
    def create(self):
        status,p=self.request('/api/projects',{'name':'Test','settings':defaults()});self.assertEqual(status,201);return p['id']
    def upload(self,identifier):
        pdf=make_pdf(self.root/'source.pdf')
        return self.request('/api/projects/'+identifier+'/pdf',headers={'X-Filename':'../optique.pdf','Content-Type':'application/pdf'},raw=pdf.read_bytes())

    def test_host_origin_and_csrf_protection(self):
        self.assertEqual(self.request('/api/projects',{'name':'test'},headers={'X-Podcast-Token':'wrong'})[0],403)
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.test'})[0],403)
        self.assertEqual(self.request('/api/projects',{'name':'test'},headers={'Origin':'https://evil.test'})[0],403)
        self.assertEqual(self.request('/api/state')[0],200)

    def test_upload_validation_job_completion_and_settings_invalidation(self):
        identifier=self.create();self.assertEqual(self.upload(identifier)[0],200)
        self.assertEqual(self.upload(identifier)[0],400)
        status,_=self.request('/api/projects/'+identifier+'/run',{'first':1,'until':9});self.assertEqual(status,202)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            task=read(self.app.project(identifier)/'tache.json')
            if task['state'] not in ('queued','running'):break
            time.sleep(.05)
        self.assertEqual(task['state'],'done',task)
        self.assertEqual(self.request('/files/'+identifier+'/podcast.txt')[0],200)
        self.assertEqual(self.request('/api/projects/'+identifier+'/settings',{**defaults(),'minutes':30})[1]['invalidated_from'],5)
        folder=self.app.project(identifier)
        self.assertTrue((folder/'etapes/04.json').exists());self.assertFalse((folder/'etapes/05.json').exists())
        self.assertEqual(self.request('/files/'+identifier+'/podcast.txt')[0],404)
        self.assertEqual(self.request('/files/'+identifier+'/%2e%2e%2fprojet.json')[0],404)
        self.assertEqual(self.upload(identifier)[0],409)

    def test_invalid_pdf_does_not_create_source_and_invalid_settings_are_rejected(self):
        identifier=self.create()
        self.assertEqual(self.request('/api/projects/'+identifier+'/pdf',headers={'X-Filename':'test.pdf'},raw=b'not a real PDF')[0],400)
        self.assertEqual(read(self.app.project(identifier)/'projet.json')['pdfs'],[])
        for invalid in [{'minutes':True},{'speakers':['Sophie','Sophie']},{'endpoint':'https://other.test'},{'num_ctx':100}]:
            with self.assertRaises(ValueError):settings({**defaults(),**invalid})

    def test_worker_survives_failure_to_save_status_and_can_retry(self):
        import app as module
        identifier=self.create();self.assertEqual(self.upload(identifier)[0],200)
        original_write=module.write
        def write_status(path,value):
            if Path(path).name=='tache.json' and value.get('state')!='queued':
                raise PermissionError('WinError 5 simulé : tache.json verrouillé')
            return original_write(path,value)
        with patch('app.write',side_effect=write_status):
            self.assertEqual(self.request('/api/projects/'+identifier+'/run',{'first':1,'until':1})[0],202)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and identifier not in self.app.task_errors:time.sleep(.01)
            state=self.app.summary(self.app.project(identifier))
            self.assertEqual(state['task']['state'],'error')
            self.assertIn('tache.json',state['task']['error']);self.assertTrue(self.app.worker.is_alive())
        self.assertEqual(self.request('/api/projects/'+identifier+'/run',{'first':1,'until':1})[0],202)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            task=read(self.app.project(identifier)/'tache.json')
            if task['state'] not in ('queued','running'):break
            time.sleep(.01)
        self.assertEqual(task['state'],'done',task);self.assertNotIn(identifier,self.app.task_errors)


if __name__=='__main__':unittest.main()
