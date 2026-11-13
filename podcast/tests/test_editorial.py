"""Régressions sémantiques de l'audit et dialogue à réponses immuables."""
import copy
from pathlib import Path
import tempfile
import unittest
import editorial,quality
from app import App
from fixtures import FakeClient
from llm import ModelError
from pipeline import Pipeline
from storage import defaults,read,write

def facts(count=6,role='concept'):
    result=[]
    for n in range(count):
        value={'id':f'PDF1-P1-I{83+n:03}','statement':f'Le phénomène {n} dépend de sa condition propre.',
            'explanation':f'La condition particulière {n} doit être précisée pour éviter les généralisations.',
            'document':'PDF1','pages':[n+1],'evidence':[],'role':role,'importance':'essential'}
        value['source_hash']=editorial.source_hash(value);result.append(value)
    return result

class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)
        write(self.project/'projet.json',{'settings':defaults(),'pdfs':[]})
    def tearDown(self):self.temp.cleanup()
    def prepare(self,ideas,glossary=None):
        value={'workflow_version':editorial.VERSION,'ideas':copy.deepcopy(ideas),'groups':[],
            'documents':[{'id':'PDF1','name':'Essai.pdf','glossary':glossary or {}}],
            'source_uncertainties':[],'classification_warnings':[]}
        for i in value['ideas']:i['source_hash']=editorial.source_hash(i)
        write(self.project/'etapes/04.json',{'data':value});return value
    def generate(self,client=None,until=9):
        Pipeline(self.project,client or FakeClient()).run(5,until)
    def test_ook_reference_can_never_be_shifted_to_amplification(self):
        ideas=facts(2)
        ideas[0]['statement']='La modulation OOK utilise la présence ou l’absence de lumière.'
        ideas[0]['explanation']='La présence et l’absence de lumière représentent les deux valeurs binaires.'
        ideas[1]['id']='PDF1-P1-I100'
        ideas[1]['statement']='Un amplificateur renforce la puissance du signal.'
        ideas[1]['explanation']='Le signal reçoit une amplification dans le dispositif.'
        self.prepare(ideas)
        class Swap(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if task in ('key_sentences','common_paragraphs','explanation_paragraphs'):
                    raise AssertionError('Le modèle ne doit plus réécrire ces faits.')
                return super().ask(task,payload,*args,**kwargs)
        self.generate(Swap())
        for stage in (6,7):
            entries={i['idea_id']:i for c in read(self.project/'etapes'/f'{stage:02}.json')['data']['chapters'] for i in c['items']}
            self.assertIn('OOK',entries[ideas[0]['id']].get('sentence',entries[ideas[0]['id']].get('text','')))
            self.assertNotIn('amplificateur',entries[ideas[0]['id']].get('sentence',entries[ideas[0]['id']].get('text','')))
        output=read(self.project/'exports/podcast.json')
        turns=[t for c in output['chapters'] for t in c['turns'] if t.get('kind')=='source']
        self.assertEqual({t['idea_ids'][0]:t['text'] for t in turns},{i['id']:editorial.passage(i) for i in ideas})
    def test_modified_sentence_with_same_id_and_hash_is_rejected(self):
        self.prepare(facts(2));self.generate(until=6)
        value=read(self.project/'etapes/06.json')
        value['data']['chapters'][0]['items'][0]['sentence']='Une autre idée a été insérée.'
        write(self.project/'etapes/06.json',value)
        with self.assertRaisesRegex(ValueError,'Phrase associée'):Pipeline(self.project,FakeClient()).run(7,7)
    def test_modified_explanation_with_same_id_and_hash_is_rejected(self):
        self.prepare(facts(2));self.generate(until=7)
        value=read(self.project/'etapes/07.json');value['data']['chapters'][0]['items'][0]['text']='Interprétation étrangère.'
        write(self.project/'etapes/07.json',value)
        with self.assertRaisesRegex(ValueError,'désolidarisée'):Pipeline(self.project,FakeClient()).run(8,8)
    def test_model_cannot_insert_answers_or_fictional_ids(self):
        self.prepare(facts(2))
        class Poison(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task!='dialogue':return super().ask(task,payload,instructions,validate,budget)
                value={'questions':{i['ref']:'Peux-tu expliquer ce point ?' for i in payload['ideas']},
                       'turns':[{'text':'Garantie inventée à 100 %.','idea_ids':['PDF9-P9-I999']}]}
                validate(value);return value
        self.generate(Poison());result=read(self.project/'exports/podcast.json')
        self.assertNotIn('Garantie inventée',result['plain_text']);self.assertNotIn('PDF9-P9-I999',str(result))
        self.assertTrue(result['all_planned_ids_present'])
    def test_missing_questions_are_repaired_locally_without_losing_answers(self):
        self.prepare(facts(2))
        class Missing(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task!='dialogue':return super().ask(task,payload,instructions,validate,budget)
                self.calls.append((task,copy.deepcopy(payload)))
                entries=payload['ideas']
                value={'questions':{entries[1]['ref']:'Peux-tu expliquer ce point ?'}} if len(entries)>1 else {'questions':{}}
                validate(value);return value
        client=Missing();self.generate(client)
        calls=[p for t,p in client.calls if t=='dialogue']
        self.assertEqual(len(calls),2);self.assertEqual(len(calls[1]['ideas']),1)
        self.assertEqual(calls[1]['ideas'][0]['ref'],calls[0]['ideas'][0]['ref'])
        result=read(self.project/'exports/podcast.json')
        self.assertTrue(result['all_planned_ids_present']);self.assertTrue(any('secours' in w for w in result['generation_warnings']))
    def test_swapped_device_question_is_not_used_for_the_ook_answer(self):
        ideas=facts(2)
        ideas[0].update(statement='La modulation OOK représente les valeurs binaires.',explanation='La présence de lumière représente une valeur.')
        ideas[1].update(statement='Un EDFA amplifie un signal optique.',explanation='Le dispositif renforce ce signal.')
        self.prepare(ideas)
        class Swapped(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task!='dialogue':return super().ask(task,payload,instructions,validate,budget)
                value={'questions':{i['ref']:'Quel rôle joue l’EDFA ?' for i in payload['ideas']}}
                validate(value);return value
        self.generate(Swapped());output=read(self.project/'exports/podcast.json')
        turns=output['chapters'][0]['turns']
        position=next(n for n,t in enumerate(turns) if t.get('idea_ids')==[ideas[0]['id']])
        self.assertNotIn('EDFA',turns[position-1]['text']);self.assertIn('OOK',turns[position]['text'])
    def test_each_dialogue_block_is_resumable_after_a_network_failure(self):
        self.prepare(facts(6));self.generate(until=7)
        class Interrupted(FakeClient):
            def ask(self,task,payload,*args,**kwargs):
                if task=='dialogue':
                    self.count+=1
                    if self.count==2:raise ModelError('HTTP 500')
                return super().ask(task,payload,*args,**kwargs)
        first=Interrupted();first.count=0
        with self.assertRaisesRegex(ModelError,'Étape 8/9.*500'):Pipeline(self.project,first).run(8,8)
        path=self.project/'etapes/parties/08-C1-B1.md';before=path.read_bytes()
        refs={i['ref'] for t,p in first.calls if t=='dialogue' for i in p['ideas']}
        second=FakeClient();Pipeline(self.project,second).run(8,9)
        self.assertEqual(path.read_bytes(),before)
        self.assertFalse(refs & {i['ref'] for t,p in second.calls if t=='dialogue' for i in p['ideas']})
    def test_modified_dialogue_answer_is_rejected_even_with_its_original_hash(self):
        self.prepare(facts(2));self.generate(until=8)
        value=read(self.project/'etapes/08.json')
        turn=next(t for c in value['data']['chapters'] for t in c['turns'] if t.get('kind')=='source')
        turn['text']='Un résultat scientifique entièrement différent.'
        write(self.project/'etapes/08.json',value)
        with self.assertRaisesRegex(ValueError,'modifie une idée source'):Pipeline(self.project,FakeClient()).run(9,9)
    def test_missing_source_turn_still_triggers_the_original_coverage_guard(self):
        self.prepare(facts(2));self.generate(until=8)
        value=read(self.project/'etapes/08.json');chapter=value['data']['chapters'][0]
        removed=False;turns=[]
        for turn in chapter['turns']:
            if turn.get('kind')=='source' and not removed:removed=True;continue
            turns.append(turn)
        chapter['turns']=turns;write(self.project/'etapes/08.json',value)
        with self.assertRaisesRegex(ValueError,'toutes les idées'):Pipeline(self.project,FakeClient()).run(9,9)
    def test_source_mutation_requires_a_new_plan(self):
        self.prepare(facts(2));self.generate(until=5)
        value=read(self.project/'etapes/04.json');value['data']['ideas'][0]['statement']='Une autre source.'
        write(self.project/'etapes/04.json',value)
        with self.assertRaisesRegex(ValueError,'source a changé'):Pipeline(self.project,FakeClient()).run(6,6)
    def test_mw_and_MW_have_different_source_hashes(self):
        a=facts(1)[0];b=copy.deepcopy(a);a['statement']='Une puissance de 1 mW est utilisée.';b['statement']='Une puissance de 1 MW est utilisée.'
        self.assertNotEqual(editorial.source_hash(a),editorial.source_hash(b))
    def test_glossary_is_defined_once_even_inside_a_shared_block(self):
        ideas=facts(4)
        for n,i in enumerate(ideas):i.update(statement=f'Le SNR est observé dans la condition {n}.',explanation='La mesure conserve cette condition.')
        self.prepare(ideas,{'SNR':[{'definition':'Signal-to-noise ratio','page':1}]});self.generate()
        result=read(self.project/'exports/podcast.json')
        definitions=[t for c in result['chapters'] for t in c['turns'] if t.get('kind')=='definition']
        self.assertEqual(len(definitions),1);self.assertIn('rapport signal sur bruit',definitions[0]['text'])
    def test_changed_glossary_requires_replanning(self):
        self.prepare(facts(2));self.generate(until=5)
        value=read(self.project/'etapes/04.json');value['data']['documents'][0]['glossary']={'SNR':[{'definition':'Signal-to-noise ratio','page':1}]}
        write(self.project/'etapes/04.json',value)
        with self.assertRaisesRegex(ValueError,'lexique source a changé'):Pipeline(self.project,FakeClient()).run(6,6)
    def test_changed_definition_cannot_pass_the_final_review(self):
        ideas=facts(1);ideas[0]['statement']='Le SNR est un indicateur de transmission.'
        self.prepare(ideas,{'SNR':[{'definition':'Signal-to-noise ratio','page':1}]});self.generate(until=8)
        value=read(self.project/'etapes/08.json')
        turn=next(t for c in value['data']['chapters'] for t in c['turns'] if t.get('kind')=='definition')
        turn['text']='Une définition inventée.'
        write(self.project/'etapes/08.json',value)
        with self.assertRaisesRegex(ValueError,'Définition différente'):Pipeline(self.project,FakeClient()).run(9,9)
    def test_word_count_excludes_speaker_labels(self):
        self.prepare(facts(2));self.generate()
        result=read(self.project/'exports/podcast.json')
        count=sum(len(c['opening_transition'].split())+sum(len(t['text'].split()) for t in c['turns']) for c in result['chapters'])
        self.assertEqual(result['word_count'],count)
        self.assertLess(count,len(result['plain_text'].split()))
    def test_questions_cannot_introduce_a_document_id_or_universal_promise(self):
        idea=facts(1)[0]
        idea['statement']='Le document PDF1 décrit une méthode mesurée dans une expérience.'
        for question in ('Que présente PDF1 ?', 'Pourquoi la méthode est-elle toujours fiable ?', 'Pourquoi la méthode garantit-elle ce résultat ?'):
            with self.subTest(question=question):self.assertFalse(editorial.valid_question(question,idea,[]))
    def test_a_question_number_must_match_a_complete_source_number(self):
        idea=facts(1)[0];idea['statement']='La puissance mesurée vaut 20 mW.'
        self.assertFalse(editorial.valid_question('Pourquoi mesure-t-on 2 mW ?',idea,[]))
    def test_an_unrelated_question_is_not_accepted(self):
        idea=facts(1)[0];idea['statement']='Une modulation représente les valeurs binaires.'
        self.assertFalse(editorial.valid_question('Quelle est la capitale de France ?',idea,[]))
        self.assertTrue(editorial.valid_question('Comment fonctionne cette modulation ?',idea,[]))
        self.assertTrue(editorial.valid_question('Peux-tu expliquer cette notion simplement ?',idea,[]))
    def test_a_question_cannot_change_the_unit_of_a_source_measurement(self):
        idea=facts(1)[0];idea['statement']='La puissance mesurée vaut 20 mW.'
        self.assertFalse(editorial.valid_question('Pourquoi mesure-t-on une puissance de 20 MW ?',idea,[]))
        self.assertTrue(editorial.valid_question('Pourquoi mesure-t-on une puissance de 20 mW ?',idea,[]))
    def test_identical_questions_are_varied_without_changing_the_answers(self):
        self.prepare(facts(6));self.generate()
        result=read(self.project/'exports/podcast.json')
        questions=[quality.definition_key(t['text']) for c in result['chapters'] for t in c['turns'] if t.get('kind')=='question']
        self.assertTrue(all(a!=b for a,b in zip(questions,questions[1:])))
        self.assertTrue(result['source_texts_preserved'])
    def test_metadata_classification_cannot_rewrite_source_sentences(self):
        source=facts(2)
        class Poison(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                value={'roles':{i['ref']:{'role':'concept','importance':'essential','reason':'Test.',
                    'statement':'Un fait étranger.'} for i in payload['ideas']}}
                validate(value);return value
        annotated,_=editorial.annotated(Pipeline(self.project,Poison()),source)
        self.assertEqual([i['statement'] for i in annotated],[i['statement'] for i in source])
    def test_document_location_and_template_text_do_not_enter_the_dialogue(self):
        ideas=facts(3)
        ideas[0]['statement']='L’extrait provient de la page 125 du document.'
        ideas[1]['explanation']='Le signal reçoit une amplification. (source_text)'
        self.prepare(ideas);self.generate()
        result=read(self.project/'exports/podcast.json')
        self.assertEqual(result['selected_count'],1)
        self.assertNotIn('source_text',result['plain_text']);self.assertNotIn('page 125',result['plain_text'])
        self.assertEqual(len(result['excluded_ideas']),2)

class SourceGuardTests(unittest.TestCase):
    def fact(self,statement,explanation,quote):
        return {'id':'PDF1-P1-I001','statement':statement,'explanation':explanation,'evidence':[quote],'status':'kept','reason':'Test.'}
    def validate(self,fact,terms=None):
        quality.validate_review({'kept':[fact],'excluded':[]},[fact],' '.join(fact['evidence']),terms)
    def test_wss_citation_cannot_be_promoted_as_oms(self):
        quote='The WSS devices minimize insertion loss and maximize isolation between wavelengths.'
        wrong=self.fact('Les OMS réduisent les pertes d’insertion.','Le dispositif limite les pertes dans ce cas.',quote)
        with self.assertRaisesRegex(ValueError,'sujet OMS'):self.validate(wrong)
        wrong['statement']='Les WSS réduisent les pertes d’insertion.';self.validate(wrong)
    def test_adding_an_oms_paragraph_does_not_transfer_a_wss_property(self):
        quote='The WSS devices minimize insertion loss and maximize isolation. An OMS manages several wavelengths over a fibre.'
        wrong=self.fact('Les OMS réduisent les pertes d’insertion.','Le dispositif réduit ces pertes dans le réseau.',quote)
        with self.assertRaisesRegex(ValueError,'propriété citée'):self.validate(wrong)
        wrong['statement']='Les WSS réduisent les pertes d’insertion.';self.validate(wrong)
    def test_plural_symbols_and_french_AI_alias_preserve_the_correct_subject(self):
        quote='The WSSs reduce insertion loss while AI agents help analyze the data.'
        value=self.fact('Les WSS réduisent les pertes.','Les pertes sont limitées par le dispositif.',quote);self.validate(value)
        value=self.fact('Les agents IA analysent les données.','Ces agents sont employés dans ce cas.',quote)
        self.validate(value,{'AI':[{'definition':'Artificial intelligence','page':1}]})
    def test_a_new_numeric_result_or_changed_unit_is_rejected(self):
        quote='The measured optical power is 1 mW in this experiment.'
        for claim in ('La puissance mesurée est de 1 MW.','La puissance mesurée est de 2 mW.'):
            value=self.fact(claim,'La mesure dépend des conditions de cette expérience.',quote)
            with self.subTest(claim=claim),self.assertRaisesRegex(ValueError,'Valeur et unité'):self.validate(value)
    def test_a_test_accuracy_is_not_a_universal_guarantee(self):
        quote='The model achieves 100% accuracy in this API test.'
        value=self.fact('Le modèle est précis à 100%.','La méthode garantit cette précision.',quote)
        with self.assertRaisesRegex(ValueError,'périmètre'):self.validate(value)
        value['statement']='Dans ce test, le modèle atteint une précision de 100%.'
        value['explanation']='La mesure concerne les API testées dans cette expérience.'
        self.validate(value)
    def test_localization_and_prompt_placeholders_require_source_repair(self):
        quote='The signal is amplified before transmission through the optical fibre.'
        for statement in ('L’extrait provient de la page 125 du document.',
                          'Le signal est amplifié avant la transmission. (source_text)'):
            with self.subTest(statement=statement),self.assertRaisesRegex(ValueError,'localisation'):
                self.validate(self.fact(statement,'Le dispositif renforce le signal transmis.',quote))
    def test_short_english_statements_are_not_validated_as_french(self):
        for text in ('Per-span power spectra are typically unavailable in commercial networks',
                     'A refinement technique is used to estimate missing information'):
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'français'):quality.french_text(text)
        quality.french_text('La puissance du signal dépend de la distance parcourue dans la fibre.')
    def test_a_source_fact_cannot_start_with_an_unresolved_cela(self):
        self.assertTrue(quality.ambiguous_subject('Cela permet une transmission fiable sur de longues distances.'))
        quote='The optical amplifier compensates for signal attenuation along the fibre.'
        with self.assertRaisesRegex(ValueError,'ambigu'):
            self.validate(self.fact('Cela permet une transmission fiable sur de longues distances.',
                                    'Le dispositif compense une partie des pertes.',quote))

class MigrationTests(unittest.TestCase):
    def test_old_project_requires_review_and_keeps_old_files_until_user_rebuilds(self):
        with tempfile.TemporaryDirectory() as directory:
            app=App(Path(directory),FakeClient)
            try:
                identity=app.create({'name':'Ancien projet','settings':defaults()})['id'];project=app.project(identity)
                meta=read(project/'projet.json');meta['pdfs']=[{'file':'source.pdf','name':'source.pdf'}];write(project/'projet.json',meta)
                write(project/'etapes/02.json',{'data':{'quality_version':'source-review-v2','documents':[]}})
                for n in range(3,8):write(project/'etapes'/f'{n:02}.json',{'data':{}})
                (project/'exports').mkdir();(project/'exports/podcast.txt').write_text('Ancien script conservé.')
                state=app.summary(project);self.assertTrue(state['needs_source_upgrade']);self.assertFalse(state['exports'])
                with self.assertRaisesRegex(ValueError,'anciens contrôles'):app.enqueue(project,{'first':8,'until':9})
                self.assertEqual((project/'exports/podcast.txt').read_text(),'Ancien script conservé.')
            finally:app.close()

if __name__=='__main__':unittest.main()
