"""Sigles DT, compilation bornée et reprise sans perdre les sources."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import quality
from llm import Cancelled, InvalidResponseError, ModelError, Ollama, RepetitionError, ResponseLimitError
from pipeline import Pipeline
from storage import defaults, read, write
from fixtures import FakeClient, StubServer, make_pdf


TERMS = {'DT':[{'definition':'Digital twin','page':27}]}


class CompilationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[]})
    def tearDown(self):self.temp.cleanup()

    def prepare(self, summaries):
        parts=[{'number':n,'summary':summary,'ideas':[{
            'id':f'PDF1-P{n}-I001','statement':'Le signal perd de la puissance.',
            'explanation':'Les pertes augmentent dans la fibre.',
            'pages':[n],'document':'PDF1','evidence':[{'quote':'The signal loses power.','page':n}]}]} for n,summary in enumerate(summaries,1)]
        data={'documents':[{'id':'PDF1','name':'Essai.pdf','parts':parts,'glossary':copy.deepcopy(TERMS)}]}
        write(self.project/'etapes/02.json',{'data':data})
        return data

    def test_dt_variants_depend_on_the_source_definition(self):
        for definition in ('Digital twin','digital twins','double numérique','doubles numériques','jumeaux numériques'):
            with self.subTest(definition=definition):
                quality.validate_acronyms('Les '+definition+' (DT) représentent le réseau.',TERMS)
        with self.assertRaises(ValueError):
            quality.validate_acronyms('Un jumeau numérique (DT).',{'DT':[{'definition':'Decision tree','page':27}]})

    def test_only_the_uncertain_section_is_quarantined(self):
        source={k:'' for k in quality.TITLES}
        source.update(problem='Comprendre les pertes dans le réseau.',concepts='Le double temporel (DT) est utilisé.')
        expected=copy.deepcopy(source)
        safe,warnings=quality.checked_sections(source,TERMS)
        self.assertEqual(source,expected)
        self.assertEqual(safe['problem'],source['problem']);self.assertEqual(safe['concepts'],'')
        self.assertEqual(len(warnings),1);self.assertEqual(warnings[0]['original'],source['concepts'])

    def test_summary_retains_valid_sections_and_saves_the_uncertain_formulation(self):
        class UnsafeDT(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                value={k:'' for k in quality.TITLES}
                value.update(problem='Comprendre les pertes.',concepts='Les doubles temporels (DT) représentent le réseau.')
                validate(value);return value
        packet=Pipeline(self.project,UnsafeDT()).structured_summary('DT','Synthèse',
            [{'statement':'Le DT représente le réseau.'}],TERMS,details=True)
        self.assertIn('Comprendre les pertes.',packet['text'])
        self.assertNotIn('doubles temporels',packet['text']);self.assertEqual(len(packet['warnings']),1)
        markdown=(self.project/'etapes/parties/02-DT-S0B1.md').read_text()
        self.assertIn('Texte automatique non retenu',markdown);self.assertIn('doubles temporels',markdown)

    def test_exhausted_summary_generation_keeps_source_statements(self):
        for error in (InvalidResponseError,RepetitionError,ResponseLimitError):
            class Failed(FakeClient):
                def ask(self,*args,**kwargs):raise error('Échec de formulation')
            packet=Pipeline(self.project,Failed()).structured_summary(error.__name__,'Synthèse',
                [{'statement':'Le DT représente le réseau.'}],TERMS,details=True)
            self.assertIn('Le DT représente le réseau.',packet['text']);self.assertTrue(packet['warnings'])

    def test_compilation_splits_without_losing_characters(self):
        original=('Une phrase avec des accents éèà et des espaces.\n\n'*700)+'FIN'
        fragments=list(quality.text_fragments(original))
        self.assertGreater(len(fragments),1)
        self.assertEqual(''.join(fragments),original);self.assertTrue(all(len(v)<=6000 for v in fragments))

    def test_stage3_preserves_the_saved_sources_and_registry(self):
        original=self.prepare(['Les digital twins (DT) représentent le réseau.','Les pertes diminuent la puissance.','Les limites dépendent des conditions.'])
        before=(self.project/'etapes/02.json').read_bytes();client=FakeClient()
        Pipeline(self.project,client).run(3,3)
        self.assertEqual((self.project/'etapes/02.json').read_bytes(),before)
        result=read(self.project/'etapes/03.json')['data']['documents'][0]
        self.assertEqual(result['parts'],original['documents'][0]['parts'])
        self.assertFalse(result['synthesis_provisional'])
        payload=next(p for task,p in client.calls if task=='pdf_synthesis')
        self.assertEqual(payload['glossary'],TERMS)
        self.assertTrue(all(set(p)=={'number','summary'} for p in payload['parts']))
        self.assertNotIn('ideas',json.dumps(payload))

    def test_unknown_dt_in_compilation_is_reported_without_forwarding_it(self):
        class UnsafeDT(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                value={'text':'Le double temporel (DT) représente le réseau.'};validate(value);return value
        self.prepare(['Le DT représente le réseau.'])
        Pipeline(self.project,UnsafeDT()).run(3,3)
        doc=read(self.project/'etapes/03.json')['data']['documents'][0]
        self.assertEqual(doc['synthesis'],'Le DT représente le réseau.');self.assertTrue(doc['synthesis_provisional'])
        self.assertIn('double temporel',doc['synthesis_warnings'][0]['original'])
        self.assertIn('Compilation provisoire',(self.project/'etapes/03.md').read_text())

    def test_compilation_uses_schema_and_a_bounded_output_budget(self):
        stub=StubServer()
        try:
            client=Ollama({**defaults(),'endpoint':stub.endpoint},self.project/'cache')
            result=Pipeline(self.project,client).compile_pdf('PDF1',[{'number':1,'summary':'Le signal perd de la puissance.'}],TERMS)
            self.assertFalse(result['provisional'])
            request=stub.requests[0]
            self.assertEqual(request['format']['required'],['text'])
            self.assertFalse(request['format']['additionalProperties'])
            self.assertEqual(request['options']['num_predict'],2000)
        finally:stub.close()

    def test_truncated_response_is_not_accepted_as_a_finished_compilation(self):
        stub=StubServer()
        try:
            stub.responses=[(200,[{'message':{'content':'{"text":"INCOMPLET"}'},'done':True,'done_reason':'length'}])]
            client=Ollama({**defaults(),'endpoint':stub.endpoint},self.project/'cache')
            result=Pipeline(self.project,client).compile_pdf('PDF1',[{'number':1,'summary':'La source reste disponible.'}],TERMS)
            self.assertTrue(result['provisional']);self.assertEqual(result['text'],'La source reste disponible.')
            self.assertNotIn('INCOMPLET',json.dumps(result));self.assertFalse(list((self.project/'cache').glob('*.json')))
        finally:stub.close()

    def test_long_compilation_resumes_at_the_unfinished_block(self):
        self.prepare(['Première partie. '+'Le signal diminue dans la fibre. '*150,
                      'Deuxième partie. '+'Les pertes dépendent du parcours. '*150])
        class Interrupted(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if len(self.calls)==1:raise ModelError('Ollama répond HTTP 404')
                return super().ask(task,payload,*args,**kwargs)
        with self.assertRaisesRegex(ModelError,'Étape 3/9.*404'):
            Pipeline(self.project,Interrupted()).run(3,3)
        saved=self.project/'etapes/parties/03-PDF1-S0B1.md';before=saved.read_bytes()
        self.assertFalse((self.project/'etapes/03.json').exists())
        client=FakeClient();Pipeline(self.project,client).run(3,3)
        calls=[p for task,p in client.calls if task=='pdf_synthesis']
        self.assertEqual(len(calls),2);self.assertIn('Deuxième partie',calls[0]['parts'][0]['summary'])
        self.assertTrue(all(sum(len(json.dumps(p,ensure_ascii=False)) for p in v['parts'])<=9000 for v in calls))
        self.assertEqual(saved.read_bytes(),before)

    def test_non_reducing_compilation_stops_and_retains_all_source_fragments(self):
        class Failed(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                self.calls.append((task,copy.deepcopy(payload)));raise RepetitionError('Répétition')
        source='DÉBUT. '+('Le réseau a des limites. '*900)+' FIN.'
        client=Failed();result=Pipeline(self.project,client).compile_pdf('PDF1',[{'number':1,'summary':source}],TERMS)
        self.assertTrue(result['provisional']);self.assertLess(len(client.calls),10)
        # Le seul ajout autorisé est le séparateur entre fragments.
        sent=''.join(p['summary'] for _,v in client.calls for p in v['parts'])
        self.assertEqual(sent,source)
        self.assertTrue(result['text'].startswith('DÉBUT.'));self.assertTrue(result['text'].endswith(' FIN.'))

    def test_a_changed_glossary_invalidates_compilation_checkpoint(self):
        self.prepare(['Le DT représente le réseau.']);first=FakeClient();Pipeline(self.project,first).run(3,3)
        data=read(self.project/'etapes/02.json');data['data']['documents'][0]['glossary']['DT'][0]['definition']='Decision tree'
        write(self.project/'etapes/02.json',data)
        second=FakeClient();Pipeline(self.project,second).run(3,3)
        self.assertEqual(len(second.calls),1)

    def test_cancel_and_disk_failures_remain_fatal(self):
        for error in (Cancelled,OSError):
            class Failed(FakeClient):
                def ask(self,*args,**kwargs):raise error('Arrêt')
            with self.subTest(error=error),self.assertRaises(error):
                Pipeline(self.project,Failed()).compile_pdf('PDF1',[{'number':1,'summary':'Une source.'}],TERMS)

    def test_synthesis_warnings_reach_the_final_report(self):
        (self.project/'sources').mkdir();make_pdf(self.project/'sources/a.pdf')
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[{'file':'a.pdf','name':'Essai.pdf'}]})
        Pipeline(self.project,FakeClient()).run(1,3)
        data=read(self.project/'etapes/03.json');warning={'section':'Concepts','reason':'À vérifier','original':'Un texte non retenu.'}
        data['data']['documents'][0]['synthesis_warnings']=[warning]
        data['data']['documents'][0]['parts'][0]['synthesis_warnings']=[warning]
        write(self.project/'etapes/03.json',data);Pipeline(self.project,FakeClient()).run(4,9)
        report=read(self.project/'exports/podcast.json')
        self.assertEqual(len(report['synthesis_warnings']),2)
        self.assertIn('Formulations de synthèse à vérifier',(self.project/'etapes/09.md').read_text())


if __name__=='__main__':unittest.main()
