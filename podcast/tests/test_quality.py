"""Tri des contenus, appui aux sources et découpage des longs registres."""
import copy
from pathlib import Path
import tempfile
import unittest

import quality
from pipeline import Pipeline
from llm import InvalidResponseError,ModelError
from storage import defaults,read,write
from fixtures import FakeClient


def document(pages):
    return {'id':'PDF1','name':'Essai.pdf','parts':[{'number':n,'pages':[n],'blocks':[{'page':n,'text':t}]} for n,t in enumerate(pages,1)]}


class ContractsTests(unittest.TestCase):
    def test_known_front_matter_is_separated_but_abstract_and_body_are_kept(self):
        doc=document(['HAL Id: tel-123 Un dépôt scientifique.','Une dédicace personnelle.',
            'Abstract The scientific result is discussed with its limitations.',
            'Contents 1 Introduction 12','Acronyms and Abbreviations WSS Wavelength selective switch SOA Semiconductor optical amplifier',
            'Chapter 1 Introduction Le signal perd de la puissance.',
            'Bibliography [1] Un article.','[2] Un autre article.'])
        pages=quality.catalog(doc)
        self.assertEqual([p['kind'] for p in pages.values()],['cover','cover','content','contents','glossary','content','bibliography','bibliography'])
        terms=quality.glossary(pages)
        self.assertEqual(terms['WSS'][0]['definition'],'Wavelength selective switch')
        self.assertEqual(terms['SOA'][0]['definition'],'Semiconductor optical amplifier')
        self.assertEqual(set(quality.relevant_terms(terms,'Le WSS est utilisé.')),{'WSS'})
    def test_unrecognized_section_is_not_discarded(self):
        pages=quality.catalog(document(['Une page technique sans titre connu.','Un résultat qui reste à examiner.']))
        self.assertTrue(all(p['kind']=='content' for p in pages.values()))
        self.assertEqual(quality.catalog(document(['References to earlier experiments explain this result.']))[1]['kind'],'content')
        dense=quality.catalog(document(['HAL Id: xyz Une couverture.','Des résultats techniques sans titre. '*60]))
        self.assertEqual(dense[2]['kind'],'content')

    def test_wrong_acronym_expansions_are_rejected_using_the_source_glossary(self):
        terms={'SOA':[{'definition':'Semiconductor optical amplifier','page':29}],
               'WSS':[{'definition':'Wavelength selective switch','page':29}]}
        for value in ('Un sélecteur optique à fibres dopées (SOA).','WSS signifie White Space Spectrum.'):
            with self.subTest(value=value),self.assertRaises(ValueError):quality.validate_acronyms(value,terms)
        quality.validate_acronyms('Le SOA amplifie le signal par émission stimulée.',terms)
        quality.validate_acronyms('Semiconductor optical amplifier (SOA)',terms)

    def test_recognized_french_definitions_are_allowed_for_english_source_terms(self):
        terms={'AI':[{'definition':'Artificial intelligence','page':1}],
               'DT':[{'definition':'Digital twin','page':1}],
               'LLM':[{'definition':'Large language model','page':1}],
               'SOA':[{'definition':'Semiconductor optical amplifier','page':1}]}
        for value in ('L’intelligence artificielle (AI) utilise les données.',
                      'AI désigne l’intelligence artificielle.',
                      'AI signifie intelligence artificielle.',
                      'Les jumeaux numériques (DT) représentent le réseau.',
                      'Les grands modèles de langage (LLM) traitent les textes.',
                      'Un amplificateur optique à semi-conducteurs (SOA) amplifie le signal.',
                      '(AI) est employé dans cette partie.',
                      'Le terme AI (AI) est repris dans le texte.'):
            with self.subTest(value=value):quality.validate_acronyms(value,terms)

    def test_french_alias_is_not_inferred_from_the_acronym_alone(self):
        terms={'AI':[{'definition':'Acoustic impedance','page':1}]}
        with self.assertRaises(ValueError):quality.validate_acronyms('Intelligence artificielle (AI)',terms)
        with self.assertRaises(ValueError):quality.validate_acronyms('AI signifie intelligence artificielle.',terms)

    def test_definition_comparison_does_not_relax_source_quotes_or_units(self):
        self.assertEqual(quality.definition_key('génération-augmentée'),quality.definition_key('GENERATION AUGMENTEE'))
        self.assertNotEqual(quality.normalized('1 mW'),quality.normalized('1 MW'))
        self.assertEqual(quality.definition_aliases([{'definition':'Noise figure','page':1}]),{'noise figure','facteur de bruit'})
    def test_source_quote_coverage_and_explanation_are_checked(self):
        source='The model uncertainty requires larger operational margins. These margins reduce spectral efficiency.'
        candidate={'id':'PDF1-P1-I001','statement':'Le ML réduit les performances.','explanation':'Cette relation doit être vérifiée dans la source.'}
        value={'kept':[{'id':candidate['id'],'statement':'Les marges réduisent l’efficacité spectrale.',
            'explanation':'Les imprécisions du modèle imposent des marges plus grandes.',
            'status':'corrected','reason':'La cause est une marge, pas la méthode.',
            'evidence':['These margins reduce spectral efficiency.']}],'excluded':[]}
        quality.validate_review(value,[candidate],source)
        wrapped=copy.deepcopy(value);wrapped['kept'][0]['evidence']=['« These margins reduce spectral efficiency. »']
        quality.validate_review(wrapped,[candidate],source)
        vague=copy.deepcopy(value);vague['kept'][0]['statement']='Ces techniques diminuent les performances.'
        with self.assertRaises(ValueError):quality.validate_review(vague,[candidate],source)
        for field,bad in [('evidence',['This quotation was invented and is absent.']),('explanation','[65, 66].'),('explanation','De la thèse')]:
            invalid=copy.deepcopy(value);invalid['kept'][0][field]=bad
            with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):quality.validate_review(invalid,[candidate],source)
        invalid=copy.deepcopy(value);invalid['excluded']=[{'id':candidate['id'],'reason':'doublon'}]
        with self.assertRaises(ValueError):quality.validate_review(invalid,[candidate],source)
        self.assertNotEqual(quality.normalized('1 mW'),quality.normalized('1 MW'))
        mismatch=copy.deepcopy(value);mismatch['kept'][0]['evidence']=['these margins reduce spectral efficiency.']
        with self.assertRaises(ValueError):quality.validate_review(mismatch,[candidate],source)
    def test_synthesis_requires_the_five_sections_and_is_bounded(self):
        value={key:'' for key in quality.TITLES};value['problem']='Une question précise.'
        quality.validate_sections(value)
        self.assertIn('Problème posé',quality.section_markdown(value))
        with self.assertRaises(ValueError):quality.validate_sections({'text':'Un résumé de plus.'})
        value['problem']='mot '*951
        with self.assertRaises(ValueError):quality.validate_sections(value)
        value['problem']='The model is based on the data and the results are compared with the previous approach.'
        with self.assertRaises(ValueError):quality.validate_sections(value)


class QualityPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[]})
    def tearDown(self):self.temp.cleanup()
    def prepare(self,doc):write(self.project/'etapes/01.json',{'data':{'documents':[doc]}})
    def test_non_scientific_pages_never_reach_the_extraction_or_summary_model(self):
        self.prepare(document(['HAL Id: abc Une couverture.','Acknowledgements Merci à tous.','Bibliography [1] Un ouvrage.']))
        client=FakeClient();Pipeline(self.project,client).run(2,3)
        data=read(self.project/'etapes/02.json')['data']
        self.assertEqual(data['quality_version'],quality.VERSION)
        self.assertTrue(all(not part['ideas'] and part['page_notes'] for part in data['documents'][0]['parts']))
        self.assertFalse(client.calls)
    def test_empty_explanations_are_not_carried_forward_from_old_results(self):
        doc=document(['Le signal perd de la puissance dans la fibre et peut être amplifié.']*3);self.prepare(doc)
        previous={'documents':[{'id':'PDF1','name':'Essai','parts':[{'number':n,'ideas':[
           {'id':f'PDF1-P{n}-I001','statement':'Une idée.','explanation':'[65, 66].','pages':[n]}]} for n in (1,2,3)]}]}
        from storage import fingerprint
        write(self.project/'reprises/02.json',{'source':fingerprint({'documents':[doc]}),'generation':'initial','data':previous})
        # Le client simulé conserve cette explication invalide : le contrôle doit l'arrêter.
        with self.assertRaises(ValueError):Pipeline(self.project,FakeClient()).run(2,2)
        self.assertFalse((self.project/'etapes/02.json').exists())
    def test_inconclusive_review_is_reported_without_accepting_invalid_facts(self):
        self.prepare(document(['Le signal perd de la puissance dans la fibre et un amplificateur peut compenser les pertes.']*3))
        class Uncertain(FakeClient):
            def ask(self,task,*args,**kwargs):
                if task=='review_facts':raise InvalidResponseError('Citation absente après correction')
                return super().ask(task,*args,**kwargs)
        Pipeline(self.project,Uncertain()).run(2,2)
        result=read(self.project/'etapes/02.json')['data']
        parts=result['documents'][0]['parts']
        self.assertTrue(all(not p['ideas'] and p['uncertain_ideas'] for p in parts))
        self.assertEqual(read(self.project/'projet.json')['summary_warnings'],6)
        self.assertIn('à vérifier',(self.project/'etapes/02.md').read_text())
    def test_ambiguous_original_cause_is_flagged_instead_of_trusting_model_correction(self):
        candidate={'id':'PDF1-P1-I001','statement':'Ces techniques diminuent les performances.',
                   'explanation':'Les marges de sécurité limitent les performances.'}
        client=FakeClient();pipeline=Pipeline(self.project,client)
        value=pipeline.review_candidates({'candidates':[candidate]},[candidate],'Une source.')
        self.assertEqual(value['kept'],[])
        self.assertEqual(value['excluded'][0]['id'],candidate['id'])
        self.assertIn('À vérifier',value['excluded'][0]['reason']);self.assertFalse(client.calls)
    def test_unavailable_model_is_not_silently_turned_into_an_uncertainty(self):
        self.prepare(document(['Le signal perd de la puissance dans la fibre et un amplificateur peut compenser les pertes.']*3))
        class Offline(FakeClient):
            def ask(self,task,*args,**kwargs):
                if task=='review_facts':raise ModelError('Ollama répond HTTP 404')
                return super().ask(task,*args,**kwargs)
        with self.assertRaisesRegex(ModelError,'404'):Pipeline(self.project,Offline()).run(2,2)
        self.assertFalse((self.project/'etapes/02.json').exists())
    def test_synthesis_is_structured_and_pdf_compilation_does_not_resend_the_registry(self):
        self.prepare(document(['Le signal perd de la puissance dans la fibre et un amplificateur peut compenser les pertes.']*3))
        client=FakeClient();Pipeline(self.project,client).run(2,3)
        data=read(self.project/'etapes/02.json')['data']
        for part in data['documents'][0]['parts']:
            self.assertIn('### Problème posé',part['summary'])
            self.assertTrue(all(i['evidence'] for i in part['ideas']))
        payload=next(p for task,p in client.calls if task=='pdf_synthesis')
        self.assertTrue(all(set(p)=={'number','summary'} for p in payload['parts']))

    def test_french_ai_definition_does_not_abort_the_structured_summary(self):
        class FrenchAI(FakeClient):
            def ask(inner,task,payload,instructions,validate,budget=4000):
                if task!='part_structure':return super().ask(task,payload,instructions,validate,budget)
                inner.calls.append((task,copy.deepcopy(payload)))
                value={key:'' for key in quality.TITLES}
                value['problem']='L’intelligence artificielle (AI) aide à analyser les données du réseau.'
                validate(value);return value
        client=FrenchAI();terms={'AI':[{'definition':'Artificial intelligence','page':1}]}
        result=Pipeline(self.project,client).structured_summary('AI','Synthèse AI',
            [{'id':'PDF1-P1-I001','statement':'L’AI analyse les données.'}],terms)
        self.assertIn('intelligence artificielle (AI)',result)
        self.assertEqual(len(client.calls),1)
        self.assertTrue((self.project/'etapes/parties/02-AI-S0B1.md').exists())
    def test_long_registry_is_grouped_in_small_batches_with_no_missing_ids(self):
        ideas=[{'id':f'PDF1-P1-I{n:03}','statement':f'Le phénomène {n} possède une condition différente.',
                'explanation':'La condition change la réponse physique du système.','pages':[n],'document':'PDF1'} for n in range(1,251)]
        write(self.project/'etapes/03.json',{'data':{'documents':[{'id':'PDF1','name':'Long.pdf','parts':[{'ideas':ideas}]}]}})
        client=FakeClient();Pipeline(self.project,client).run(4,5)
        batches=[p for task,p in client.calls if task=='global_groups']
        self.assertTrue(len(batches)>1);self.assertTrue(all(len(p['ideas'])<=12 for p in batches))
        plan=read(self.project/'etapes/05.json')['data']
        covered=[i for c in plan['chapters'] for i in c['idea_ids']]+[e['idea_id'] for e in plan['exclusions']]
        self.assertEqual(set(covered),{i['id'] for i in ideas});self.assertEqual(len(covered),250)
        payload=next(p for task,p in client.calls if task=='plan_groups')
        self.assertNotIn('ideas',payload)
        self.assertTrue(all('idea_ids' not in g for g in payload['groups']))


if __name__=='__main__':unittest.main()
