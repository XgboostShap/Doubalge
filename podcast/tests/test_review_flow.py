"""Une longue liste d’incertitudes ne doit pas imposer une régénération des sources."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import App
from fixtures import FakeClient,make_pdf
from issues import SourceIssue
from pipeline import Pipeline
from review_queue import Reviews
from storage import read,write
import review_flow


class DeferredSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=App(self.temp.name,FakeClient)
        self.project=self.app.project(self.app.create({'name':'Quatre-vingt-dix passages à examiner'})['id'])
        make_pdf(self.project/'sources/a.pdf')
        meta=read(self.project/'projet.json');meta['pdfs']=[{'file':'a.pdf','name':'Optique.pdf'}]
        meta['audio_settings']={'voices':{'Sophie':'profil-local-a','Emma':'profil-local-b'}};write(self.project/'projet.json',meta)
        Pipeline(self.project,FakeClient()).run(1,2)
        self.saved=read(self.project/'etapes/02.json');self.part=self.saved['data']['documents'][0]['parts'][0]
        self.store=Reviews(self.project)
        for number in range(90):
            idea={'id':f'PDF1-P1-I{900+number}','statement':f'Passage non confirmé numéro {number}.',
                  'explanation':'La formulation et son appui restent à examiner.','pages':[1],'reason':'À vérifier : formulation non confirmée.'}
            self.part['excluded_ideas'].append(idea);self.part['uncertain_ideas'].append(idea)
            self.store.record(2,'Source-'+idea['id'],{**idea,'document':'PDF1'},SourceIssue(idea['reason']))
        write(self.project/'etapes/02.json',self.saved)
        partial=self.project/'etapes/parties/02-PDF1-P1.json';packet=read(partial);packet['data']=copy.deepcopy(self.part);write(partial,packet)
        self.ids=[i['id'] for i in self.store.pending()]
        self.before={p:p.read_bytes() for p in (self.project/'etapes').glob('0[12].*')}
        self.voices=read(self.project/'projet.json')['audio_settings']
    def tearDown(self):self.app.close();self.temp.cleanup()

    def test_overview_explains_why_stage_three_has_not_started(self):
        state=self.app.summary(self.project)
        self.assertEqual(state['flow']['state'],'needs_review');self.assertEqual(state['flow']['pending'],90)
        self.assertIn('calcul est arrêté',state['flow']['title']);self.assertIn('avant l’étape 3',state['flow']['detail'])
        self.assertTrue(state['flow']['can_continue_retained']);self.assertEqual(set(state['flow']['eligible_ids']),set(self.ids))

    def test_continue_defers_uncertainties_and_queues_stage_three_without_touching_sources(self):
        with patch.object(self.app,'enqueue',return_value={'first':3}) as enqueue:
            result=self.app.defer_reviews(self.project,{'ids':self.ids,'continue':True})
        enqueue.assert_called_once_with(self.project,{'first':3,'until':9})
        self.assertEqual(result['deferred'],90);self.assertFalse(self.store.pending())
        self.assertEqual(len([i for i in self.store.data()['items'] if i['status']=='deferred']),90)
        self.assertTrue(all(p.read_bytes()==raw for p,raw in self.before.items()))
        self.assertEqual(read(self.project/'projet.json')['audio_settings'],self.voices)
        self.assertTrue(all(i['status']!='validated' for i in self.store.data()['items']))

    def test_cached_stage_two_does_not_reopen_the_deferred_questions(self):
        self.app.defer_reviews(self.project,{'ids':self.ids})
        Pipeline(self.project,FakeClient()).run(2,2)
        self.assertFalse(self.store.pending());self.assertEqual(len(self.app.summary(self.project)['deferred_reviews']),90)
        self.assertEqual(len(read(self.project/'etapes/02.json')['data']['documents'][0]['parts'][0]['ideas']),len(self.part['ideas']))

    def test_full_resume_exports_only_retained_ideas_and_keeps_the_deferred_report(self):
        self.app.defer_reviews(self.project,{'ids':self.ids,'continue':True});self.app.pending.join()
        state=self.app.summary(self.project)
        self.assertEqual(state['task']['state'],'done',state['task'])
        final=read(self.project/'exports/podcast.json')
        excluded={i['id'] for i in self.part['uncertain_ideas']}
        self.assertFalse(excluded & set(final['expected_idea_ids']))
        self.assertEqual(len(final['deferred_source_ideas']),90)
        self.assertEqual(len(final['source_uncertainties']),90)
        self.assertTrue(all(p.read_bytes()==raw for p,raw in self.before.items()))
        self.assertEqual(read(self.project/'projet.json')['audio_settings'],self.voices)

    def test_reopening_a_deferred_question_is_explicit_and_keeps_its_history(self):
        self.app.defer_reviews(self.project,{'ids':self.ids})
        self.app.reopen_review(self.project,{'id':self.ids[0]})
        self.assertEqual(len(self.store.pending()),1)
        self.assertEqual(len(self.app.summary(self.project)['deferred_reviews']),89)
        self.assertEqual(self.store.data()['decisions'][-1]['action'],'reopen')

    def test_a_retained_idea_cannot_be_silently_put_aside(self):
        retained=self.part['ideas'][0]
        item=self.app.flag_source(self.project,{'id':retained['id']})
        self.assertFalse(self.app.summary(self.project)['flow']['can_continue_retained'])
        with self.assertRaises(ValueError):self.app.defer_reviews(self.project,{'ids':self.ids+[item['id']],'continue':True})
        self.assertEqual(len(self.store.pending()),91)
        self.assertFalse(any(i['status']=='deferred' for i in self.store.data()['items']))

    def test_stale_selection_does_not_partially_approve_or_defer_anything(self):
        with self.assertRaises(ValueError):self.app.defer_reviews(self.project,{'ids':self.ids[:-1],'continue':True})
        self.assertEqual(len(self.store.pending()),90)
        self.assertFalse(self.store.data()['decisions'])

    def test_an_unread_fragment_cannot_be_hidden_by_the_continue_choice(self):
        self.part['incomplete_extraction']=True;write(self.project/'etapes/02.json',self.saved)
        with self.assertRaises(ValueError):self.app.defer_reviews(self.project,{'ids':self.ids,'continue':True})
        self.assertEqual(len(self.store.pending()),90)

    def test_retry_requested_earlier_is_respected_before_stage_three(self):
        self.app.resolve_review(self.project,{'id':self.ids[0],'action':'retry'})
        with patch.object(self.app,'enqueue',return_value={'first':2}) as enqueue:
            self.app.defer_reviews(self.project,{'ids':self.ids[1:],'continue':True})
        enqueue.assert_called_once_with(self.project,{'first':2,'until':9})

    def test_changed_source_makes_a_deferred_question_stale(self):
        self.app.defer_reviews(self.project,{'ids':self.ids})
        write(self.project/'etapes/01.json',{'data':{'documents':[]}})
        state=self.app.summary(self.project)
        self.assertFalse(state['deferred_reviews'])
        self.assertTrue(all(i['status']=='stale' for i in self.store.data()['items']))

    def test_only_a_newly_retained_idea_clears_its_deferred_status(self):
        self.app.defer_reviews(self.project,{'ids':self.ids})
        key=self.store.data()['items'][0]['key']
        self.store.completed(2,key);self.assertEqual(self.store.data()['items'][0]['status'],'deferred')
        self.store.completed(2,key,include_deferred=True);self.assertEqual(self.store.data()['items'][0]['status'],'validated')


class ProgressClockTests(unittest.TestCase):
    def test_clock_freezes_when_the_program_waits_for_a_decision(self):
        task={'state':'needs_review','started_at':10,'finished_at':25}
        with patch('review_flow.time.time',return_value=36000):
            result=review_flow.overview({},[1,2],task,[{'step':2,'id':'r','idea_id':'I','source':{}}],[])
        self.assertEqual(result['elapsed_seconds'],15)
    def test_running_step_is_visible_even_while_the_model_has_not_saved_a_new_unit(self):
        task={'state':'running','step':3,'started_at':10}
        with patch('review_flow.time.time',return_value=25):result=review_flow.overview({},[1,2],task,[],[])
        self.assertEqual(result['state'],'running');self.assertIn('Étape 3/9',result['title']);self.assertEqual(result['elapsed_seconds'],15)


if __name__=='__main__':unittest.main()
