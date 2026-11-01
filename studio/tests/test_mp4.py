"""Vérifie le son décodé du MP4, les corrections et l'arrêt de FFmpeg."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_mp4 import Cancelled, render, run, windows


class MixRulesTests(unittest.TestCase):
    def test_overlap_short_pause_and_unknown(self):
        intervals = [{'start': .2, 'end': .4, 'character': 'voice:0'},
                     {'start': .3, 'end': .8, 'character': 'voice:1'},
                     {'start': .45, 'end': .6, 'character': 'voice:0'},
                     {'start': .9, 'end': 1., 'character': None}]
        mix = {'removedCharacters': ['voice:0'], 'keepUnknown': True}
        self.assertEqual(windows(intervals, mix, 1), [[0, .2], [.4, .45], [.6, 1]])
        mix['keepUnknown'] = False
        self.assertEqual(windows(intervals, mix, 1), [[.4, .45], [.6, .8]])

    def test_cancellation_terminates_process(self):
        cancel = threading.Event()
        timer = threading.Timer(.2, cancel.set)
        timer.start()
        with self.assertRaises(Cancelled):
            run([sys.executable, '-c', 'import time; time.sleep(30)'], cancel)
        timer.join()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/ffprobe requis pour les tests multimédias')
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy
        from make_fixture import create
        from serveur_editeur import load_document
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.document = load_document(create(cls.directory)[0])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def request(self, removed, ambience):
        d = self.document
        edits = {k: copy.deepcopy(d[k]) for k in ['schema', 'analysis_id', 'source_sha256', 'duration', 'characters']}
        edits.update(intervals=copy.deepcopy(d['initial']), cuts=copy.deepcopy(d['initialCuts']),
                     audioMix={'removedCharacters': removed, 'keepAmbience': ambience, 'keepUnknown': True})
        # Déplacer la première plage : le rendu doit utiliser la correction, pas l'analyse.
        edits['intervals'][0].update(start=.3, end=.6, character='voice:1')
        edits['cuts'][0]['time'] = 1.0
        edits['characters'][0]['label'] = 'Élodie {\\test}'
        return {'edits': edits, 'profile': 'mail'}

    def test_real_mp4_audio_and_corrected_cues(self):
        import numpy as np
        for removed, ambience in [(['voice:0'], True), (['voice:0', 'voice:1'], False)]:
            request = self.request(removed, ambience)
            with self.subTest(removed=removed, ambience=ambience), tempfile.TemporaryDirectory(dir=self.directory) as work:
                progress = []
                output = render(self.document, request, work, threading.Event(), progress.append)
                metadata = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)]))
                video, audio = metadata['streams']
                self.assertEqual((video['codec_name'], video['pix_fmt'], audio['codec_name']), ('h264', 'yuv420p', 'aac'))
                self.assertAlmostEqual(float(metadata['format']['duration']), 3, places=1)
                self.assertEqual(progress[-1], 1)
                raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(output), '-vn', '-f', 'f32le', '-ac', '1', '-ar', '24000', '-'])
                samples = np.frombuffer(raw, dtype='<f4')
                def amplitude(t, frequency):
                    segment = samples[round(t*24000):round((t+.08)*24000)]
                    phase = np.arange(len(segment))*2*np.pi*frequency/24000
                    return 2*abs(np.sum(segment*np.exp(-1j*phase)))/len(segment)
                # .4 : plage réattribuée à voice:1 ; .9 : voice:0 retirée (avec chevauchement).
                # 1.5 : autre voix ; 2.45 : voix toujours conservée.
                for t, retained in [(.4, len(removed) == 1), (.9, False), (1.5, len(removed) == 1), (2.45, True)]:
                    self.assertGreater(amplitude(t, 440), .08) if retained else self.assertLess(amplitude(t, 440), .015)
                    self.assertGreater(amplitude(t, 110), .08) if ambience else self.assertLess(amplitude(t, 110), .015)
                # Comparer les pixels avec/sans vignettes en bas de l'image.
                def frame(path):
                    return np.frombuffer(subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', '0.9', '-i', str(path), '-frames:v', '1', '-vf', 'scale=480:360', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']), dtype=np.uint8).reshape(360, 480, 3).astype(float)
                a, b = frame(output), frame(Path(work)/'source.mp4')
                self.assertGreater(np.mean(abs(a[210:310,400:470]-b[210:310,400:470])), 8)

    def test_mismatched_corrections_and_invalid_selection_rejected(self):
        request = self.request([], True)
        with self.assertRaisesRegex(ValueError, 'une ou deux'):
            render(self.document, request, self.directory, threading.Event(), lambda _: None)
        request['edits']['source_sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'correspondent'):
            render(self.document, request, self.directory, threading.Event(), lambda _: None)


if __name__ == '__main__':
    unittest.main()
