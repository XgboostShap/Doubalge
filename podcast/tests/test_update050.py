from issues import ReviewRequired
from review_queue import Reviews
"""Régressions du résultat utilisateur : rédaction, vérification et oralisation."""
import copy
from pathlib import Path
import tempfile
import unittest
from storage import write,read,defaults,fingerprint
from pipeline import Pipeline
from llm import InvalidResponseError
from fixtures import FakeClient
import test_editorial
from test_editorial import facts
import quality,editorial,writing,spoken,audio_export

class ObservedErrors(unittest.TestCase):
    def test_distribution_notice_cannot_be_a_source_for_a_network_property(self):
        self.assertTrue(quality.unusable_fact_text('Le réseau est structuré selon AI-LIGHT DT Huawei Propriétaire et distribué de manière restreinte.'))
        with self.assertRaises(ValueError):quality.explanatory_quote('APPENDIX A. NETWORK STATE IN AI-LIGHT DT Huawei Proprietary - Restricted Distribution')
    def test_phd_publications_and_production_comments_are_not_facts(self):
        for text in ['Le chapitre repose sur des publications réalisées pendant un doctorat de l’auteur.',
                     'La traduction française reconnue est le transmetteur dans un récepteur.']:
            with self.subTest(text=text):self.assertTrue(quality.unusable_fact_text(text))
    def test_observed_translation_errors_are_rejected(self):
        for text,source in [('Une égalisation automatique du pouvoir est proposée.','autonomous power equalization'),
                            ('Le transmetteur dans un récepteur convertit les données.','The transmitter converts data.'),
                            ('La lumière circule dans un fibre optique.','Light propagates along a fibre.'),
                            ('Les ions d’érium émettent de la lumière.','Erbium ions emit light.'),
                            ('Le terme secondaire explique la dispersion.','The second-order term causes dispersion.')]:
            with self.subTest(text=text),self.assertRaises(ValueError):quality.validate_technical_wording(text,source)
    def test_copied_or_invented_support_quotes_do_not_pass(self):
        fact={'evidence':['The transmitter converts digital data into an optical signal.']}
        with self.assertRaises(ValueError):quality.support_quotes({'statement_quote':'An unrelated phrase that is invented.','explanation_quote':fact['evidence'][0]},fact)
    def test_a_removed_unconfirmed_expansion_is_recorded_and_numbers_are_kept(self):
        terms={'DT':[{'definition':'Digital twin','page':1}]}
        value={'decisions':{'I1':{'status':'kept','statement':'Le DT (Data Transfer) représente le système physique.','explanation':'Le DT (20 mW, 30 mW) est observé dans cette expérience.','reason':'Test.'}}}
        quality.prepare_decisions(value,'A digital twin (DT) represents a physical system.',terms)
        fact=value['decisions']['I1'];self.assertNotIn('Data Transfer',fact['statement'])
        self.assertIn('20 mW, 30 mW',fact['explanation']);self.assertTrue(fact['automatic_corrections']);self.assertEqual(fact['status'],'corrected')
        for condition in ['Sans bruit','sans bruit','under stable conditions']:
            value={'decisions':{'I1':{'status':'kept','statement':'Le DT ('+condition+') représente le système.','explanation':'Le système est représenté dans ces conditions.','reason':'Test.'}}}
            quality.prepare_decisions(value,'A digital twin (DT) represents a physical system.',terms)
            self.assertIn(condition,value['decisions']['I1']['statement'])
            quality.validate_acronyms(value['decisions']['I1']['statement'],terms)
    def test_foreign_device_and_changed_case_unit_cannot_enter_a_paraphrase(self):
        idea={'statement':'Les WSS réduisent les pertes d’insertion.','explanation':'Le dispositif réduit ces pertes.','evidence':[{'quote':'The WSS devices minimize insertion loss.'}]}
        with self.assertRaises(ValueError):writing.validate_text('Les OMS réduisent les pertes d’insertion.',idea,{})
        idea={'statement':'La puissance mesurée vaut 1 mW.','explanation':'La mesure est expérimentale.','evidence':[]}
        with self.assertRaises(ValueError):writing.validate_text('La puissance mesurée vaut 1 MW.',idea,{})
    def test_spoken_version_preserves_measurement_case_and_removes_only_references(self):
        text='Dans cette grille : 50 GHz, 1 mW et 1 MW. Résultat [68, 69]. β2 vaut 2.'
        actual=spoken.prepare(text,strip_references=True)
        self.assertIn('50 gigahertz',actual);self.assertIn('1 milliwatts',actual);self.assertIn('1 mégawatts',actual)
        self.assertNotIn('[68',actual);self.assertIn('bêta 2',actual);self.assertIn('vaut 2',actual)
        self.assertIn('3,5 décibels',spoken.prepare('Dans ce test : 3.5 dB.'))
        self.assertIn('[0, 1]',spoken.prepare('La valeur appartient à [0, 1].'))
    def test_old_scripts_are_not_ready_for_audio_just_because_ids_are_present(self):
        with self.assertRaises(ValueError):audio_export.validate_script({'workflow_version':editorial.VERSION,'source_quality':quality.VERSION,'content_checks_passed':True})

