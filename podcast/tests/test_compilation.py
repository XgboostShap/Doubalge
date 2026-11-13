"""Synthèses extractives et références des sources."""
import copy
from pathlib import Path
import tempfile
import unittest
import editorial,quality
from pipeline import Pipeline
from storage import defaults,read,write
from fixtures import FakeClient

class CompilationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[]})
    def tearDown(self):self.temp.cleanup()
    def prepare(self):
        parts=[{'number':n,'summary':'Ancienne formulation non retenue.','ideas':[{
            'id':f'PDF1-P{n}-I001','statement':f'Le phénomène {n} dépend des conditions.',
            'explanation':'Les conditions doivent être précisées.','document':'PDF1','pages':[n],
            'role':'concept','importance':'essential','evidence':[]}]} for n in (1,2,3)]
        for part in parts:
            for idea in part['ideas']:idea['source_hash']=editorial.source_hash(idea)
        data={'quality_version':quality.VERSION,'documents':[{'id':'PDF1','name':'Essai.pdf','parts':parts,
            'glossary':{'DT':[{'definition':'Digital twin','page':1}]}}]}
        write(self.project/'etapes/02.json',{'data':data});return data
    def test_dt_variants_depend_on_the_source_definition(self):
        terms={'DT':[{'definition':'Digital twin','page':1}]}
        for definition in ('digital twins','double numérique','jumeaux numériques'):
            quality.validate_acronyms('Les '+definition+' (DT) représentent le réseau.',terms)
        with self.assertRaises(ValueError):
            quality.validate_acronyms('Un jumeau numérique (DT).',{'DT':[{'definition':'Decision tree','page':1}]})
    def test_summary_cannot_promote_a_model_hallucination(self):
        class Poison(FakeClient):
            def ask(self,*args,**kwargs):raise AssertionError('Aucune synthèse libre ne doit être demandée.')
        source=[{'id':'PDF1-P1-I001','statement':'Le DT représente le réseau.','explanation':'Il dépend de données de surveillance.','role':'concept'}]
        packet=Pipeline(self.project,Poison()).structured_summary('DT','Synthèse',source,{},details=True)
        self.assertIn(source[0]['statement'],packet['text']);self.assertIn(source[0]['explanation'],packet['text'])
        self.assertIn('[PDF1-P1-I001]',packet['text'])
    def test_stage3_preserves_sources_but_ignores_old_freeform_summaries(self):
        original=self.prepare();before=(self.project/'etapes/02.json').read_bytes();client=FakeClient()
        Pipeline(self.project,client).run(3,3)
        doc=read(self.project/'etapes/03.json')['data']['documents'][0]
        self.assertEqual(doc['parts'],original['documents'][0]['parts'])
        self.assertEqual((self.project/'etapes/02.json').read_bytes(),before)
        self.assertNotIn('Ancienne formulation',doc['synthesis']);self.assertFalse(client.calls)
        self.assertEqual(len(doc['synthesis_ids']),3)
    def test_changed_glossary_is_carried_forward_without_rewriting_facts(self):
        self.prepare();Pipeline(self.project,FakeClient()).run(3,3)
        value=read(self.project/'etapes/02.json');value['data']['documents'][0]['glossary']['DT'][0]['definition']='Decision tree'
        write(self.project/'etapes/02.json',value);Pipeline(self.project,FakeClient()).run(3,3)
        doc=read(self.project/'etapes/03.json')['data']['documents'][0]
        self.assertEqual(doc['glossary']['DT'][0]['definition'],'Decision tree')
        self.assertEqual(doc['parts'],value['data']['documents'][0]['parts'])
    def test_old_source_results_require_upgrade(self):
        data=self.prepare();data['quality_version']='source-review-v2';write(self.project/'etapes/02.json',{'data':data})
        with self.assertRaisesRegex(ValueError,'Anciennes sources'):Pipeline(self.project,FakeClient()).run(3,3)
    def test_long_inputs_are_preserved_without_model_context_or_output_limits(self):
        text='La source conserve ses conditions et ses limites. '*1000
        result=Pipeline(self.project,FakeClient()).compile_pdf('PDF1',[{'number':1,'summary':text}],{})
        self.assertIn(text,result['text']);self.assertFalse(result['warnings'])
    def test_incomplete_roles_do_not_remove_source_facts_from_the_registry(self):
        self.prepare();Pipeline(self.project,FakeClient()).run(3,4)
        data=read(self.project/'etapes/04.json')['data']
        self.assertEqual(len(data['ideas']),3)
        self.assertEqual({i['id'] for i in data['ideas']},{f'PDF1-P{n}-I001' for n in (1,2,3)})

if __name__=='__main__':unittest.main()
