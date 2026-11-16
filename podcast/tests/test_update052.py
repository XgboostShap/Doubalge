"""Reprise d'une rédaction trop longue sans couper ses réserves ni ses sources."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from fixtures import FakeClient,StubServer
from llm import Cancelled,InvalidResponseError,ModelError,Ollama
from pipeline import Pipeline
from storage import defaults,read,write
import editorial,quality,writing


SHORT='La puissance du signal diminue dans la fibre. Une amplification peut compenser une partie des pertes, sans les supprimer.'
LONG=('Les pertes réduisent la puissance disponible au cours de la propagation. '*8+
      'Une amplification peut compenser une partie des pertes, sans les supprimer.')
HUGE=('Les pertes réduisent la puissance disponible au cours de la propagation. '*40+
      'Une amplification peut compenser une partie des pertes, sans les supprimer.')


class Drafts(FakeClient):
    def __init__(self,drafts,verdict='supported'):
        super().__init__();self.drafts=iter(drafts);self.verdict=verdict
    def ask(self,task,payload,instructions,validate,budget=4000):
        if task=='grounded_text':
            self.calls.append((task,copy.deepcopy(payload)))
            result=next(self.drafts)
            if isinstance(result,Exception):raise result
            value=result if isinstance(result,dict) else {'text':result}
            validate(value);return value
        if task=='writing_check' and self.verdict!='supported':
            self.calls.append((task,copy.deepcopy(payload)))
            return {'status':self.verdict,'reason':'La restriction de la source manque dans la reformulation.'}
        return super().ask(task,payload,instructions,validate,budget)


class ConcisionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.project=self.root
        write(self.root/'projet.json',{'settings':defaults(),'pdfs':[]})
        self.idea={'id':'PDF1-P1-I001','statement':'Le signal perd de la puissance dans la fibre.',
            'explanation':'Une amplification ne compense qu’une partie des pertes.',
            'document':'PDF1','pages':[1],'role':'concept','importance':'essential',
            'evidence':[{'page':1,'quote':'The signal loses power in the fibre. Amplification can compensate part of the losses, without removing them.'}]}
        self.idea['source_hash']=editorial.source_hash(self.idea)
    def tearDown(self):self.temp.cleanup()
    def rewrite(self,client,**kwargs):return writing.rewrite(Pipeline(self.root,client),3,'Synthese-'+self.idea['id'],self.idea,{},**kwargs)
    def prepare(self):
        data={'quality_version':quality.VERSION,'documents':[{'id':'PDF1','name':'Essai.pdf','glossary':{},
            'parts':[{'number':1,'ideas':[self.idea],'excluded_ideas':[]}]}]}
        write(self.root/'etapes/02.json',{'data':data})

    def test_length_diagnostic_distinguishes_missing_text_and_measured_overflow(self):
        with self.assertRaisesRegex(writing.TextShapeError,'champ text.*PDF1-P1-I001'):
            writing.validate_text(None,self.idea,{})
        with self.assertRaisesRegex(writing.WordCountError,str(len(LONG.split()))+' mots reçus'):
            writing.validate_text(LONG,self.idea,{},85)
        with self.assertRaisesRegex(writing.WordCountError,'1 mots'):
            writing.validate_text('Oui.',self.idea,{})

    def test_shortening_receives_the_whole_draft_and_preserves_the_final_reservation(self):
        client=Drafts([LONG,SHORT]);result=self.rewrite(client)
        attempts=[p for t,p in client.calls if t=='grounded_text']
        self.assertEqual(attempts[1]['draft'],LONG)
        self.assertEqual(attempts[1]['previous_word_count'],len(LONG.split()))
        self.assertEqual(attempts[0]['source'],attempts[1]['source'])
        self.assertEqual(result['text'],SHORT);self.assertIn('sans les supprimer',result['text'])
        self.assertEqual(result['word_count'],len(SHORT.split()));self.assertTrue(result['length_adjusted'])
        self.assertEqual(result['warnings'],[])
        checked=next(p for t,p in client.calls if t=='writing_check')
        self.assertEqual(checked['text'],SHORT)

    def test_moderate_overflow_can_finish_only_with_review_and_visible_editorial_note(self):
        self.prepare();before=(self.root/'etapes/02.json').read_bytes()
        client=Drafts([LONG,LONG]);Pipeline(self.root,client).run(3,3)
        doc=read(self.root/'etapes/03.json')['data']['documents'][0]
        self.assertIn(LONG,doc['synthesis']);self.assertTrue(doc['synthesis_warnings'])
        self.assertIn('Notes éditoriales',(self.root/'etapes/03.md').read_text())
        self.assertEqual((self.root/'etapes/02.json').read_bytes(),before)
        self.assertTrue(any(t=='writing_check' for t,_ in client.calls))
        self.assertIn('sans les supprimer',doc['synthesis'])

    def test_a_shortening_with_an_invented_measurement_is_never_used(self):
        client=Drafts([LONG,'Le signal garde une puissance de 900 MW dans cette fibre.'])
        result=self.rewrite(client)
        self.assertEqual(result['text'],LONG);self.assertNotIn('900',result['text'])
        self.assertTrue(result['warnings']);self.assertTrue(result['length_repair_issue'])
        self.assertEqual(next(p for t,p in client.calls if t=='writing_check')['text'],LONG)

    def test_a_factually_rejected_long_text_does_not_become_a_finished_part(self):
        client=Drafts([LONG,LONG,LONG,LONG],verdict='uncertain')
        with self.assertRaises(InvalidResponseError):self.rewrite(client)
        self.assertFalse(list((self.root/'etapes/parties').glob('*.json')))

    def test_a_huge_draft_is_omitted_whole_and_the_complete_source_is_kept(self):
        client=Drafts([HUGE,SHORT]);result=self.rewrite(client)
        attempts=[p for t,p in client.calls if t=='grounded_text']
        self.assertEqual(attempts[1]['mode'],'restart');self.assertTrue(attempts[1]['draft_omitted'])
        self.assertNotIn('draft',attempts[1]);self.assertEqual(attempts[0]['source'],attempts[1]['source'])
        self.assertEqual(result['text'],SHORT)

    def test_missing_or_one_word_responses_are_restarted_from_the_source(self):
        for invalid in ({'other':'Le mauvais champ contient du texte.'},'Oui.'):
            with self.subTest(invalid=invalid),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);write(root/'projet.json',{'settings':defaults(),'pdfs':[]})
                client=Drafts([invalid,SHORT]);result=writing.rewrite(Pipeline(root,client),3,'Unique',self.idea,{})
                self.assertEqual(result['text'],SHORT)
                self.assertEqual([p for t,p in client.calls if t=='grounded_text'][1]['mode'],'restart')

    def test_a_second_huge_response_stops_with_the_id_and_actual_count(self):
        client=Drafts([HUGE,HUGE])
        with self.assertRaisesRegex(InvalidResponseError,'PDF1-P1-I001.*'+str(len(HUGE.split()))+' mots'):
            self.rewrite(client)
        self.assertEqual(len(client.calls),2)
        self.assertFalse(list((self.root/'etapes/parties').glob('*.json')))

    def test_network_error_or_cancel_during_shortening_is_not_swallowed(self):
        for failure in (ModelError('Connexion interrompue'),Cancelled()):
            with self.subTest(error=type(failure).__name__):
                with self.assertRaises(type(failure)):self.rewrite(Drafts([LONG,failure]))
                self.assertFalse(list((self.root/'etapes/parties').glob('*.json')))

    def test_a_completed_part_is_not_requested_again_after_an_update(self):
        self.rewrite(Drafts([SHORT]));saved=next((self.root/'etapes/parties').glob('*.json'))
        # Les anciennes parties validées ne portent pas les nouveaux champs éditoriaux.
        value=read(saved)
        for key in ('word_count','preferred_max_words','length_adjusted','length_repair_issue','warnings'):
            value['data'].pop(key,None)
        write(saved,value);before=saved.read_bytes()
        client=Drafts([]);result=self.rewrite(client)
        self.assertEqual(result['text'],SHORT);self.assertEqual(client.calls,[])
        self.assertEqual(saved.read_bytes(),before)

    def test_key_sentences_use_the_same_bounded_repair(self):
        statement=('La puissance du signal diminue lorsque les pertes augmentent dans la fibre. '*3+
                   'Une amplification ne les supprime pas.')
        self.assertGreater(len(statement.split()),35);self.assertLess(len(statement.split()),60)
        result=self.rewrite(Drafts([statement,SHORT]),kind='sentence')
        self.assertLessEqual(result['word_count'],35);self.assertIn('sans les supprimer',result['text'])

    def test_real_http_client_retries_shortening_then_checks_the_saved_text(self):
        with StubServerContext() as stub:
            def event(text):return (200,[{'message':{'content':json.dumps({'text':text})},'done':True,'done_reason':'stop'}])
            stub.responses=[event(LONG),event(LONG),event(SHORT)]
            client=Ollama({**defaults(),'endpoint':stub.endpoint},self.root/'cache')
            result=self.rewrite(client)
            self.assertEqual(result['text'],SHORT)
            self.assertEqual([t for t,_ in stub.calls],['grounded_text','grounded_text','grounded_text','writing_check'])
            self.assertEqual(stub.calls[1][1]['draft'],LONG)
            self.assertIn(str(len(LONG.split()))+' mots',stub.requests[2]['messages'][-1]['content'])

    def test_final_response_can_include_definitions_without_reusing_the_old_160_word_stop(self):
        text=LONG+' '+LONG
        self.assertGreater(len(text.split()),160);self.assertLessEqual(len(text.split()),240)
        chapter={'turns':[{'kind':'source','idea_ids':[self.idea['id']],'text':text}]}
        client=FakeClient()
        result,_=writing.final_pass(Pipeline(self.root,client),[chapter],{self.idea['id']:self.idea},
            {'documents':[{'id':'PDF1','glossary':{}}]})
        turn=result[0]['turns'][0]
        self.assertEqual(turn['text'],text);self.assertTrue(turn['length_warning'])
        self.assertTrue(next(p for t,p in client.calls if t=='writing_check')['final_review'])

    def test_length_notes_remain_in_the_report_and_never_enter_the_spoken_script(self):
        from test_editorial import EditorialTests
        # Exercer les étapes 5 à 9 avec le même dépassement modéré à l'étape 7.
        EditorialTests.prepare(self,[self.idea])
        class LongExplanations(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='grounded_text':
                    value={'text':SHORT if payload['kind']=='sentence' else LONG}
                    validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        Pipeline(self.root,LongExplanations()).run(5,9)
        output=read(self.root/'exports/podcast.json')
        self.assertTrue(any('cible éditoriale' in w for w in output['generation_warnings']))
        self.assertIn('Points à relire',(self.root/'etapes/09.md').read_text())
        self.assertNotIn('cible éditoriale',output['plain_text'])
        self.assertIn('sans les supprimer',output['plain_text'])


class StubServerContext:
    def __enter__(self):self.stub=StubServer();return self.stub
    def __exit__(self,*args):self.stub.close()


if __name__=='__main__':unittest.main()
