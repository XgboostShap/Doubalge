"""Compatibilité de l'ancienne IHM, imports sans exécution et lecture TXT."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import audio_export,voice_legacy
from app import App
from fixtures import FakeClient
from storage import defaults,read,write
from test_audio_export import VoiceServer,final_script

OLD_SETTINGS="""
voice_studio_url = st.text_input('API', 'http://127.0.0.1:3900')
vs_anneso = st.text_input('AnneSo', 'profile-anne')
vs_sophie = st.text_input('Sophie', 'profile-sophie')
normalize_audio = st.checkbox('Volume', value=True)
target_dbfs = st.slider('dBFS', -26, -14, -20)
pause_ms = st.slider('Pause', 100, 1000, 350, 50)
"""

class ImportTests(unittest.TestCase):
    def test_legacy_widget_defaults_are_read_without_executing_python(self):
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'unsafe'
            source=OLD_SETTINGS+'\nopen('+repr(str(marker))+', "w").write("executed")\n'
            result=voice_legacy.read_settings(source)
            self.assertFalse(marker.exists());self.assertEqual(result['pause_ms'],350)
            self.assertEqual(result['target_dbfs'],-20)
            self.assertEqual(result['voices'],{'AnneSo':'profile-anne','Sophie':'profile-sophie'})
    def test_missing_and_identical_references_are_rejected(self):
        for values in [{'vs_anneso':'x'},{'vs_anneso':'x','vs_sophie':'x'}]:
            with self.subTest(values=values),self.assertRaises(ValueError):voice_legacy.read_settings(json.dumps(values))
    def test_dialogue_is_kept_word_for_word_and_is_not_marked_scientifically_valid(self):
        text='AnneSo: Pourquoi ?\nSophie: Voici une réponse.\nElle continue ici.'
        value=voice_legacy.parse_dialogue(text)
        self.assertEqual(value['speakers'],['AnneSo','Sophie'])
        self.assertEqual([t['text'] for t in value['chapters'][0]['turns']],['Pourquoi ?','Voici une réponse. Elle continue ici.'])
        self.assertNotIn('content_checks_passed',value);self.assertEqual(value['source_kind'],'provided_text')
        audio_export.validate_script(value)
        changed=copy.deepcopy(value);changed['chapters'][0]['turns'][1]['text']='Un autre résultat.'
        with self.assertRaises(ValueError):audio_export.validate_script(changed)
    def test_replies_without_speakers_are_not_silently_ignored(self):
        with self.assertRaises(ValueError):voice_legacy.parse_dialogue('Un titre sans interlocuteur.\nSophie: Une réponse.')
    def test_trial_keeps_whole_replies_and_never_modifies_the_complete_script(self):
        value=voice_legacy.parse_dialogue('\n'.join(('AnneSo' if n%2==0 else 'Sophie')+': '+('mot '*100)+'.' for n in range(12)))
        before=copy.deepcopy(value)
        selected=audio_export.selected_segments(value,{**audio_export.defaults(),'scope_minutes':3},value['speakers'])
        self.assertEqual(len(selected),4);self.assertEqual(value,before)

class LocalApiTests(unittest.TestCase):
    def setUp(self):self.server=VoiceServer()
    def tearDown(self):self.server.close()
    def test_api_requiring_bearer_local_and_exact_legacy_fields_works(self):
        self.server.require_auth=True;self.server.strict=True
        client=audio_export.VoiceStudio({'endpoint':self.server.endpoint})
        client.health();self.assertEqual(len(client.voices()),2)
        raw=client.speech('Bonjour, voici la voix.','ref-sophie')
        self.assertTrue(raw.startswith(b'RIFF'));self.assertEqual(set(self.server.calls[0]),{'model','input','voice','response_format'})
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg requis pour ce test média')
    def test_silent_synthesis_is_rejected_before_mp3_export(self):
        self.server.silent=True
        with tempfile.TemporaryDirectory() as directory:
            render=audio_export.AudioRenderer(Path(directory),{'endpoint':self.server.endpoint,'voices':{'Sophie':'ref-sophie','Emma':'ref-emma'}},['Sophie','Emma'])
            with self.assertRaisesRegex(ValueError,'silencieuse'):render.render(final_script())
            self.assertFalse((Path(directory)/'exports/podcast.mp3').exists())
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg requis pour ce test média')
    def test_voice_levels_are_balanced_without_clipping(self):
        self.server.amplitudes={'ref-sophie':800,'ref-emma':8000}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);render=audio_export.AudioRenderer(root,{'endpoint':self.server.endpoint,'voices':{'Sophie':'ref-sophie','Emma':'ref-emma'}},['Sophie','Emma'])
            render.render(final_script());stats=[audio_export.pcm_stats(p) for p in (root/'audio_cache').glob('*.wav')]
            self.assertEqual(len(stats),2);self.assertLess(abs(stats[0][0]-stats[1][0]),1)
            self.assertTrue(all(p<=-1 for _,p in stats))

class AppImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=App(Path(self.temp.name),FakeClient)
        identity=self.app.create({'name':'Essai','settings':defaults()})['id'];self.folder=self.app.project(identity)
    def tearDown(self):self.app.close();self.temp.cleanup()
    def test_cast_import_preserves_pdf_steps_and_rebuilds_only_dialogue(self):
        for n in range(1,10):write(self.folder/'etapes'/f'{n:02}.json',{'data':{'quality_version':'source-review-v4'}})
        write(self.folder/'exports/podcast.json',final_script())
        first=(self.folder/'etapes/02.json').read_bytes()
        result=self.app.import_audio_settings(self.folder,{'source':OLD_SETTINGS,'apply_cast':True})
        self.assertEqual(result['invalidated_from'],8);self.assertEqual((self.folder/'etapes/02.json').read_bytes(),first)
        self.assertFalse((self.folder/'etapes/08.json').exists());self.assertTrue((self.folder/'etapes/07.json').exists())
        self.assertEqual(read(self.folder/'projet.json')['settings']['speakers'],['AnneSo','Sophie'])
    def test_import_for_provided_text_keeps_the_pdf_project_and_its_cast(self):
        self.app.save_audio_text(self.folder,{'mode':'provided','text':'AnneSo: Pourquoi ?\nSophie: Une explication.'})
        write(self.folder/'etapes/08.json',{'data':{}});before=(self.folder/'etapes/08.json').read_bytes()
        result=self.app.import_audio_settings(self.folder,{'source':OLD_SETTINGS,'apply_cast':True})
        self.assertIsNone(result['invalidated_from']);self.assertEqual((self.folder/'etapes/08.json').read_bytes(),before)
        self.assertEqual(self.app.summary(self.folder)['audio']['speakers'],['AnneSo','Sophie'])
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg requis pour ce test média')
    def test_provided_text_renders_without_pdf_and_trial_preserves_full_mp3(self):
        server=VoiceServer()
        try:
            self.app.save_audio_text(self.folder,{'mode':'provided','text':'AnneSo: Pourquoi ?\nSophie: Voici la réponse.'})
            config={'endpoint':server.endpoint,'voices':{'AnneSo':'ref-sophie','Sophie':'ref-emma'}}
            self.app.save_audio_settings(self.folder,config);self.app.enqueue_audio(self.folder,{'action':'generate'});self.app.pending.join()
            state=self.app.summary(self.folder);self.assertEqual(state['task']['state'],'done',state['task'])
            self.assertTrue(state['audio']['available']);full=(self.folder/'exports/podcast.mp3').read_bytes()
            self.app.save_audio_settings(self.folder,{**config,'scope_minutes':3});self.app.enqueue_audio(self.folder,{'action':'generate'});self.app.pending.join()
            state=self.app.summary(self.folder);self.assertEqual(state['task']['state'],'done',state['task']);self.assertEqual(state['audio']['filename'],'essai-3min.mp3')
            self.assertEqual((self.folder/'exports/podcast.mp3').read_bytes(),full)
            self.assertTrue((self.folder/'exports/rapport_essai-3min.csv').exists())
            self.assertFalse((self.folder/'etapes/01.json').exists());self.assertNotIn('content_checks_passed',read(self.folder/'lecture/dialogue.json'))
        finally:server.close()
    def test_invalid_text_does_not_replace_the_existing_source(self):
        self.app.save_audio_text(self.folder,{'mode':'provided','text':'AnneSo: Pourquoi ?\nSophie: Une réponse.'})
        before=(self.folder/'lecture/dialogue.json').read_bytes()
        with self.assertRaises(ValueError):self.app.save_audio_text(self.folder,{'mode':'provided','text':'Un texte sans noms.'})
        self.assertEqual((self.folder/'lecture/dialogue.json').read_bytes(),before)

if __name__=='__main__':unittest.main()
