"""PM : libellés français sourcés et correction bornée des développements refusés."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from fixtures import FakeClient,StubServer
from llm import Cancelled,InvalidResponseError,ModelError,Ollama
from pipeline import Pipeline
from storage import defaults,read,write
import quality,writing


TERMS={'PM':[{'definition':'Predictive Maintenance','page':1}]}
BAD='La prévision minière (PM) anticipe les défaillances avec les journaux d’événements.'
GOOD='La maintenance prédictive (PM) anticipe les défaillances à partir des journaux d’événements, afin de préparer les interventions.'


class TermDrafts(FakeClient):
    def __init__(self,drafts,verdict='supported'):
        super().__init__();self.drafts=iter(drafts);self.verdict=verdict
    def ask(self,task,payload,instructions,validate,budget=4000):
        if task=='grounded_text':
            self.calls.append((task,copy.deepcopy(payload)));result=next(self.drafts)
            if isinstance(result,Exception):raise result
            value={'text':result};validate(value);return value
        if task=='writing_check' and self.verdict!='supported':
            self.calls.append((task,copy.deepcopy(payload)))
            return {'status':self.verdict,'reason':'La source ne confirme pas ce mécanisme.'}
        return super().ask(task,payload,instructions,validate,budget)


class SourceTerminology(unittest.TestCase):
    def test_pm_recognizes_standard_french_variants_in_all_definition_positions(self):
        for label in ('maintenance prédictive','maintenance prévisionnelle','entretien prédictif',
                      'maintenances prévisionnelles','entretiens prédictifs','Predictive Maintenance'):
            for text in (label+' (PM) anticipe les pannes.','PM ('+label+') anticipe les pannes.',
                         'PM désigne '+label+'.'):
                with self.subTest(text=text):quality.validate_acronyms(text,TERMS)

    def test_predictive_aliases_are_not_inferred_from_the_letters_pm(self):
        for source in ('Pain management','Pattern mining','Preventive maintenance'):
            for label in ('maintenance prédictive','maintenance prévisionnelle','entretien prédictif'):
                with self.subTest(source=source,label=label),self.assertRaises(quality.AcronymExpansionError):
                    quality.validate_acronyms(label+' (PM) est utilisée.',{'PM':[{'definition':source,'page':3}]})

    def test_wrong_meanings_remain_rejected_before_after_and_beside_pm(self):
        for label in ('prévision minière','maintenance préventive','gestion de la douleur'):
            for text in (label+' (PM) est employée.','PM ('+label+') est employée.','PM signifie '+label+'.'):
                with self.subTest(text=text),self.assertRaises(quality.AcronymExpansionError) as caught:
                    quality.validate_acronyms(text,TERMS)
                self.assertEqual(caught.exception.term,'PM')
                self.assertIn('maintenance prédictive',caught.exception.allowed_forms)
                self.assertIn('Predictive Maintenance',str(caught.exception))

    def test_diagnostics_include_the_received_label_and_source_allowlist(self):
        with self.assertRaises(quality.AcronymExpansionError) as caught:quality.validate_acronyms(BAD,TERMS)
        issue=caught.exception
        self.assertIn('prevision miniere',quality.definition_key(issue.received))
        self.assertEqual(issue.source_definitions,TERMS['PM'])
        self.assertEqual(issue.preferred,'maintenance prédictive')

    def test_writing_preferences_and_validation_use_the_same_source_bound_forms(self):
        for definition,expected in (('Predictive Maintenance','maintenance prédictive'),
                                    ('Frequent Itemset Mining','fouille de motifs fréquents'),
                                    ('Bayesian Mixture Model','modèle de mélange bayésien')):
            terms={'TERM':[{'definition':definition,'page':1}]}
            preferred=quality.writing_definition(definition)
            self.assertEqual(preferred,expected)
            quality.validate_acronyms(preferred+' (TERM) explique ce mécanisme.',terms)
        self.assertEqual(quality.writing_definition('Pain management'),'Pain management')

    def test_existing_plan_definition_labels_are_stable(self):
        # Ces libellés participent aux empreintes des plans 0.5.2 : ne pas les changer.
        self.assertEqual(quality.preferred_definition('Predictive Maintenance'),'Predictive Maintenance')
        self.assertEqual(quality.preferred_definition('Frequent Itemset Mining'),'Frequent Itemset Mining')
        self.assertEqual(quality.preferred_definition('Noise figure'),'facteur de bruit')

    def test_numeric_and_conditional_parentheses_are_not_rewritten_as_definitions(self):
        for text in ('Le PM (20 mW, 30 mW) est étudié.','Le PM (sans bruit) est étudié.',
                     'Le PM (under stable conditions) est étudié.'):
            quality.validate_acronyms(text,TERMS)


class TerminologyRecovery(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        write(self.root/'projet.json',{'settings':defaults(),'pdfs':[]})
        self.idea={'id':'PDF1-P1-I004','statement':'La maintenance prédictive anticipe les défaillances.',
            'explanation':'Les journaux d’événements servent à prévoir les interventions.',
            'document':'PDF1','pages':[1],
            'evidence':[{'page':1,'quote':'Predictive Maintenance (PM) aims to anticipate failures in industrial systems to plan early interventions. Event logs provide information on system health.'}]}
    def tearDown(self):self.temp.cleanup()
    def rewrite(self,client):return writing.rewrite(Pipeline(self.root,client),3,'Synthese-'+self.idea['id'],self.idea,TERMS)

    def test_recognized_french_variant_is_accepted_without_a_retry(self):
        client=TermDrafts([GOOD.replace('prédictive','prévisionnelle')]);result=self.rewrite(client)
        self.assertIn('prévisionnelle',result['text'])
        self.assertEqual(len([t for t,_ in client.calls if t=='grounded_text']),1)
        self.assertEqual(result['terminology_corrections'],[])

    def test_unknown_expansion_receives_a_targeted_repair_and_source_review(self):
        client=TermDrafts([BAD,GOOD]);result=self.rewrite(client)
        drafts=[p for t,p in client.calls if t=='grounded_text']
        self.assertEqual(drafts[0]['preferred_wording']['PM'],'maintenance prédictive')
        self.assertEqual(drafts[1]['mode'],'terminology');self.assertEqual(drafts[1]['draft'],BAD)
        self.assertEqual(drafts[1]['canonical_definition'],'maintenance prédictive')
        self.assertEqual(drafts[1]['source_definitions'],TERMS['PM'])
        self.assertEqual(drafts[0]['source'],drafts[1]['source'])
        self.assertEqual(result['text'],GOOD);self.assertEqual(result['terminology_corrections'][0]['term'],'PM')
        self.assertEqual(next(p for t,p in client.calls if t=='writing_check')['text'],GOOD)

    def test_persistent_wrong_expansion_is_bounded_and_never_saved_as_complete(self):
        client=TermDrafts([BAD,BAD])
        with self.assertRaisesRegex(InvalidResponseError,'PDF1-P1-I004.*PM'):self.rewrite(client)
        self.assertEqual(len(client.calls),2)
        self.assertFalse(list((self.root/'etapes/parties').glob('*.json')))

    def test_correct_pm_does_not_approve_an_invented_number_or_unit(self):
        client=TermDrafts([BAD,GOOD+' La puissance est garantie à 900 MW.'])
        with self.assertRaises((ValueError,InvalidResponseError)):self.rewrite(client)
        self.assertFalse(list((self.root/'etapes/parties').glob('*.json')))

    def test_correct_pm_still_requires_positive_semantic_review(self):
        client=TermDrafts([BAD,GOOD,BAD,GOOD],verdict='uncertain')
        with self.assertRaises(InvalidResponseError):self.rewrite(client)
        self.assertEqual(len([t for t,_ in client.calls if t=='writing_check']),2)
        self.assertFalse(list((self.root/'etapes/parties').glob('*.json')))

    def test_length_and_terminology_can_be_repaired_once_each_in_either_order(self):
        huge=('Les journaux d’événements fournissent des informations sur l’état du système. '*20)
        for drafts in ([huge,BAD,GOOD],[BAD,huge,GOOD]):
            with self.subTest(first=drafts[0][:30]),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);write(root/'projet.json',{'settings':defaults(),'pdfs':[]})
                client=TermDrafts(drafts)
                result=writing.rewrite(Pipeline(root,client),3,'Unique',self.idea,TERMS)
                self.assertEqual(result['text'],GOOD)
                self.assertEqual(len([t for t,_ in client.calls if t=='grounded_text']),3)

    def test_cancel_and_network_errors_during_terminology_repair_propagate(self):
        for error in (Cancelled(),ModelError('Connexion interrompue')):
            with self.subTest(error=type(error).__name__),self.assertRaises(type(error)):
                self.rewrite(TermDrafts([BAD,error]))
            self.assertFalse(list((self.root/'etapes/parties').glob('*.json')))

    def test_completed_old_entry_without_terminology_metadata_is_reused(self):
        self.rewrite(TermDrafts([GOOD]));path=next((self.root/'etapes/parties').glob('*.json'))
        value=read(path);value['data'].pop('terminology_corrections');write(path,value);before=path.read_bytes()
        client=TermDrafts([]);self.assertEqual(self.rewrite(client)['text'],GOOD)
        self.assertEqual(client.calls,[]);self.assertEqual(path.read_bytes(),before)

    def test_real_http_client_routes_the_exact_wrapped_error_to_terminology_repair(self):
        stub=StubServer()
        try:
            def event(text):return (200,[{'message':{'content':json.dumps({'text':text})},'done':True,'done_reason':'stop'}])
            stub.responses=[event(BAD),event(BAD),event(GOOD)]
            client=Ollama({**defaults(),'endpoint':stub.endpoint},self.root/'cache')
            result=self.rewrite(client)
            self.assertEqual(result['text'],GOOD)
            payload=stub.calls[2][1]
            self.assertEqual(payload['mode'],'terminology')
            self.assertEqual(payload['term_to_fix'],'PM');self.assertEqual(payload['draft'],BAD)
            self.assertEqual(stub.calls[-1][0],'writing_check')
        finally:stub.close()


if __name__=='__main__':unittest.main()
