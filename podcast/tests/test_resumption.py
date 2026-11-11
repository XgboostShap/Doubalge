"""Reprises après boucle Ollama, sauvegardes partielles et contexte de continuité."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest

from llm import Cancelled, ModelError, Ollama, RepetitionError
from pipeline import Pipeline, continuity
from storage import defaults, invalidate, read, write
from fixtures import FakeClient, StubServer, make_pdf

REPEAT = 'prediction aborted, token repeat limit reached'


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stub = StubServer()
        self.progress = []
        self.client = Ollama({**defaults(),'endpoint':self.stub.endpoint},self.root,progress=self.progress.append)
        self.payload = {'ideas':[{'id':'PDF1-P1-I001','statement':'Un fait'}]}
    def tearDown(self):
        self.stub.close();self.temp.cleanup()
    def ask(self):
        return self.client.ask('global_text',self.payload,'texte',lambda v: self.assertIn('[PDF1-P1-I001]',v['text']))
    def test_repeat_stream_restarts_fresh_then_only_valid_result_is_cached(self):
        self.stub.responses = [(200,[{'message':{'content':'NE PAS REINJECTER'}}, {'error':REPEAT}])]
        value = self.ask()
        self.assertEqual(len(self.stub.calls),2)
        second = self.stub.requests[1]
        self.assertNotIn('NE PAS REINJECTER',json.dumps(second))
        self.assertEqual([m['role'] for m in second['messages']],['system','user','user'])
        self.assertGreater(second['options']['repeat_penalty'],self.stub.requests[0]['options']['repeat_penalty'])
        self.assertEqual(second['options']['num_ctx'],16384)
        self.assertTrue(any('répété' in p for p in self.progress))
        self.assertEqual(len(list(self.root.glob('*.json'))),1)
        self.assertEqual(self.ask(),value);self.assertEqual(len(self.stub.calls),2)
    def test_repeat_exhaustion_is_bounded_preserves_exact_error_and_no_cache(self):
        self.stub.responses = [(200,[{'error':REPEAT}])]*2
        with self.assertRaisesRegex(RepetitionError,REPEAT):self.ask()
        self.assertEqual(len(self.stub.calls),2)
        self.assertFalse(list(self.root.glob('*.json')))
    def test_http_repeat_is_recoverable_but_unknown_model_is_not_retried(self):
        self.stub.responses = [(500,[{'error':REPEAT}])]
        self.ask();self.assertEqual(len(self.stub.calls),2)
        self.payload['ideas'][0]['statement']='Autre requête'
        self.stub.responses = [(404,[{'error':'model missing'}])]
        with self.assertRaisesRegex(ModelError,'HTTP 404'):self.ask()
        self.assertEqual(len(self.stub.calls),3)
    def test_cancel_before_repeat_retry_is_not_retried(self):
        self.stub.responses = [(200,[{'error':REPEAT}])]
        self.client.progress = lambda _:self.client.cancelled.set()
        with self.assertRaises(Cancelled):self.ask()
        self.assertEqual(len(self.stub.calls),1)
        self.assertFalse(list(self.root.glob('*.json')))
    def test_truncated_generation_is_not_accepted_or_cached(self):
        self.stub.responses = [(200,[{'message':{'content':'{"text":"incomplet"}'},'done':True,'done_reason':'length'}])]
        with self.assertRaisesRegex(ModelError,'limite de sortie'):self.ask()
        self.assertEqual(len(self.stub.calls),1)
        self.assertFalse(list(self.root.glob('*.json')))
    def test_independent_tasks_do_not_accumulate_conversation(self):
        self.ask();self.payload['ideas'][0]['statement']='Nouveau fait';self.ask()
        self.assertTrue(all(len(r['messages'])==2 for r in self.stub.requests))

    def test_grounded_review_uses_an_explicit_json_schema_in_ollama(self):
        import quality
        source='The signal loses power as it travels along the optical fibre.'
        candidates=[{'id':'PDF1-P1-I001','statement':'Le signal perd de la puissance.',
                     'explanation':'Les pertes augmentent au cours de la propagation.'}]
        self.client.ask('review_facts',{'source_text':source,'candidates':candidates},'Contrôle',
                        lambda v:quality.validate_review(v,candidates,source))
        schema=self.stub.requests[0]['format']
        self.assertIsInstance(schema,dict)
        self.assertFalse(schema['additionalProperties'])
        decisions=schema['properties']['decisions']
        self.assertEqual(decisions['required'],['PDF1-P1-I001'])
        kept=decisions['properties']['PDF1-P1-I001']
        self.assertEqual(kept['properties']['status']['enum'],['kept','corrected','excluded','uncertain'])
        self.assertIn('reason',kept['required']);self.assertIn('evidence',kept['required'])

    def test_old_invalid_cache_is_rechecked_and_replaced_by_a_valid_response(self):
        from pipeline import citations
        self.ask();path=next(self.root.glob('*.json'))
        path.write_text('{"text":"Une ancienne réponse sans référence."}')
        value=self.client.ask('global_text',self.payload,'texte',lambda v:citations(v,['PDF1-P1-I001']))
        self.assertIn('[PDF1-P1-I001]',value['text']);self.assertEqual(len(self.stub.calls),2)
        self.assertTrue(any('cache incompatible' in p for p in self.progress))


class PartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.project = Path(self.temp.name)
        (self.project/'sources').mkdir()
        make_pdf(self.project/'sources/a.pdf')
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[{'file':'a.pdf','name':'Optique.pdf'}]})
        self.parts = self.project/'etapes'/'parties'
    def tearDown(self):self.temp.cleanup()
    def test_completed_pdf_part_survives_failure_and_is_not_requested_again(self):
        class FailPart2(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if task=='part_summary' and payload['part']==2:raise ModelError('Panne simulée')
                return super().ask(task,payload,*args,**kwargs)
        with self.assertRaises(ModelError):Pipeline(self.project,FailPart2()).run(1,2)
        self.assertTrue((self.parts/'02-PDF1-P1.md').exists())
        self.assertFalse((self.parts/'02-PDF1-P2.json').exists())
        self.assertFalse((self.project/'etapes/02.json').exists())
        invalidate(self.project,2,partials=False)
        client = FakeClient();Pipeline(self.project,client).run(2,2)
        self.assertEqual([p['part'] for task,p in client.calls if task=='part_summary'],[2,3])
        self.assertEqual(sum((self.parts/f'02-PDF1-P{n}.md').exists() for n in (1,2,3)),3)
        # Une source modifiée ou une régénération ne doit pas réutiliser une ancienne partie.
        source = read(self.project/'etapes/01.json');source['data']['documents'][0]['parts'][0]['blocks'][0]['text']+=' ajout'
        write(self.project/'etapes/01.json',source)
        changed = FakeClient();Pipeline(self.project,changed).run(2,2)
        self.assertEqual([p['part'] for task,p in changed.calls if task=='part_summary'],[1])
        meta = read(self.project/'projet.json');meta['cache_generation']='nouvelle';write(self.project/'projet.json',meta)
        forced = FakeClient();Pipeline(self.project,forced).run(2,2)
        self.assertEqual(len([p for task,p in forced.calls if task=='part_summary']),3)
    def test_dialogue_is_saved_before_next_chapter_and_resumes_with_continuity(self):
        Pipeline(self.project,FakeClient()).run(1,7)
        class FailChapter2(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if task=='dialogue' and payload['chapter']['id']=='C2':raise ModelError('Panne simulée')
                return super().ask(task,payload,*args,**kwargs)
        with self.assertRaises(ModelError):Pipeline(self.project,FailChapter2()).run(8,8)
        markdown = (self.parts/'08-C1.md').read_text()
        self.assertIn('Sophie',markdown)
        self.assertTrue((self.project/'memoire/C1.json').exists())
        self.assertFalse((self.project/'etapes/08.json').exists())
        # Même sans cache LLM, le chapitre 1 n'est pas régénéré.
        client = FakeClient();Pipeline(self.project,client).run(8,9)
        dialogue = [p for task,p in client.calls if task=='dialogue']
        self.assertEqual([p['chapter']['id'] for p in dialogue],['C2'])
        self.assertTrue(dialogue[0]['memory']['last_turns'])
        self.assertIn('C1',dialogue[0]['memory']['definitions'])
        self.assertEqual((self.parts/'08-C1.md').read_text(),markdown)
        self.assertTrue(read(self.project/'exports/podcast.json')['all_planned_ids_present'])
        # Modification des paramètres : plus de réemploi du contenu périmé.
        meta=read(self.project/'projet.json');meta['settings']['speakers']=['Alice','Bob'];write(self.project/'projet.json',meta)
        changed=FakeClient();Pipeline(self.project,changed).run(8,8)
        self.assertEqual(len([p for task,p in changed.calls if task=='dialogue']),2)
    def test_invalidating_settings_archives_partials_even_without_completed_stage(self):
        self.parts.mkdir(parents=True)
        write(self.parts/'08-C1.json',{'data':'texte'})
        (self.parts/'08-C1.md').write_text('Dialogue')
        invalidate(self.project,8)
        self.assertFalse(list(self.parts.glob('*')))
        self.assertTrue(list((self.project/'versions').rglob('08-C1.md')))
    def test_repeat_fallback_splits_actual_text_without_losing_source_pages(self):
        class RepeatLarge(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if sum(len(b['text']) for b in payload['blocks'])>1300:raise RepetitionError(REPEAT)
                self.received.extend(payload['blocks'])
                return super().ask(task,payload,*args,**kwargs)
        client=RepeatLarge();client.received=[]
        chunk=[{'page':14,'text':'0123456789'*240}]
        value=Pipeline(self.project,client).summary_excerpt('PDF1',1,14,chunk)
        self.assertEqual(''.join(b['text'] for b in client.received),chunk[0]['text'])
        self.assertEqual({b['page'] for b in client.received},{14})
        self.assertEqual(len(value['ideas']),4)
    def test_fallback_does_not_loop_indefinitely_on_a_small_unreadable_excerpt(self):
        class AlwaysRepeat(FakeClient):
            def ask(self,*args,**kwargs):self.calls.append(1);raise RepetitionError(REPEAT)
        client=AlwaysRepeat()
        with self.assertRaises(RepetitionError):
            Pipeline(self.project,client).summary_excerpt('PDF1',1,14,[{'page':14,'text':'abc '*2000}])
        self.assertEqual(len(client.calls),4)
    def test_continuity_is_bounded_while_complete_archive_is_preserved(self):
        memory={'explained_ideas':{f'I{n}':'Idée '*500 for n in range(200)},
                'definitions':{f'Terme{n}':'définition '*500 for n in range(200)},
                'examples':['Exemple '*500]*100,'open_questions':['Question '*500]*100,
                'last_turns':[{'speaker':'Sophie','text':'Réplique '*1000,'idea_ids':['I1']}]*4}
        before=copy.deepcopy(memory)
        note=continuity(memory,{'title':'Terme1'})
        self.assertLess(len(json.dumps(note,ensure_ascii=False)),8000)
        self.assertEqual(memory,before)
        self.assertEqual(note['archived_counts']['ideas'],200)
        self.assertIn('Terme1',note['definitions'])
        self.assertIn('I199',note['explained_ideas'])


if __name__=='__main__':unittest.main()
