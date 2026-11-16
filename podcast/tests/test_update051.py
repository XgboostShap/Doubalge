"""Reprise des projets sans idée retenue et preuves sélectionnées par référence."""
import copy
from pathlib import Path
import tempfile
import unittest

from app import App
from fixtures import FakeClient,make_pdf
from llm import ModelError
from pipeline import Pipeline
from storage import defaults,fingerprint,read,write
import quality,source_review,writing

class SourceReferences(unittest.TestCase):
    def test_excerpts_keep_original_characters_and_are_bounded(self):
        raw=('Le signal garde sa casse, 1 mW et 1 MW. Une phrase avec une ligature ﬁ et un mot coupé event- logs. '*60)
        rows=source_review.excerpts(raw)
        self.assertGreater(len(rows),1);self.assertTrue(all(len(r['text'])<=1100 for r in rows))
        self.assertEqual(''.join(''.join(r['text'].split()) for r in rows),''.join(raw.split()))
        for row in rows:self.assertIn(row['text'],raw)
    def test_an_unknown_reference_cannot_become_a_citation(self):
        with self.assertRaises(ValueError):source_review.resolve(['E99'],[{'ref':'E1','text':'This passage describes actual signal propagation.'}])
    def test_refs_resolve_to_the_original_source_and_do_not_translate_it(self):
        raw='Predictive maintenance anticipates failures using patterns in event- logs.'
        value={'decisions':{'I1':{'statement':'La maintenance prédictive anticipe les défaillances.','explanation':'Les codes des journaux signalent des événements avant une panne.','evidence':['E1'],'status':'kept','reason':'Appui.'}}}
        source_review.decisions(value,source_review.excerpts(raw),raw,{})
        self.assertEqual(value['decisions']['I1']['evidence'],[raw])
        self.assertEqual(value['decisions']['I1']['evidence_refs'],['E1'])
        quality.validate_review(value,[{'id':'I1'}],raw,{})
    def test_known_proof_annotations_do_not_cause_rejection_or_change_quotes(self):
        raw='Predictive maintenance anticipates failures using patterns in event logs.'
        value={'decisions':{'I1':{'statement':'La maintenance prédictive anticipe les défaillances (E1).','explanation':'Les codes des journaux signalent des événements avant une panne.','evidence':['E1'],'status':'kept','reason':'Appui.'}}}
        source_review.decisions(value,source_review.excerpts(raw),raw,{})
        fact=value['decisions']['I1']
        self.assertEqual(fact['statement'],'La maintenance prédictive anticipe les défaillances.')
        self.assertEqual(fact['evidence'],[raw]);self.assertTrue(fact['automatic_corrections'])
        quality.validate_review(value,[{'id':'I1'}],raw,{})
    def test_schema_restricts_quotes_to_existing_reference_choices(self):
        payload={'source_excerpts':[{'ref':'E1','text':'A real explanatory source sentence.'}],'candidates':[{'id':'I1'}]}
        schema=quality.response_schema('review_facts',payload)
        self.assertEqual(schema['properties']['decisions']['properties']['I1']['properties']['evidence']['items']['enum'],['E1'])
        with self.assertRaises(ValueError):source_review.support({'status':'supported','reason':'Appui.','statement_refs':['E2'],'explanation_refs':['E1']},{'evidence':['The source describes signal propagation.']})
    def test_inline_definitions_ground_short_article_acronyms(self):
        terms=quality.glossary({1:{'kind':'content','text':'Predictive Maintenance (PM) uses logs. Frequent Itemset Mining (FIM) finds patterns. Dis- criminative Pattern Mining (DPM) compares classes.'}})
        self.assertEqual(terms['PM'][0]['definition'],'Predictive Maintenance')
        self.assertEqual(terms['DPM'][0]['definition'],'Discriminative Pattern Mining')
        self.assertNotIn('XYZ',quality.glossary({1:{'kind':'content','text':'An unrelated title (XYZ) is mentioned.'}}))
        with self.assertRaises(ValueError):quality.validate_acronyms('La prévision minière (PM) est utilisée.',terms)
        quality.validate_acronyms('La maintenance prédictive (PM) anticipe les pannes.',terms)

    def test_predictive_is_not_translated_as_preventive(self):
        source='Predictive maintenance uses event logs to anticipate failures.'
        fact={'statement':'Une méthode pour l’entretien préventif est étudiée.','explanation':'La maintenance préventive utilise des codes.'}
        result=quality.normalize_terminology(fact,source)
        self.assertIn('maintenance prédictive',result['statement']);self.assertIn('maintenance prédictive',result['explanation'])
        observed={'statement':"Un algorithme pour la prédiction de l'entretien préventif est présenté.",'explanation':"Le rôle de l'entretien préventif est présenté."}
        corrected=quality.normalize_terminology(observed,source)
        self.assertEqual(corrected['statement'],'Un algorithme pour la maintenance prédictive est présenté.')
        self.assertEqual(corrected['explanation'],'Le rôle de la maintenance prédictive est présenté.')
        with self.assertRaises(ValueError):quality.validate_technical_wording(fact['statement'],source)
        # Les deux concepts doivent rester distincts dans une comparaison.
        self.assertEqual(quality.normalize_terminology(fact,source+' Preventive maintenance follows a schedule.'),fact)

    def test_dataset_counts_and_names_need_matching_evidence(self):
        source='Three public datasets: ijcnn1, cod-rna, a9a. Doors is an industrial dataset.'
        with self.assertRaisesRegex(ValueError,'nombre de jeux'):
            quality.validate_evidence_details('Trois jeux de données publiques : ijcnn1, cod-rna, a9a et Doors.',source)
        with self.assertRaisesRegex(ValueError,'nombre de jeux'):
            quality.validate_evidence_details('Trois jeux de données publiques couramment utilisés pour le benchmarking : ijcnn1, cod-rna, a9a et Doors.',source)
        with self.assertRaisesRegex(ValueError,'absent des citations'):
            quality.validate_evidence_details('Trois jeux de données publics : ijcnn1, cod-rna et a9a.','The ijcnn1 experiment measures the recall.')
        with self.assertRaisesRegex(ValueError,'caractère public'):
            quality.validate_evidence_details('Quatre jeux de données publics : ijcnn1, cod-rna, a9a et Doors.','Experiments use ijcnn1, cod-rna, a9a and Doors. Doors contains logs provided by the railway company.')
        quality.validate_evidence_details('Trois jeux de données publics : ijcnn1, cod-rna et a9a. Le jeu Doors est industriel.',source)
        quality.validate_evidence_details('Trois jeux de données publics : ijcnn1, cod-rna et a9a.',source.replace('public','pub- lic'))

