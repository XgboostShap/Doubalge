"""Régression de l'étape 4 et qualité des preuves, avec données synthétiques."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

from fixtures import FakeClient,StubServer,make_pdf
from llm import Cancelled,InvalidResponseError,ModelError,Ollama,ResponseLimitError
from pipeline import Pipeline,citations
from storage import defaults,read,write
import quality


def source_ideas(count=2):
    return [{'id':f'PDF1-P2-I{109+n:03}','statement':f'Le réglage {n} progresse par étapes.',
        'explanation':'Les mesures déterminent le prochain ajustement.',
        'document':'PDF1','pages':[80]} for n in range(count)]


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[]})
    def tearDown(self):self.temp.cleanup()
    def pipeline(self,client):return Pipeline(self.project,client)

    def prepare3(self,ideas):
        write(self.project/'etapes/03.json',{'data':{'documents':[{'id':'PDF1','name':'Essai',
            'parts':[{'number':2,'ideas':ideas}]}]}})

    def test_exact_reported_id_is_preserved_when_the_model_omits_its_paragraph(self):
        ideas=source_ideas(1)
        with self.assertRaisesRegex(ValueError,'Attendus : PDF1-P2-I109'):
            citations({'text':'Une formulation sans référence.'},[ideas[0]['id']])
        class Missing(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='common_paragraphs':
                    self.calls.append((task,copy.deepcopy(payload)));value={'paragraphs':{}}
                    validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        self.prepare3(ideas);client=Missing();self.pipeline(client).run(4,4)
        result=read(self.project/'etapes/04.json')['data']
        self.assertIn('[PDF1-P2-I109]',result['groups'][0]['text'])
        self.assertIn(ideas[0]['statement'],result['groups'][0]['text']);self.assertTrue(result['text_warnings'])
        payload=next(p for task,p in client.calls if task=='common_paragraphs')
        self.assertNotIn('PDF1-P2-I109',json.dumps(payload))

    def test_missing_or_foreign_paragraphs_never_change_source_coverage(self):
        class Wrong(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                value={'paragraphs':{'I1':'Le premier réglage repose sur une mesure. [PDF9-P9-I999]',
                    'I2':None,'I999':'Un passage étranger au registre.'}}
                validate(value);return value
        ideas=source_ideas();before=copy.deepcopy(ideas)
        packet=self.pipeline(Wrong()).common_text({'id':'G1','title':'Réglages'},ideas)
        self.assertEqual(re.findall(r'\[(PDF\d+-P\d+-I\d+)\]',packet['text']),[i['id'] for i in ideas])
        self.assertEqual(ideas,before);self.assertNotIn('passage étranger',packet['text'])
        self.assertIn(ideas[1]['statement'],packet['text']);self.assertTrue(packet['warnings'])

    def test_invalid_or_truncated_generation_keeps_sources_and_reports_the_failure(self):
        for error in (InvalidResponseError,ResponseLimitError):
            class Failed(FakeClient):
                def ask(self,*args,**kwargs):raise error('Réponse inutilisable')
            packet=self.pipeline(Failed()).common_text({'id':error.__name__,'title':'Réglages'},source_ideas())
            self.assertTrue(packet['warnings'])
            for idea in source_ideas():self.assertIn(idea['statement'],packet['text'])

    def test_a_generic_model_paragraph_keeps_the_precise_source_statement(self):
        class Generic(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                value={'paragraphs':{'I1':'Nous allons discuter de ce sujet important.'}};validate(value);return value
        idea=source_ideas(1)[0];packet=self.pipeline(Generic()).common_text({'id':'G1','title':'Réglages'},[idea])
        self.assertIn(idea['statement'],packet['text'])

    def test_network_cancel_and_disk_errors_are_not_converted_to_source_fallbacks(self):
        for error in (ModelError,Cancelled,OSError):
            class Failed(FakeClient):
                def ask(self,*args,**kwargs):raise error('Arrêt')
            with self.subTest(error=error),self.assertRaises(error):
                self.pipeline(Failed()).common_text({'id':'G1','title':'Réglages'},source_ideas())

    def test_finished_common_text_group_survives_a_later_failure(self):
        self.prepare3(source_ideas(4))
        class Interrupted(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if task=='common_paragraphs' and payload['ideas'][0]['statement'].startswith('Le réglage 2'):
                    raise ModelError('HTTP 404')
                return super().ask(task,payload,*args,**kwargs)
        with self.assertRaisesRegex(ModelError,'Étape 4/9.*404'):self.pipeline(Interrupted()).run(4,4)
        path=self.project/'etapes/parties/04-G1.md';before=path.read_bytes()
        client=FakeClient();self.pipeline(client).run(4,4)
        calls=[p for task,p in client.calls if task=='common_paragraphs']
        self.assertEqual(len(calls),1);self.assertTrue(calls[0]['ideas'][0]['statement'].startswith('Le réglage 2'))
        self.assertEqual(path.read_bytes(),before)

    def test_all_summary_blocks_and_source_anchors_reach_the_compilation(self):
        ideas=source_ideas(31);client=FakeClient()
        packet=self.pipeline(client).structured_summary('All','Tous les concepts',ideas,{},details=True)
        self.assertEqual(len([t for t,p in client.calls if t=='part_structure']),4)
        for idea in ideas:
            self.assertIn('['+idea['id']+'] '+idea['statement'],packet['text'])
        self.assertIn(ideas[-1]['statement'],packet['text'])

    def test_nine_stages_report_common_text_and_explanation_fallbacks(self):
        (self.project/'sources').mkdir();make_pdf(self.project/'sources/a.pdf')
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[{'file':'a.pdf','name':'Essai.pdf'}]})
        class Missing(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task in ('common_paragraphs','explanation_paragraphs'):
                    value={'paragraphs':{}};validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        self.pipeline(Missing()).run(1,9)
        final=read(self.project/'exports/podcast.json')
        self.assertTrue(final['all_planned_ids_present']);self.assertTrue(final['generation_warnings'])
        explanations=read(self.project/'etapes/07.json')['data'];self.assertTrue(explanations['warnings'])
        self.assertTrue(all(ch['transition'] for ch in explanations['chapters']))


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[]})
        self.candidates=source_ideas()
        self.source='CHAPTER 2. OPTICAL NETWORKS The signal loses power along the fibre. Measurements determine the next adjustment.'
        self.payload={'source_page':80,'source_text':self.source,'candidates':self.candidates,'glossary':{}}
    def tearDown(self):self.temp.cleanup()

    def test_headers_table_columns_and_bibliography_are_not_explanatory_evidence(self):
        for quote in ('CHAPTER 2. OPTICAL NETWORKS','APPENDIX A. NETWORK STATE Indexf c [GHz]λ c [nm]',
                      'C. Example et al., “A test paper,” Journal of Tests, vol. 1, 2025.'):
            with self.subTest(quote=quote),self.assertRaises(ValueError):quality.explanatory_quote(quote)
        quality.explanatory_quote('The transmitted power decreases as distance increases.')

    def test_one_bad_quote_does_not_discard_the_other_source_idea(self):
        class OneBad(FakeClient):
            def ask(inner,task,payload,instructions,validate,budget=4000):
                if task!='review_facts':return super().ask(task,payload,instructions,validate,budget)
                inner.calls.append((task,copy.deepcopy(payload)))
                value={'decisions':{i['id']:{'statement':i['statement'],'explanation':i['explanation'],
                    'status':'kept','reason':'Contrôle simulé.','evidence':[
                        'The signal loses power along the fibre.' if i['id'].endswith('109') else 'CHAPTER 2. OPTICAL NETWORKS']}
                    for i in payload['candidates']}}
                validate(value);return value
        client=OneBad();result=Pipeline(self.project,client).review_candidates(self.payload,self.candidates,self.source)
        self.assertEqual([i['id'] for i in result['kept']],['PDF1-P2-I109'])
        self.assertEqual([i['id'] for i in result['excluded']],['PDF1-P2-I110'])
        review=[p for t,p in client.calls if t=='review_facts']
        self.assertEqual(len(review),2);self.assertEqual([i['id'] for i in review[1]['candidates']],['PDF1-P2-I110'])

    def test_invalid_bulk_format_is_retried_per_idea_and_good_decisions_are_saved(self):
        class BadBulk(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if task=='review_facts' and len(payload['candidates'])>1:raise InvalidResponseError('Objet absent')
                return super().ask(task,payload,*args,**kwargs)
        result=Pipeline(self.project,BadBulk()).review_candidates(self.payload,self.candidates,self.source)
        self.assertEqual(len(result['kept']),2)
        self.assertTrue((self.project/'etapes/parties/02-Verify-PDF1-P2-I109.md').exists())

    def test_exact_quote_with_unsupported_meaning_is_not_accepted(self):
        class Contradiction(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task!='fact_support':return super().ask(task,payload,instructions,validate,budget)
                value={'verdicts':{i['ref']:{'status':'contradicted','reason':'La citation décrit une baisse, et non une hausse.'} for i in payload['facts']}}
                validate(value);return value
        result=Pipeline(self.project,Contradiction()).review_candidates(self.payload,self.candidates,self.source)
        self.assertEqual(result['kept'],[]);self.assertEqual(len(result['excluded']),2)
        self.assertTrue(all('citations en contradiction' in i['reason'] for i in result['excluded']))

    def test_support_checkpoint_is_bound_to_all_original_ids_and_source_metadata(self):
        facts=[{**i,'status':'kept','reason':'Premier contrôle.','evidence':['The signal loses power along the fibre.']} for i in self.candidates]
        client=FakeClient();pipeline=Pipeline(self.project,client);pipeline.check_support(facts,80)
        changed=copy.deepcopy(facts);changed[1]['id']='PDF1-P2-I999';changed[1]['reason']='Contrôle révisé.'
        result=pipeline.check_support(changed,80)
        self.assertEqual([i['id'] for i in result['kept']],[i['id'] for i in changed])
        self.assertEqual(result['kept'][1]['reason'],'Contrôle révisé.')

    def test_missing_second_verdict_is_retried_alone_and_never_assumed_supported(self):
        facts=[{**i,'status':'kept','reason':'Test','evidence':['The signal loses power along the fibre.']} for i in self.candidates]
        class Missing(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                self.calls.append((task,copy.deepcopy(payload)))
                if len(payload['facts'])==1:raise ResponseLimitError('Limite de sortie')
                value={'verdicts':{'I1':{'status':'supported','reason':'La citation appuie cette idée.'}}};validate(value);return value
        client=Missing();result=Pipeline(self.project,client).check_support(facts,80)
        self.assertEqual([i['id'] for i in result['kept']],['PDF1-P2-I109'])
        self.assertEqual([i['id'] for i in result['excluded']],['PDF1-P2-I110'])
        self.assertEqual([f['ref'] for f in client.calls[1][1]['facts']],['I2'])

    def test_model_connectivity_failure_during_support_check_still_stops_the_stage(self):
        class Offline(FakeClient):
            def ask(self,task,*args,**kwargs):
                if task=='fact_support':raise ModelError('HTTP 404')
                return super().ask(task,*args,**kwargs)
        with self.assertRaisesRegex(ModelError,'404'):
            Pipeline(self.project,Offline()).review_candidates(self.payload,self.candidates,self.source)

    def test_copying_the_candidate_is_not_a_positive_independent_verdict(self):
        facts=[{**i,'status':'kept','reason':'Test','explanation':'La baisse de cette grandeur réduirait aussi une autre grandeur.',
                'evidence':['The signal loses power along the fibre.']} for i in self.candidates]
        class Echo(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                value={'verdicts':{f['ref']:{'status':'supported','reason':f['explanation']} for f in payload['facts']}}
                validate(value);return value
        result=Pipeline(self.project,Echo()).check_support(facts,80)
        self.assertFalse(result['kept']);self.assertEqual(len(result['excluded']),2)
        self.assertTrue(all('recopie' in f['reason'] for f in result['excluded']))

    def test_embedding_a_long_claim_in_an_affirmation_is_still_not_a_justification(self):
        fact={'statement':'La méthode réduit cette grandeur et provoque ainsi une diminution de toutes les ressources nécessaires.',
              'explanation':'Le mécanisme doit être expliqué à partir de la source.'}
        self.assertTrue(quality.copied_support_reason({'reason':'La citation confirme cet énoncé : '+fact['statement']},fact))


class SchemaTests(unittest.TestCase):
    def test_common_text_request_uses_short_keys_and_keeps_real_ids_out_of_the_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp);write(project/'projet.json',{'settings':defaults(),'pdfs':[]});stub=StubServer()
            try:
                client=Ollama({**defaults(),'endpoint':stub.endpoint},project/'cache')
                value=Pipeline(project,client).common_text({'id':'G1','title':'Réglages'},source_ideas(1))
                request=stub.requests[0]
                self.assertEqual(request['format']['properties']['paragraphs']['required'],['I1'])
                self.assertNotIn('PDF1-P2-I109',json.dumps(request));self.assertIn('[PDF1-P2-I109]',value['text'])
            finally:stub.close()


if __name__=='__main__':unittest.main()
