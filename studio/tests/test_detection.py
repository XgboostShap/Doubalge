import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from detection_parole import detecter, normaliser_tours, python_avance
from export_html import empreinte
from lancer_studio import initialiser, ffmpeg, traiter


class TurnsTests(unittest.TestCase):
    def test_short_pauses_and_interruptions_are_preserved(self):
        result = normaliser_tours([(0, 1, 'A'), (1.2, 2, 'A'), (.9, 1.3, 'B')], 3)
        self.assertEqual(result, [{'start': 0, 'end': 1, 'speaker': 0},
                                  {'start': .9, 'end': 1.3, 'speaker': 1},
                                  {'start': 1.2, 'end': 2, 'speaker': 0}])

    def test_overlaps_merge_for_same_voice_without_shortening_nested_turn(self):
        result = normaliser_tours([(1, 4, 'A'), (2, 3, 'A'), (3.5, 5, 'A'), (2, 3, 'B')], 6)
        self.assertEqual(result, [{'start': 1, 'end': 5, 'speaker': 0},
                                  {'start': 2, 'end': 3, 'speaker': 1}])

    def test_labels_follow_first_appearance_and_bounds_are_clipped(self):
        result = normaliser_tours([(2, 5, 'first-in-input'), (-.1, 1, 'early'), (8, 9, 'outside')], 3)
        self.assertEqual(result, [{'start': 0, 'end': 1, 'speaker': 0},
                                  {'start': 2, 'end': 3, 'speaker': 1}])
        with self.assertRaises(ValueError):
            normaliser_tours([(0, float('nan'), 'A')], 3)
        self.assertEqual(normaliser_tours([(0, 2, 'A')], 1.23456)[0]['end'], 1.23456)

    def test_model_choice_is_explicit_and_requires_completed_install(self):
        with patch('detection_parole.python_avance', return_value=None), patch('detection_parole.classique') as legacy:
            with self.assertRaises(RuntimeError):
                detecter('audio.wav', 'unused', 2, True, 3, Path('.'), mode='community-1')
            legacy.assert_not_called()
            detecter('audio.wav', 'unused', 2, True, 3, Path('.'), mode='auto')
            legacy.assert_called_once_with('audio.wav', 'unused', 2, True, 3)

    def test_partial_installation_is_not_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / '.venv-detection' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch('detection_parole.ROOT', root), patch.dict(os.environ, {}, clear=True):
                self.assertIsNone(python_avance())
                (root / '.venv-detection/installation-ok.txt').write_text('community-1-v1')
                self.assertEqual(python_avance(), executable)


class ReuseTests(unittest.TestCase):
    def test_corrected_json_bypasses_detection_even_when_advanced_mode_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source.mp4'
            initialiser()
            ffmpeg(['-f', 'lavfi', '-i', 'color=c=blue:size=64x64:rate=10',
                    '-f', 'lavfi', '-i', 'sine=frequency=220:duration=2', '-t', '2',
                    '-c:v', 'libx264', '-threads', '1', '-c:a', 'aac', str(source)])
            digest = empreinte(source)
            correction = {'schema': 'doublagebasic.timeline-edit.v1', 'analysis_id': 'manuel',
                          'source_sha256': digest, 'duration': 2,
                          'intervals': [{'id': 'edit-unique', 'start': .35, 'end': .9,
                                         'character': 'voice:0', 'reviewed': True}],
                          'cuts': [{'id': 'plan-manuel', 'time': 1, 'reviewed': True}]}
            path = root / 'corrections.json'
            path.write_text(json.dumps(correction))
            with patch('detection_parole.detecter', side_effect=AssertionError('Nouvelle IA interdite')) as detector:
                editor, _ = traiter(str(source), root / 'resultat', corrections=path,
                                    detection='community-1', separation=False)
                detector.assert_not_called()
            data = json.loads((root / 'resultat/timeline.json').read_text())
            self.assertEqual(data['corrections']['intervals'], correction['intervals'])
            self.assertEqual(data['corrections']['cuts'], correction['cuts'])
            self.assertIn('edit-unique', editor.read_text())


if __name__ == '__main__':
    unittest.main()
