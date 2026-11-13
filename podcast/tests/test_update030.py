"""Défauts observés dans l'export utilisateur : glossaire, sens et progression."""
import copy
import unittest
import quality,editorial
from fixtures import FakeClient
import test_editorial
from test_editorial import facts
from storage import read

class GlossaryTests(unittest.TestCase):
    def terms(self):
        return {'DT':[{'definition':'Digital twin','page':1}], 'SDN':[{'definition':'Software defined networking','page':1}],
                'OMS':[{'definition':'Optical multiplex section','page':1}]}
    def test_mixed_case_terms_are_not_swallowed_by_the_previous_definition(self):
        terms=quality.glossary({28:{'kind':'glossary','text':'QAM Quadrature amplitude modulation QoT Quality of transmission QPSK Quadrature phase shift keying SDN Software defined networking xix'}})
        self.assertEqual(terms['QAM'][0]['definition'],'Quadrature amplitude modulation')
        self.assertEqual(terms['QoT'][0]['definition'],'Quality of transmission')
        self.assertEqual(terms['QPSK'][0]['definition'],'Quadrature phase shift keying')
    def test_invalid_expansions_after_the_acronym_are_also_rejected(self):
        for text in ['Le DT (Data Transfer) observe le réseau.','Le SDN (Switched Digital Network) contrôle les équipements.',
                     'Les OMS (One-hop Multi-service Switch) sont connectés.']:
            with self.subTest(text=text),self.assertRaises(ValueError):quality.validate_acronyms(text,self.terms())
        quality.validate_acronyms('Le DT (jumeau numérique) représente le système.',self.terms())
        quality.validate_acronyms('Le SDN (Software-defined networking) contrôle le réseau.',self.terms())
    def test_plural_acronyms_are_checked_and_defined_at_first_use(self):
        terms={'LLM':[{'definition':'Large language model','page':1}]}
        with self.assertRaises(ValueError):quality.validate_acronyms('Les LLMs (Large liquid machines) traitent le texte.',terms)
        quality.validate_acronyms('Les grands modèles de langage (LLMs) traitent le texte.',terms)
        data={'documents':[{'id':'PDF1','glossary':terms}]}
        self.assertEqual(editorial.fact_definitions({'statement':'Les LLMs traitent le texte.','document':'PDF1'},editorial.definitions(data))[0]['term'],'LLM')
    def test_step_size_and_snr_margin_are_distinct(self):
        for text in ['Case-3 utilise une marge dynamique.','Case-2 utilise deux pas de regard à une étape avec une marge de 1dB.']:
            with self.subTest(text=text),self.assertRaises(ValueError):quality.validate_technical_wording(text,'Case-3: 1-step lookahead with dynamic step-size; Case-2: 2-step lookahead with 1dB step-size.')
        quality.validate_technical_wording('Le cas anticipe deux actions et utilise un pas de réglage de 1 dB.','Case-2: 2-step lookahead with 1dB step-size.')
    def test_grid_spacing_keeps_its_scope(self):
        with self.assertRaises(ValueError):quality.validate_technical_wording('Les canaux sont séparés par 50 GHz.','A wave grid with 50 GHz channel spacing.')
        quality.validate_technical_wording('Dans cette grille, les canaux sont séparés par 50 GHz.','A wave grid with 50 GHz channel spacing.')
    def test_a_distribution_notice_is_not_an_explanatory_fact(self):
        self.assertTrue(quality.unusable_fact_text('Le document est distribué à usage restreint.'))
    def test_repeating_the_whole_statement_is_not_an_explanation(self):
        statement='Le dispositif est flexible et ses capacités permettent une intégration dans plusieurs systèmes optiques.'
        value={'id':'I1','statement':statement,'explanation':'Le texte explique que '+statement,
            'status':'kept','reason':'Test.','evidence':['The device is flexible and integrates into optical systems.']}
        with self.assertRaisesRegex(ValueError,'recopie'):
            quality.validate_review({'kept':[value],'excluded':[]},[value],value['evidence'][0])
    def test_deduplication_never_changes_the_case_of_a_physical_symbol(self):
        idea={'statement':'mW est une unité.','explanation':'La mesure s’exprime en mW.'}
        self.assertTrue(editorial.passage(idea).startswith('mW'))

class PedagogyTests(unittest.TestCase):
    setUp=test_editorial.EditorialTests.setUp
    tearDown=test_editorial.EditorialTests.tearDown
    prepare=test_editorial.EditorialTests.prepare
    generate=test_editorial.EditorialTests.generate
    def test_topics_keep_related_ideas_together_and_foundations_come_first(self):
        source=facts(4)
        source[0].update(topic='Règles de contrôle',level='core',role='method')
        source[1].update(topic='Bases du signal',level='foundation',role='concept')
        source[2].update(topic='Règles de contrôle',level='core',role='result')
        source[3].update(topic='Bases du signal',level='foundation',role='concept')
        self.prepare(source);self.generate()
        plan=read(self.project/'etapes/05.json')['data']
        self.assertEqual(plan['chapters'][0]['title'],'Bases du signal')
        self.assertEqual(set(plan['chapters'][0]['idea_ids']),{source[1]['id'],source[3]['id']})
        final=read(self.project/'exports/podcast.json')
        self.assertIn('Bonjour',final['chapters'][0]['opening_transition'])
        self.assertIn(source[3]['statement'].rstrip('. '),final['chapters'][1]['opening_transition'])
        self.assertEqual(final['chapters'][-1]['turns'][-1]['kind'],'closing')
        self.assertIn('Pour conclure',final['plain_text']);self.assertTrue(final['content_checks_passed'])
    def test_specialized_details_stay_in_the_dossier_with_a_reason(self):
        source=facts(2);source[1].update(level='detail',importance='detail')
        self.prepare(source);self.generate()
        final=read(self.project/'exports/podcast.json')
        self.assertEqual(final['selected_count'],1);self.assertEqual(final['excluded_ideas'][0]['idea_id'],source[1]['id'])
    def test_final_review_rejects_wrong_expansion_even_with_the_original_hash(self):
        from pipeline import Pipeline
        source=facts(1);source[0]['statement']='Le DT (Data Transfer) représente le réseau.'
        self.prepare(source,{'DT':[{'definition':'Digital twin','page':1}]});self.generate(until=8)
        with self.assertRaisesRegex(ValueError,'Développement non confirmé'):Pipeline(self.project,FakeClient()).run(9,9)

if __name__=='__main__':unittest.main()
