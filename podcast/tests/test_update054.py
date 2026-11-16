"""Étape 4 : assembler les passages relus et reprendre les anciens résultats sans les couper."""
import copy
from pathlib import Path
import tempfile
import unittest

from fixtures import FakeClient
from llm import InvalidResponseError,ModelError
from pipeline import Pipeline
from storage import defaults,fingerprint,read,write
import editorial,quality,writing


PARAGRAPH=('Les motifs fréquents sont identifiés dans un ensemble de données. '*6+
           'Cette analyse conserve les conditions du seuil et ses limites.')
SHORT='Les motifs fréquents sont retenus selon un seuil. La sélection conserve ses conditions et ses limites.'


class Replies(FakeClient):
    def __init__(self,text=SHORT,status='supported'):
        super().__init__();self.text=text;self.status=status
    def ask(self,task,payload,instructions,validate,budget=4000):
        if task=='grounded_text':
            self.calls.append((task,copy.deepcopy(payload)))
            value={'text':self.text};validate(value);return value
        if task=='writing_check' and self.status!='supported':
            self.calls.append((task,copy.deepcopy(payload)))
            return {'status':self.status,'reason':'La source ne confirme pas le passage.'}
        return super().ask(task,payload,instructions,validate,budget)


class NoCalls(FakeClient):
    def ask(self,*args,**kwargs):raise AssertionError('Une rédaction déjà relue et compatible doit être réutilisée.')


class CommonTextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        write(self.root/'projet.json',{'settings':defaults(),'pdfs':[]})
        self.idea={'id':'PDF1-P2-I001','statement':'Les motifs fréquents dépendent du seuil dans les données.',
            'explanation':'Le seuil doit être indiqué avec ses conditions.',
            'document':'PDF1','pages':[2],'role':'concept','importance':'essential',
            'evidence':[{'page':2,'quote':'Frequent patterns depend on a threshold in the data. The threshold determines retained patterns under the stated conditions.'}]}
        self.idea['source_hash']=editorial.source_hash(self.idea)
        self.terms={}
    def tearDown(self):self.temp.cleanup()
    def prepare(self,ideas=None):
        data={'quality_version':quality.VERSION,'documents':[{'id':'PDF1','name':'Essai.pdf','glossary':self.terms,
              'parts':[{'number':2,'ideas':ideas or [self.idea],'excluded_ideas':[]}]}]}
        write(self.root/'etapes/02.json',{'data':data})
    def warm(self,text=SHORT,ideas=None):
        self.prepare(ideas);Pipeline(self.root,Replies(text)).run(3,3)
    def snapshot3(self):
        return {p:p.read_bytes() for p in (self.root/'etapes').glob('03.*')} | {
            p:p.read_bytes() for p in (self.root/'etapes/parties').glob('03-*')}
    def assert_preserved(self,files):
        self.assertTrue(all(p.read_bytes()==raw for p,raw in files.items()))
    def packet(self,step=3):
        prefix='Synthese-' if step==3 else 'Commun-'
        return self.root/'etapes/parties'/f'{step:02}-{prefix}{self.idea["id"]}.json'

    def test_a_70_word_synthesis_is_reused_whole_without_another_model_call(self):
        self.assertEqual(len(PARAGRAPH.split()),70)
        self.warm(PARAGRAPH);before=self.snapshot3()
        Pipeline(self.root,NoCalls()).run(4,4)
        data=read(self.root/'etapes/04.json')['data']
        self.assertIn(PARAGRAPH,data['groups'][0]['text'])
        self.assertEqual(read(self.packet(4))['data']['reused_from']['step'],3)
        self.assert_preserved(before)

    def test_existing_stage4_sentence_units_remain_byte_identical(self):
        self.warm()
        writing.rewrite(Pipeline(self.root,Replies(SHORT)),4,'Commun-'+self.idea['id'],self.idea,self.terms,'sentence')
        files={p:p.read_bytes() for p in self.packet(4).parent.glob('04-*')}
        Pipeline(self.root,NoCalls()).run(4,4)
        self.assert_preserved(files)
        self.assertIn(SHORT,read(self.root/'etapes/04.json')['data']['groups'][0]['text'])

    def test_missing_synthesis_unit_is_written_as_a_paragraph_not_a_key_sentence(self):
        self.warm();before=(self.root/'etapes/03.json').read_bytes()
        self.packet().unlink()
        client=Replies(PARAGRAPH);Pipeline(self.root,client).run(4,4)
        drafts=[p for task,p in client.calls if task=='grounded_text']
        self.assertEqual(len(drafts),1);self.assertEqual(drafts[0]['kind'],'explanation')
        self.assertEqual(read(self.packet(4))['data']['word_count'],70)
        self.assertEqual((self.root/'etapes/03.json').read_bytes(),before)
        self.assertTrue(any(task=='writing_check' for task,_ in client.calls))

    def test_all_registry_ideas_survive_even_if_stage3_selected_only_two(self):
        ideas=[]
        for n,label in enumerate(('premier','second','dernier'),1):
            idea=copy.deepcopy(self.idea);idea['id']=f'PDF1-P2-I{n:03}'
            idea['statement']='Le '+label+' motif dépend des conditions de la collecte.'
            idea['source_hash']=editorial.source_hash(idea);ideas.append(idea)
        self.warm(ideas=ideas)
        selected=set(read(self.root/'etapes/03.json')['data']['documents'][0]['synthesis_ids'])
        self.assertEqual(len(selected),2)
        client=Replies();Pipeline(self.root,client).run(4,4)
        data=read(self.root/'etapes/04.json')['data']
        self.assertEqual({i['id'] for i in data['ideas']},{i['id'] for i in ideas})
        self.assertEqual({i for g in data['groups'] for i in g['idea_ids']},{i['id'] for i in ideas})
        self.assertEqual(len([task for task,_ in client.calls if task=='grounded_text']),1)

    def test_an_uncertain_cached_review_is_not_reused(self):
        self.warm();value=read(self.packet());value['data']['review']['status']='uncertain';write(self.packet(),value)
        client=Replies(PARAGRAPH);Pipeline(self.root,client).run(4,4)
        self.assertTrue(any(task=='writing_check' for task,_ in client.calls))
        self.assertNotIn('reused_from',read(self.packet(4))['data'])

    def test_tampered_text_or_an_invented_review_quote_is_not_reused(self):
        for field,bad in (('text','Une interprétation modifiée à la main.'),('quote','An invented quote that is absent from the source.')):
            with self.subTest(field=field):
                self.warm();value=read(self.packet())
                if field=='text':value['data']['text']=bad
                else:value['data']['review']['quote']=bad
                write(self.packet(),value)
                # Vérifier directement la sélection évite qu'une autre unité masque le refus.
                self.assertIsNone(writing.completed_entry(Pipeline(self.root,NoCalls()),3,'Synthese-'+self.idea['id'],self.idea,self.terms))
                self.packet().unlink()

    def test_relevant_glossary_change_prevents_stale_reuse(self):
        self.idea.update(statement='Le DT représente un système physique.',explanation='Le modèle dépend des données du système.',
            evidence=[{'page':2,'quote':'A digital twin (DT) represents a physical system and depends on data from that system.'}])
        self.idea['source_hash']=editorial.source_hash(self.idea)
        self.terms={'DT':[{'definition':'Digital twin','page':2}]}
        self.warm('Le jumeau numérique (DT) représente un système physique à partir de ses données.')
        changed={'DT':[{'definition':'Decision tree','page':2}]}
        self.assertIsNone(writing.completed_entry(Pipeline(self.root,NoCalls()),3,'Synthese-'+self.idea['id'],self.idea,changed))

    def test_a_matching_but_invalid_stage4_cache_cannot_bypass_revalidation(self):
        self.warm();Pipeline(self.root,NoCalls()).run(4,4)
        value=read(self.packet(4));value['data']['text']='Les motifs garantissent une puissance de 900 MW.'
        value['data']['text_hash']=fingerprint(value['data']['text']);write(self.packet(4),value)
        Pipeline(self.root,NoCalls()).run(4,4)
        data=read(self.packet(4))['data']
        self.assertEqual(data['text'],SHORT);self.assertNotIn('900',data['text'])

    def test_corrupt_app_cache_is_rebuilt_from_a_valid_source_unit(self):
        self.warm();self.packet(4).write_text('{JSON interrompu',encoding='utf-8')
        Pipeline(self.root,NoCalls()).run(4,4)
        self.assertEqual(read(self.packet(4))['data']['text'],SHORT)

    def test_rejected_new_paragraph_never_completes_stage4(self):
        self.warm();self.packet().unlink()
        before=(self.root/'etapes/03.json').read_bytes()
        with self.assertRaises(InvalidResponseError):Pipeline(self.root,Replies(PARAGRAPH,status='uncertain')).run(4,4)
        self.assertFalse((self.root/'etapes/04.json').exists());self.assertFalse(self.packet(4).exists())
        self.assertEqual((self.root/'etapes/03.json').read_bytes(),before)

    def test_a_real_key_sentence_over_60_words_is_an_editorial_issue_after_review(self):
        packet=writing.rewrite(Pipeline(self.root,Replies(PARAGRAPH)),6,'Phrase-'+self.idea['id'],self.idea,self.terms,'sentence')
        self.assertEqual(packet['text'],PARAGRAPH);self.assertEqual(packet['word_count'],70)
        self.assertTrue(packet['warnings']);self.assertEqual(packet['review']['status'],'supported')
        self.assertIn('ses limites',packet['text'])

    def test_cost_effective_is_not_translated_as_expensive_interventions(self):
        for source in ('cost-effective interventions','cost- effective interventions'):
            with self.subTest(source=source),self.assertRaisesRegex(ValueError,'coût/efficacité'):
                quality.validate_technical_wording('La méthode permet de planifier des interventions préventives coûteuses.',source)
            quality.validate_technical_wording('La méthode permet de planifier des interventions rentables.',source)
            quality.validate_technical_wording('La méthode permet de planifier des interventions moins coûteuses.',source)

    def test_a_previously_supported_mistranslation_is_rewritten_from_its_source(self):
        self.idea.update(statement='La maintenance prédictive anticipe les défaillances.',
            explanation='Elle permet de planifier des interventions préventives coûteuses.',
            evidence=[{'page':2,'quote':'Predictive maintenance anticipates failures to plan early and cost-effective interventions. Event logs report system health.'}])
        self.idea['source_hash']=editorial.source_hash(self.idea)
        good='La maintenance prédictive anticipe les défaillances et permet de planifier des interventions rentables.'
        self.warm(good);value=read(self.packet())
        value['data']['text']='La maintenance prédictive permet de planifier des interventions préventives coûteuses.'
        value['data']['text_hash']=fingerprint(value['data']['text']);write(self.packet(),value)
        client=Replies(good);Pipeline(self.root,client).run(4,4)
        self.assertEqual(read(self.packet(4))['data']['text'],good)
        self.assertTrue(any(task=='writing_check' for task,_ in client.calls))
        self.assertNotIn('reused_from',read(self.packet(4))['data'])

    def test_writer_and_reviewer_receive_corrected_wording_but_the_registry_is_preserved(self):
        self.idea.update(explanation='La méthode permet de planifier des interventions préventives coûteuses.',
            evidence=[{'page':2,'quote':'The method plans early and cost-effective interventions. Frequent patterns are retained under their threshold conditions.'}])
        self.idea['source_hash']=editorial.source_hash(self.idea);original=copy.deepcopy(self.idea)
        self.prepare();before=(self.root/'etapes/02.json').read_bytes()
        client=Replies('La méthode planifie des interventions rentables tout en conservant les conditions de sélection des motifs.')
        Pipeline(self.root,client).run(3,3)
        draft=next(p for task,p in client.calls if task=='grounded_text')
        review=next(p for task,p in client.calls if task=='writing_check')
        self.assertIn('rentables',draft['explanation']);self.assertNotIn('coûteuses',draft['explanation'])
        self.assertIn('rentables',review['expected_explanation'])
        self.assertEqual(self.idea,original);self.assertEqual((self.root/'etapes/02.json').read_bytes(),before)
        entry=read(self.packet())['data'];self.assertTrue(entry['source_wording_corrections'])
        self.assertEqual(entry['source_hash'],editorial.source_hash(original))

    def test_cost_wording_repair_requires_the_source_and_preserves_units_and_negations(self):
        fact={'statement':'La méthode permet de planifier une intervention coûteuse.',
              'explanation':'La puissance indiquée reste à 1 mW.'}
        before=copy.deepcopy(fact)
        repaired=quality.normalize_terminology(fact,'The method plans early and cost-effective interventions. The power remains 1 mW.')
        self.assertIn('une intervention rentable',repaired['statement']);self.assertIn('1 mW',repaired['explanation'])
        self.assertEqual(fact,before)
        for source in ('The intervention can be expensive.','These interventions are not cost-effective.'):
            self.assertEqual(quality.normalize_terminology(fact,source),fact)
        less={**fact,'statement':'La méthode permet de planifier des interventions moins coûteuses.'}
        self.assertEqual(quality.normalize_terminology(less,'Cost-effective interventions are planned.'),less)

    def test_generated_cost_mistranslation_is_traced_and_reviewed_after_source_based_repair(self):
        self.idea.update(statement='La méthode anticipe les défaillances.',
            explanation='La méthode permet de planifier des interventions rentables.',
            evidence=[{'page':2,'quote':'The method anticipates failures to plan early and cost-effective interventions.'}])
        self.idea['source_hash']=editorial.source_hash(self.idea)
        bad='La méthode anticipe les défaillances pour planifier des interventions coûteuses.'
        self.prepare();client=Replies(bad);Pipeline(self.root,client).run(3,3)
        entry=read(self.packet())['data']
        self.assertIn('interventions rentables',entry['text'])
        correction=next(c for c in entry['source_wording_corrections'] if c['field']=='draft.text')
        self.assertEqual(correction['before'],bad);self.assertEqual(correction['after'],entry['text'])
        review=next(p for task,p in client.calls if task=='writing_check')
        self.assertEqual(review['text'],entry['text']);self.assertEqual(entry['review']['status'],'supported')

    def test_a_source_based_translation_repair_does_not_bypass_a_negative_review(self):
        self.idea.update(statement='La méthode anticipe les défaillances.',
            explanation='La méthode permet de planifier des interventions rentables.',
            evidence=[{'page':2,'quote':'The method anticipates failures to plan early and cost-effective interventions.'}])
        self.idea['source_hash']=editorial.source_hash(self.idea);self.prepare()
        client=Replies('La méthode permet de planifier des interventions coûteuses.',status='uncertain')
        with self.assertRaises(InvalidResponseError):Pipeline(self.root,client).run(3,3)
        self.assertFalse(self.packet().exists());self.assertFalse((self.root/'etapes/03.json').exists())

    def test_source_bibliographic_markers_stay_in_evidence_and_out_of_reviewed_speech(self):
        self.idea['evidence'][0]['quote']+=' The retained threshold is reported [1].'
        self.idea['source_hash']=editorial.source_hash(self.idea);self.prepare()
        before=(self.root/'etapes/02.json').read_bytes()
        client=Replies('Le seuil détermine les motifs retenus dans les données [1]. Les conditions restent indiquées.')
        Pipeline(self.root,client).run(3,3)
        entry=read(self.packet())['data'];self.assertNotIn('[1]',entry['text'])
        self.assertEqual((self.root/'etapes/02.json').read_bytes(),before)
        self.assertIn('[1]',entry['source_wording_corrections'][0]['before'])
        review=next(p for task,p in client.calls if task=='writing_check')
        self.assertEqual(review['text'],entry['text']);self.assertTrue(any('[1]' in r['text'] for r in review['source_excerpts']))

    def test_draft_preparation_keeps_values_ranges_conditions_indices_and_unknown_markers(self):
        idea=copy.deepcopy(self.idea)
        idea['evidence'][0]['quote']+=' A power of 1 mW is reported [1].'
        for text in ('La puissance reste à 1 mW sous les mêmes conditions.',
                     'La condition reste dans [0,1] et dans [1-2].',
                     'Le code x[1] reste un indice dans le modèle.',
                     'La méthode est attribuée à une référence inconnue [999].'):
            with self.subTest(text=text):self.assertEqual(writing.prepare_draft(text,idea),text)
        with self.assertRaisesRegex(ValueError,'références bibliographiques'):
            writing.validate_text(writing.prepare_draft('Les motifs sont retenus selon ce seuil [999].',idea),idea,{})

    def test_network_failure_during_a_missing_paragraph_preserves_the_previous_steps(self):
        self.warm();self.packet().unlink();before=self.snapshot3()
        class Offline(FakeClient):
            def ask(self,*args,**kwargs):raise ModelError('Connexion interrompue')
        with self.assertRaisesRegex(ModelError,'Étape 4/9'):Pipeline(self.root,Offline()).run(4,4)
        self.assert_preserved(before);self.assertFalse((self.root/'etapes/04.json').exists())


if __name__=='__main__':unittest.main()