class SourceFlow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        write(self.root/'projet.json',{'settings':defaults(),'pdfs':[]})
        self.fact={'id':'PDF1-P1-I001','statement':'Le signal perd de la puissance dans la fibre.','explanation':'Les pertes réduisent la puissance disponible.'}
        self.raw='The signal loses power along the optical fibre. Losses reduce available power.'
    def tearDown(self):self.temp.cleanup()
    def test_source_quotes_are_selected_instead_of_requested_as_model_copies(self):
        client=FakeClient();out=Pipeline(self.root,client).review_candidates({'source_page':1,'source_text':self.raw,'candidates':[self.fact],'glossary':{}},[self.fact],self.raw)
        self.assertEqual(len(out['kept']),1)
        prompt=next(p for t,p in client.calls if t=='review_facts')
        self.assertNotIn('source_text',prompt);self.assertEqual(prompt['source_excerpts'][0]['text'],self.raw)
        self.assertEqual(out['kept'][0]['evidence'],[self.raw])
    def test_rephrased_reason_is_not_rejected_when_real_evidence_is_selected(self):
        fact={**self.fact,'evidence':[self.raw],'status':'kept','reason':'Test.'}
        class RepeatReason(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='fact_support':
                    value={'verdicts':{r['ref']:{'status':'supported','reason':r['statement'],'statement_refs':['E1'],'explanation_refs':['E1']} for r in payload['facts']}};validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        out=Pipeline(self.root,RepeatReason()).check_support([fact],1)
        self.assertEqual(len(out['kept']),1);self.assertTrue(out['kept'][0]['support_selection']['source_selection_verified'])
    def test_missing_evidence_is_retried_and_remains_uncertain(self):
        class Missing(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='fact_support':
                    self.calls.append((task,payload));value={'verdicts':{r['ref']:{'status':'supported','reason':'Appui sans preuve.'} for r in payload['facts']}};validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        client=Missing();out=Pipeline(self.root,client).check_support([{**self.fact,'evidence':[self.raw]}],1)
        self.assertFalse(out['kept']);self.assertEqual(len(out['excluded']),1);self.assertEqual(len(client.calls),2)
    def test_writing_review_uses_a_canonical_source_reference(self):
        idea={**self.fact,'evidence':[{'quote':self.raw}]}
        result=writing.check(Pipeline(self.root,FakeClient()),self.fact['statement'],idea,{})
        self.assertEqual(result['quote'],self.raw)
    def test_source_markers_and_ambiguous_exponents_are_not_spoken_as_facts(self):
        idea={**self.fact,'evidence':[{'quote':self.raw}]}
        with self.assertRaises(ValueError):writing.validate_text('Le signal perd de la puissance dans la fibre (E1).',idea,{})
        idea={'statement':'Le modèle est complètement corrélé.','explanation':'La complexité dépend de la dimension.','evidence':[{'quote':'The fully correlated Bernoulli model has 2d parameters.'}]}
        with self.assertRaises(ValueError):writing.validate_text('Le modèle comporte 2d paramètres dans cette situation.',idea,{})
    def test_zero_kept_facts_stop_after_the_saved_diagnostic(self):
        (self.root/'sources').mkdir();make_pdf(self.root/'sources/p.pdf')
        write(self.root/'projet.json',{'settings':defaults(),'pdfs':[{'file':'p.pdf','name':'Extrait.pdf'}]})
        class Reject(FakeClient):
            def ask(self,task,payload,instructions,validate,budget=4000):
                if task=='review_facts':
                    value={'decisions':{i['id']:{'status':'uncertain','reason':'Appui non confirmé.'} for i in payload['candidates']}};validate(value);return value
                return super().ask(task,payload,instructions,validate,budget)
        with self.assertRaisesRegex(ModelError,'Étape 2/9.*Réexaminer'):Pipeline(self.root,Reject()).run(1,9)
        self.assertTrue((self.root/'etapes/02.json').exists());self.assertTrue((self.root/'etapes/02.md').exists())
        self.assertFalse((self.root/'etapes/03.json').exists());self.assertFalse((self.root/'exports/podcast.json').exists())
        self.assertTrue(source_review.diagnostic(read(self.root/'etapes/02.json')['data'])['empty'])

class AppRecovery(unittest.TestCase):
    def test_old_zero_project_can_be_refined_without_reimporting_the_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            app=App(Path(directory),FakeClient)
            try:
                identity=app.create({'name':'Ancien projet vide','settings':defaults()})['id'];folder=app.project(identity)
                make_pdf(folder/'sources/p.pdf')
                meta=read(folder/'projet.json');meta['pdfs']=[{'file':'p.pdf','name':'Extrait.pdf'}];meta['audio_settings']={'voices':{'Sophie':'profile-a','Emma':'profile-b'}};write(folder/'projet.json',meta)
                Pipeline(folder,FakeClient()).run(1,1);source=read(folder/'etapes/01.json')['data'];original=(folder/'etapes/01.json').read_bytes()
                parts=[]
                for part in source['documents'][0]['parts']:
                    fact={'id':f'PDF1-P{part["number"]}-I001','statement':'Le signal s’atténue dans la fibre.','explanation':'Les pertes réduisent la puissance disponible.','pages':[part['pages'][0]],'reason':'À vérifier : evidence doit recopier un passage exact du PDF fourni.'}
                    parts.append({'number':part['number'],'ideas':[],'excluded_ideas':[fact],'uncertain_ideas':[fact]})
                old={'quality_version':quality.VERSION,'documents':[{'id':'PDF1','name':'Extrait.pdf','parts':parts,'glossary':{}}]}
                write(folder/'etapes/02.json',{'data':old});write(folder/'etapes/03.json',{'data':old})
                status=app.summary(folder);self.assertTrue(status['source_diagnostic']['empty']);self.assertEqual(status['source_diagnostic']['total'],3)
                with self.assertRaisesRegex(ValueError,'Réexaminer'):app.enqueue(folder,{'first':4,'until':9})
                app.enqueue(folder,{'first':2,'until':2,'refine':True});app.pending.join()
                status=app.summary(folder);self.assertEqual(status['task']['state'],'done',status['task']);self.assertFalse(status['source_diagnostic']['empty'])
                self.assertEqual((folder/'etapes/01.json').read_bytes(),original)
                self.assertEqual(read(folder/'projet.json')['audio_settings'],meta['audio_settings'])
                self.assertTrue(list((folder/'versions').rglob('02.json')))
                self.assertFalse((folder/'etapes/03.json').exists())
            finally:app.close()

if __name__=='__main__':unittest.main()
