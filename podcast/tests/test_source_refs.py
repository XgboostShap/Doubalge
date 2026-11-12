"""Régressions des identifiants omis, répétés ou inventés par le modèle."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from fixtures import FakeClient,StubServer,make_pdf
from llm import Cancelled,InvalidResponseError,ModelError,Ollama
from pipeline import Pipeline,ids_exact
from storage import defaults,read,write

REPORTED_IDS=[f'PDF1-P1-I{n:03}' for n in (46,47,48,49,50,67,68,69,121,122,123,124)]


def ideas():
    return [{'id':identity,'statement':f'Le phénomène numéro {n} a une condition précise.',
             'explanation':'La condition explique le comportement observé dans le système.',
             'pages':[n],'document':'PDF1'} for n,identity in enumerate(REPORTED_IDS,1)]


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[]})
    def tearDown(self):self.temp.cleanup()
    def pipeline(self,client):return Pipeline(self.project,client)
    def test_reported_twelve_ids_are_restored_without_being_sent_to_the_classifier(self):
        with self.assertRaisesRegex(ValueError,'Attendus : PDF1-P1-I046'):
            ids_exact(REPORTED_IDS[:-1]+[REPORTED_IDS[0]],REPORTED_IDS)
        client=FakeClient();result=self.pipeline(client).classify_batch(ideas(),1)
        covered=[i for g in result['groups'] for i in g['idea_ids']]
        self.assertEqual(covered,REPORTED_IDS)
        self.assertFalse(result['warnings'])
        payload=client.calls[0][1]
        self.assertEqual([i['ref'] for i in payload['ideas']],[f'I{n}' for n in range(1,13)])
        self.assertNotIn('PDF1-P1-I',json.dumps(payload))
    def test_incomplete_and_foreign_assignments_keep_all_source_ideas_once(self):
        class Incomplete(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                value={'assignments':{'I1':'Propagation','I2':'Propagation','I3':'',
                         'I4':17,'I999':'Sujet inventé','PDF1-P1-I999':'Autre sujet'}}
                validate(value);return value
        source=ideas();before=copy.deepcopy(source)
        result=self.pipeline(Incomplete()).classify_batch(source,1)
        covered=[i for g in result['groups'] for i in g['idea_ids']]
        self.assertEqual(set(covered),set(REPORTED_IDS));self.assertEqual(len(covered),12)
        self.assertEqual(result['groups'][0]['idea_ids'],REPORTED_IDS[:2])
        self.assertEqual(result['groups'][-1]['idea_ids'],REPORTED_IDS[2:])
        self.assertTrue(result['warnings']);self.assertEqual(source,before)
    def test_persistent_format_failure_keeps_one_explicit_provisional_group(self):
        class Invalid(FakeClient):
            def ask(self,*args,**kwargs):raise InvalidResponseError('Références manquantes')
        result=self.pipeline(Invalid()).classify_batch(ideas(),1)
        self.assertEqual(len(result['groups']),1)
        self.assertEqual(result['groups'][0]['idea_ids'],REPORTED_IDS)
        self.assertIn('à revoir',result['groups'][0]['title'])
        self.assertTrue(result['warnings'])
    def test_network_failure_and_cancellation_are_not_hidden_as_provisional_groups(self):
        class Failure(FakeClient):
            def ask(self,*args,**kwargs):raise self.error
        for error in (ModelError('HTTP 404'),Cancelled()):
            client=Failure();client.error=error
            with self.subTest(error=type(error)),self.assertRaises(type(error)):
                self.pipeline(client).classify_batch(ideas(),1)
        self.assertFalse((self.project/'etapes/parties/04-Lot1.json').exists())
    def test_completed_classification_resumes_and_different_source_ids_are_rebound(self):
        client=FakeClient();pipeline=self.pipeline(client)
        first=pipeline.classify_batch(ideas(),1)
        self.assertEqual(pipeline.classify_batch(ideas(),1),first)
        self.assertEqual(len(client.calls),1)
        other=[{**i,'id':i['id'].replace('PDF1','PDF2')} for i in ideas()]
        result=pipeline.classify_batch(other,1)
        self.assertEqual(len(client.calls),2)
        self.assertTrue(all(i.startswith('PDF2') for g in result['groups'] for i in g['idea_ids']))
    def test_missing_sentences_use_the_original_statement_and_keep_source_order(self):
        class Missing(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                value={'sentences':{'I2':'Une deuxième idée reformulée.','I1':'','I3':7,'I999':'Phrase étrangère.'}}
                validate(value);return value
        source=ideas();chapter={'id':'C1','title':'Essai','idea_ids':REPORTED_IDS}
        result=self.pipeline(Missing()).chapter_sentences(chapter,source)
        self.assertEqual([i['idea_id'] for i in result['items']],REPORTED_IDS)
        self.assertEqual(result['items'][0]['sentence'],source[0]['statement'])
        self.assertEqual(result['items'][1]['sentence'],'Une deuxième idée reformulée.')
        self.assertTrue(result['warnings'])
    def test_invalid_sentence_format_keeps_every_original_statement(self):
        class Invalid(FakeClient):
            def ask(self,*args,**kwargs):raise InvalidResponseError('JSON incomplet')
        source=ideas();chapter={'id':'C1','title':'Essai','idea_ids':REPORTED_IDS}
        result=self.pipeline(Invalid()).chapter_sentences(chapter,source)
        self.assertEqual([i['sentence'] for i in result['items']],[i['statement'] for i in source])
        self.assertTrue(result['warnings'])
    def test_nine_stages_preserve_coverage_and_export_provisional_warnings(self):
        (self.project/'sources').mkdir();make_pdf(self.project/'sources/a.pdf')
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[{'file':'a.pdf','name':'Essai.pdf'}]})
        class Missing(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task in ('global_groups','key_sentences'):
                    value={'assignments':{'I1':'Propagation'}} if task=='global_groups' else {'sentences':{}}
                    validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        self.pipeline(Missing()).run(1,9)
        final=read(self.project/'exports/podcast.json')
        self.assertTrue(final['all_planned_ids_present'])
        self.assertTrue(final['generation_warnings'])
        self.assertIn('Classements et formulations provisoires',(self.project/'etapes/09.md').read_text())


class ReferenceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name);self.stub=StubServer()
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[]})
        self.client=Ollama({**defaults(),'endpoint':self.stub.endpoint},self.project/'cache')
        self.pipeline=Pipeline(self.project,self.client)
    def tearDown(self):self.stub.close();self.temp.cleanup()
    def test_http_classifier_schema_requires_one_short_key_per_source_idea(self):
        self.pipeline.classify_batch(ideas(),1)
        schema=self.stub.requests[0]['format']
        fields=schema['properties']['assignments']
        self.assertEqual(fields['required'],[f'I{n}' for n in range(1,13)])
        self.assertFalse(fields['additionalProperties'])
        self.assertNotIn('PDF1-P1-I',json.dumps(self.stub.requests[0]))
    def test_an_old_invalid_response_is_retried_before_coverage_is_restored(self):
        self.stub.responses=[(200,[{'message':{'content':json.dumps({'groups':[{'title':'Test','idea_ids':REPORTED_IDS[:-1]}]})},
                                    'done':True,'done_reason':'stop'}])]
        result=self.pipeline.classify_batch(ideas(),1)
        self.assertEqual(len(self.stub.calls),2)
        self.assertEqual([i for g in result['groups'] for i in g['idea_ids']],REPORTED_IDS)
    def test_sentence_schema_uses_local_keys_and_program_restores_the_ids(self):
        result=self.pipeline.chapter_sentences({'id':'C1','title':'Essai','idea_ids':REPORTED_IDS},ideas())
        fields=self.stub.requests[0]['format']['properties']['sentences']
        self.assertEqual(fields['required'],[f'I{n}' for n in range(1,13)])
        self.assertEqual([i['idea_id'] for i in result['items']],REPORTED_IDS)
        self.assertNotIn('PDF1-P1-I',json.dumps(self.stub.requests[0]))


if __name__=='__main__':unittest.main()