class WritingFlow(unittest.TestCase):
    setUp=test_editorial.EditorialTests.setUp
    tearDown=test_editorial.EditorialTests.tearDown
    prepare=test_editorial.EditorialTests.prepare
    generate=test_editorial.EditorialTests.generate
    def test_paraphrasing_is_allowed_while_original_source_registry_is_preserved(self):
        source=facts(1);source[0].update(statement='Le signal perd de la puissance dans la fibre.',explanation='Une amplification compense une partie des pertes.')
        self.prepare(source)
        class Rewrite(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='grounded_text':
                    value={'text':'Dans la fibre, la puissance du signal diminue. Une amplification peut compenser ces pertes.'}
                    validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        self.generate(Rewrite());out=read(self.project/'exports/podcast.json')
        self.assertIn('la puissance du signal diminue',out['plain_text'])
        self.assertEqual(out['source_registry'][0]['statement'],source[0]['statement'])
        self.assertTrue(out['independent_final_review'])
    def test_semantically_rejected_paraphrase_never_becomes_a_complete_part(self):
        self.prepare(facts(1))
        class Reject(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='writing_check':return {'status':'uncertain','quote':'','reason':'Le mécanisme ne figure pas dans la preuve.'}
                return super().ask(task,payload,instructions,validate,budget)
        with self.assertRaises(ReviewRequired):self.generate(Reject(),until=6)
        self.assertFalse((self.project/'etapes/06.json').exists());self.assertFalse((self.project/'exports/podcast.json').exists())
    def test_final_review_can_repair_a_readability_problem_and_records_the_change(self):
        self.prepare(facts(1));self.generate(until=8)
        before=read(self.project/'etapes/08.json')['data']['chapters'][0]['turns'][1]['text']
        class Repair(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='writing_check' and payload.get('final_review') and payload['text']==before:
                    return {'status':'uncertain','quote':'','reason':'Éviter cette répétition dans la même réponse.'}
                if task=='grounded_text' and payload.get('feedback'):
                    value={'text':'La condition propre au phénomène doit être précisée pour éviter une généralisation.'};validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        Pipeline(self.project,Repair()).run(9,9);out=read(self.project/'exports/podcast.json')
        self.assertTrue(out['editorial_corrections']);self.assertNotEqual(out['editorial_corrections'][0]['after'],before)
    def test_an_unresolved_final_review_does_not_export_a_podcast(self):
        self.prepare(facts(1));self.generate(until=8)
        class RejectFinal(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if task=='writing_check' and payload.get('final_review'):return {'status':'uncertain','quote':'','reason':'Le passage reste insuffisamment clair.'}
                return super().ask(task,payload,*args,**kwargs)
        with self.assertRaises(ReviewRequired):Pipeline(self.project,RejectFinal()).run(9,9)
        self.assertFalse((self.project/'exports/podcast.json').exists())
    def test_a_method_cannot_be_classified_as_a_prerequisite_by_accident(self):
        source=facts(1);source[0]['statement']='Une stratégie multi-étapes optimise la configuration.'
        rows,_=editorial.annotated(Pipeline(self.project,FakeClient()),source)
        self.assertEqual(rows[0]['role'],'method');self.assertEqual(rows[0]['level'],'core')

if __name__=='__main__':unittest.main()
