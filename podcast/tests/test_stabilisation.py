"""Reprises, décisions de source et absence de transfert externe implicite."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from app import App
from fixtures import FakeClient, StubServer, make_pdf
from issues import DownloadConsentRequired, ReviewRequired, SourceIssue, repair_message
from llm import InvalidResponseError, ModelError, Ollama, RequestBudgetError
from pipeline import Pipeline
from review_queue import Reviews, apply_corrections
from storage import defaults, fingerprint, read, write
import audio_export
import editorial
import quality
import source_checks


QUOTE='Frequent patterns depend on a threshold in the data. The threshold determines retained patterns under the stated conditions.'
TEXT='Les motifs fréquents dépendent du seuil choisi. Ce seuil fixe les motifs retenus dans les conditions décrites.'


def fact(number=1):
    value={'id':f'PDF1-P1-I{number:03}','statement':'Les motifs fréquents dépendent du seuil dans les données.',
        'explanation':'Le seuil doit être indiqué avec ses conditions.','document':'PDF1','pages':[1],
        'role':'concept','importance':'essential','evidence':[{'page':1,'quote':QUOTE}]}
    value['source_hash']=editorial.source_hash(value)
    return value


class Replies(FakeClient):
    def ask(self,task,payload,instructions,validate,budget=4000):
        if task=='grounded_text':
            self.calls.append((task,copy.deepcopy(payload)));value={'text':TEXT};validate(value);return value
        return super().ask(task,payload,instructions,validate,budget)


class SourceConstraints(unittest.TestCase):
    def test_lost_exponent_cannot_be_interpreted_in_digits_or_words(self):
        evidence='A fully correlated Bernoulli distribution requires 2d parameters.'
        for text in ('Le modèle nécessite 2d paramètres.', 'Le modèle nécessite deux fois d paramètres.',
                     'Le modèle nécessite deux puissance d paramètres.', 'Le modèle nécessite 2^d paramètres.'):
            with self.subTest(text=text),self.assertRaises(SourceIssue) as error:source_checks.validate(text,evidence)
            self.assertEqual(error.exception.category,'formula')
        source_checks.validate('Le nombre de paramètres dépend de la dimension et devient difficile à gérer.',evidence)

    def test_a_legible_power_is_not_treated_as_a_lost_exponent(self):
        source_checks.validate('Le modèle nécessite 2^d paramètres.','The model requires 2^d parameters.')

    def test_comparison_does_not_prove_combination(self):
        with self.assertRaises(SourceIssue):source_checks.validate('La méthode combine les sorties des classifieurs.',
            'We compare three classifiers. Table II reports the accuracy for the evaluated classifiers.')
        source_checks.validate('La méthode combine les sorties des classifieurs.',
            'We compare classifiers, including an ensemble combining their predictions.')

    def test_result_keeps_almost_all_reserve(self):
        evidence='Our method performs better for almost all data sets.'
        with self.assertRaises(SourceIssue):source_checks.validate('Les résultats sont meilleurs sur tous les jeux de données.',evidence)
        source_checks.validate('Les résultats sont meilleurs sur presque tous les jeux de données.',evidence)
        source_checks.validate('Les résultats ne sont pas meilleurs dans tous les cas.',evidence)

    def test_feedback_for_a_formula_does_not_claim_json_is_wrong(self):
        kind,message=repair_message(SourceIssue('Exposant perdu.','formula'))
        self.assertEqual(kind,'formula');self.assertIn('qualitativement',message);self.assertNotIn('structure',message)
        try:json.loads('incomplet')
        except ValueError as error:kind,message=repair_message(error)
        self.assertEqual(kind,'format');self.assertIn('JSON',message)

    def test_lower_computation_cost_does_not_become_a_higher_cost(self):
        source='Many older methods are computationally intensive. We propose a model to infer the patterns with a low computational cost.'
        with self.assertRaises(SourceIssue):source_checks.validate('Cette approche permet de réduire le nombre de tests statistiques, ce qui rend la méthode plus coûteuse en calcul.',source)
        source_checks.validate('La nouvelle approche détermine les motifs à faible coût de calcul.',source)

    def test_flat_measurement_table_does_not_prove_a_combination(self):
        source='TABLE II TEST ACCURACY OF CLASSIFIERS: '+ ' '.join(str(n/100) for n in range(20))
        with self.assertRaises(SourceIssue):source_checks.validate('Les résultats obtenus pour chaque jeu de données ont ensuite été combinés.',source)
        source_checks.validate('Les classifieurs sont évalués selon leur précision dans les expériences.',source)


class LocalClient(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.stub=StubServer()
        self.client=Ollama({**defaults(),'endpoint':self.stub.endpoint},self.temp.name)
    def tearDown(self):self.stub.close();self.temp.cleanup()
    def ask(self):return self.client.ask('global_text',{'ideas':[{'id':'I1','statement':'Un fait.'}]},'texte',lambda value:None)

    def test_cloud_model_is_rejected_before_a_source_chat(self):
        self.client.config['model']='mistral:cloud'
        with self.assertRaisesRegex(ModelError,'cloud'):self.ask()
        self.assertFalse(self.stub.calls)

    def test_ollama_remote_alias_is_rejected_before_a_source_chat(self):
        self.stub.model_info={'remote_host':'https://example.invalid','remote_model':'alias','details':{'format':'gguf'}}
        with self.assertRaisesRegex(ModelError,'distant'):self.ask()
        self.assertFalse(self.stub.calls)

    def test_unidentified_model_is_not_assumed_to_be_local(self):
        self.stub.model_info={}
        with self.assertRaisesRegex(ModelError,'confirmer'):self.ask()
        self.assertFalse(self.stub.calls)

    def test_local_model_works_and_cached_response_needs_no_server(self):
        first=self.ask();self.assertEqual(len(self.stub.calls),1)
        with patch.object(self.client,'_request',side_effect=AssertionError('Un cache validé ne contacte pas le serveur.')):
            self.assertEqual(first,self.ask())

    def test_request_budget_applies_across_nested_corrections(self):
        with self.client.request_scope(2):
            self.ask()
            self.client.ask('global_text',{'ideas':[]},'autre texte',lambda value:None)
            with self.assertRaises(RequestBudgetError):
                self.client.ask('global_text',{'ideas':[]},'encore une tentative',lambda value:None)
        self.assertEqual(len(self.stub.calls),2)

    def test_no_automatic_mp3_installation_without_scoped_consent(self):
        with patch('audio_export.encoder',side_effect=ValueError('absent')),patch('audio_export.run_process') as run:
            with self.assertRaises(DownloadConsentRequired):audio_export.prepare_encoder(threading.Event(),lambda _:None)
            run.assert_not_called()

    def test_existing_mp3_encoder_needs_no_permission_or_download(self):
        with patch('audio_export.encoder',return_value='already-local'),patch('audio_export.run_process') as run:
            self.assertEqual(audio_export.prepare_encoder(threading.Event(),lambda _:None),'already-local')
            run.assert_not_called()


class SourceDecisions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=App(Path(self.temp.name)/'data',FakeClient)
        identifier=self.app.create({'name':'Reprise'})['id'];self.root=self.app.project(identifier)
        make_pdf(self.root/'sources/p.pdf')
        meta=read(self.root/'projet.json');meta['pdfs']=[{'file':'p.pdf','name':'Essai.pdf'}];write(self.root/'projet.json',meta)
        self.ideas=[fact(1),fact(2)]
        source={'documents':[{'id':'PDF1','name':'Essai.pdf','parts':[{'number':1,'pages':[1],
            'blocks':[{'page':1,'text':QUOTE}]}]}]}
        write(self.root/'etapes/01.json',{'data':source})
        self.data={'quality_version':quality.VERSION,'documents':[{'id':'PDF1','name':'Essai.pdf','glossary':{},
            'parts':[{'number':1,'ideas':self.ideas,'excluded_ideas':[],'uncertain_ideas':[],'summary':TEXT}]}]}
        write(self.root/'etapes/02.json',{'data':self.data});self.reviews=Reviews(self.root)
    def tearDown(self):self.app.close();self.temp.cleanup()
    def record(self,number=1,step=3):
        return self.reviews.record(step,'Synthese-'+self.ideas[number-1]['id'],self.ideas[number-1],SourceIssue('Vérifier la réserve.','scope'))
    def correction(self,item,**extra):
        return {'id':item['id'],'action':'correct','statement':'Les motifs retenus dépendent du seuil choisi.',
                'explanation':'Le résultat reste lié aux conditions décrites dans les données.',
                'evidence':[{'page':1,'quote':QUOTE}],'note':'Page relue et réserve conservée.',**extra}

    def test_repeated_question_is_grouped_and_old_source_is_marked_stale(self):
        first=self.record();self.record()
        self.assertEqual(len(self.reviews.pending()),1);self.assertEqual(self.reviews.pending()[0]['attempts'],2)
        changed=copy.deepcopy(self.ideas[0]);changed['statement']='Autre formulation de la source.'
        self.reviews.record(3,first['key'],changed,SourceIssue('Vérifier.'))
        self.assertEqual(len(self.reviews.pending()),1)
        self.assertEqual(self.reviews.data()['items'][0]['status'],'stale')

    def test_a_new_extraction_invalidates_pending_questions(self):
        self.record();write(self.root/'etapes/01.json',{'data':{'documents':[]}})
        self.assertFalse(self.reviews.pending());self.assertEqual(self.reviews.data()['items'][0]['status'],'stale')

    def test_one_refusal_keeps_other_valid_passages_and_blocks_incomplete_stage(self):
        class RejectOne(Replies):
            def ask(inner,task,payload,*args,**kwargs):
                if task=='writing_check' and payload['expected_statement']==self.ideas[0]['statement']:
                    # Les deux idées sont distinguées pour ce test.
                    if 'premier' in payload['expected_explanation']:return {'status':'uncertain','reason':'La réserve est absente.'}
                return super().ask(task,payload,*args,**kwargs)
        self.ideas[0]['explanation']='Le premier seuil doit garder ses conditions.'
        self.ideas[0]['source_hash']=editorial.source_hash(self.ideas[0]);write(self.root/'etapes/02.json',{'data':self.data})
        with self.assertRaises(ReviewRequired):Pipeline(self.root,RejectOne()).run(3,3)
        self.assertEqual(len(self.reviews.pending()),1)
        self.assertFalse((self.root/'etapes/03.json').exists())
        good=self.root/'etapes/parties/03-Synthese-PDF1-P1-I002.json'
        self.assertTrue(good.exists());before=good.read_bytes()
        self.app.resolve_review(self.root,self.correction(self.reviews.pending()[0]))
        Pipeline(self.root,Replies()).run(3,3)
        self.assertEqual(good.read_bytes(),before);self.assertFalse(self.reviews.pending())

    def test_manual_correction_reuses_source_everywhere_and_keeps_voices_and_other_units(self):
        Pipeline(self.root,Replies()).run(3,3)
        good=self.root/'etapes/parties/03-Synthese-PDF1-P1-I002.json';before=good.read_bytes()
        meta=read(self.root/'projet.json');meta['audio_settings']={'voices':{'Sophie':'local-test-reference'}};write(self.root/'projet.json',meta)
        item=self.record();answer=self.app.resolve_review(self.root,self.correction(item))
        self.assertEqual(answer['resume_from'],3);self.assertFalse((self.root/'etapes/03.json').exists())
        self.assertEqual(good.read_bytes(),before)
        fixed=read(self.root/'etapes/02.json')['data']['documents'][0]['parts'][0]['ideas']
        idea=next(i for i in fixed if i['id']==self.ideas[0]['id'])
        self.assertEqual(idea['statement'],'Les motifs retenus dépendent du seuil choisi.')
        self.assertEqual(idea['source_hash'],editorial.source_hash(idea));self.assertIn('human_review',idea)
        self.assertEqual(read(self.root/'projet.json')['audio_settings'],meta['audio_settings'])
        # Relire une partie d’avant la correction n’écrase pas la décision humaine.
        old=apply_corrections(self.root,copy.deepcopy(self.data))
        self.assertEqual(next(i for i in old['documents'][0]['parts'][0]['ideas'] if i['id']==idea['id'])['statement'],idea['statement'])

    def test_invented_quote_or_page_cannot_be_manually_confirmed(self):
        item=self.record()
        for proof in ([{'page':2,'quote':QUOTE}],[{'page':1,'quote':'This invented quotation is absent from the supplied PDF page.'}]):
            with self.subTest(proof=proof),self.assertRaises(ValueError):self.app.resolve_review(self.root,self.correction(item,evidence=proof))
        self.assertEqual(len(self.reviews.pending()),1);self.assertFalse((self.root/'corrections.json').exists())

    def test_exclusion_stays_in_the_source_report_with_a_reason(self):
        item=self.record()
        with self.assertRaises(ValueError):self.app.resolve_review(self.root,{'id':item['id'],'action':'exclude'})
        self.app.resolve_review(self.root,{'id':item['id'],'action':'exclude','note':'La preuve ne confirme pas cette idée.'})
        part=read(self.root/'etapes/02.json')['data']['documents'][0]['parts'][0]
        self.assertEqual([i['id'] for i in part['ideas']],['PDF1-P1-I002'])
        self.assertTrue(part['excluded_ideas'][0]['human_excluded']);self.assertFalse(self.reviews.pending())

    def test_retry_reopens_the_failed_stage_without_deleting_good_units(self):
        Pipeline(self.root,Replies()).run(3,3)
        good=self.root/'etapes/parties/03-Synthese-PDF1-P1-I002.json';before=good.read_bytes()
        item=self.record();self.app.resolve_review(self.root,{'id':item['id'],'action':'retry'})
        self.assertEqual(self.app.summary(self.root)['next_step'],3);self.assertEqual(good.read_bytes(),before)

    def test_pending_reviews_prevent_skipping_straight_to_export(self):
        self.record()
        with self.assertRaisesRegex(ValueError,'vérifications regroupées'):self.app.enqueue(self.root,{'first':3,'until':9})
        with self.assertRaisesRegex(ValueError,'vérifications des sources'):self.app.enqueue_audio(self.root,{'action':'generate'})

    def test_stale_correction_is_not_applied_to_a_different_pdf(self):
        self.app.resolve_review(self.root,self.correction(self.record()))
        write(self.root/'etapes/01.json',{'data':{'documents':[]}})
        result=apply_corrections(self.root,copy.deepcopy(self.data))
        self.assertEqual(result['documents'][0]['parts'][0]['ideas'][0]['statement'],self.ideas[0]['statement'])

    def test_render_error_before_commit_preserves_the_source_and_decision(self):
        item=self.record();before=(self.root/'etapes/02.json').read_bytes()
        with patch('pipeline.part_markdown',side_effect=ValueError('Erreur de rendu simulée.')):
            with self.assertRaises(ValueError):self.app.resolve_review(self.root,self.correction(item))
        self.assertEqual((self.root/'etapes/02.json').read_bytes(),before)
        self.assertFalse((self.root/'corrections.json').exists());self.assertEqual(len(self.reviews.pending()),1)

    def test_a_human_exclusion_can_be_reopened_and_corrected(self):
        item=self.record()
        self.app.resolve_review(self.root,{'id':item['id'],'action':'exclude','note':'Appui initialement incertain.'})
        reopened=self.app.flag_source(self.root,{'id':self.ideas[0]['id']})
        self.app.resolve_review(self.root,self.correction(reopened))
        part=read(self.root/'etapes/02.json')['data']['documents'][0]['parts'][0]
        value=next(i for i in part['ideas'] if i['id']==self.ideas[0]['id'])
        self.assertNotIn('human_excluded',value);self.assertIn('human_review',value)

    def test_download_consent_is_checked_before_queueing_an_audio_job(self):
        with patch('audio_export.encoder',side_effect=ValueError('absent')):
            with self.assertRaises(DownloadConsentRequired):self.app.enqueue_audio(self.root,{'action':'prepare'})
        self.assertFalse((self.root/'tache.json').exists())

    def test_retained_idea_can_be_put_back_in_human_review(self):
        item=self.app.flag_source(self.root,{'id':self.ideas[0]['id']})
        self.assertEqual(item['idea_id'],self.ideas[0]['id'])
        self.assertEqual(len(self.app.summary(self.root)['reviews']),1)
        self.assertEqual(self.app.summary(self.root)['task']['state'],'needs_review')

    def test_failed_extraction_is_retried_without_reusing_an_incomplete_part(self):
        fail=[True]
        class FailFirst(FakeClient):
            def ask(inner,task,payload,*args,**kwargs):
                if task=='part_summary' and fail[0]:
                    fail[0]=False;raise InvalidResponseError('Extraction non exploitable.')
                return super().ask(task,payload,*args,**kwargs)
        self.app.client_factory=FailFirst
        self.app.enqueue(self.root,{'first':1,'until':2});self.app.pending.join()
        self.assertEqual(self.app.summary(self.root)['task']['state'],'needs_review')
        failed=self.reviews.pending()[0];self.assertTrue(failed['source']['unextracted'])
        before={p:p.read_bytes() for p in (self.root/'etapes/parties').glob('02-PDF1-P[23].*')}
        self.assertTrue(before)
        self.app.resolve_review(self.root,{'id':failed['id'],'action':'retry'})
        self.app.enqueue(self.root,{'first':2,'until':2});self.app.pending.join()
        self.assertEqual(self.app.summary(self.root)['task']['state'],'done')
        self.assertFalse(self.reviews.pending())
        parts=read(self.root/'etapes/02.json')['data']['documents'][0]['parts']
        self.assertTrue(parts[0]['ideas']);self.assertFalse(parts[0]['incomplete_extraction'])
        self.assertTrue(all(p.read_bytes()==raw for p,raw in before.items()))

    def test_uncertain_source_retry_does_not_replay_the_cached_refusal(self):
        fail=[True];calls=[]
        class UncertainOnce(FakeClient):
            def ask(inner,task,payload,*args,**kwargs):
                value=super().ask(task,payload,*args,**kwargs)
                if task=='review_facts':
                    calls.extend(i['id'] for i in payload['candidates'])
                    if fail[0]:
                        fail[0]=False;identity=payload['candidates'][0]['id']
                        value['decisions'][identity]={'status':'uncertain','reason':'Appui incertain pour ce passage.'}
                return value
        self.app.client_factory=UncertainOnce
        self.app.enqueue(self.root,{'first':1,'until':2});self.app.pending.join()
        item=self.reviews.pending()[0];count=calls.count(item['idea_id'])
        before={p:p.read_bytes() for p in (self.root/'etapes/parties').glob('02-PDF1-P[23].*')}
        self.app.resolve_review(self.root,{'id':item['id'],'action':'retry'})
        self.app.enqueue(self.root,{'first':2,'until':2});self.app.pending.join()
        self.assertEqual(self.app.summary(self.root)['task']['state'],'done')
        self.assertGreater(calls.count(item['idea_id']),count)
        self.assertFalse(self.reviews.pending())
        self.assertTrue(all(p.read_bytes()==raw for p,raw in before.items()))


if __name__=='__main__':unittest.main()
