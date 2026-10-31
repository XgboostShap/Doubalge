import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_html import construire_document, exporter, serialiser_html
from lancer_studio import verifier_events


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / 'video.mp4'
        self.media.write_bytes(b'fixture-media')
        self.analysis = {'analysis_id': 'projet-A', 'source_sha256': 'a' * 64,
                         'duration': 3, 'fps': 25, 'cuts': [1.5],
                         'events': [{'start': .25, 'end': 1.25, 'speaker': 0}]}

    def document(self):
        return construire_document(self.analysis, [0, .5, 1], self.media, self.media)

    def test_exports_carry_own_source_and_no_example_timeline(self):
        document = self.document()
        editor, player = exporter(document, self.root)
        data = json.loads(re.search(r'<script id="editor-data" type="application/json">(.*?)</script>',
                                    editor.read_text(encoding='utf-8'), re.S).group(1))
        self.assertEqual(data['analysis_id'], 'projet-A')
        self.assertEqual(data['initial'][0]['start'], .25)
        self.assertEqual(len(data['characters']), 1)
        self.assertNotIn('duoAudio', data)
        self.assertIn('base64,', data['media'])
        self.assertIn('impro-data', player.read_text(encoding='utf-8'))
        self.assertEqual(document['automatic'][0]['reviewed'], False)
        document['initial'][0]['start'] = .5
        self.assertEqual(document['automatic'][0]['start'], .25)

    def test_json_cannot_terminate_data_script(self):
        value = {'label': '</script><script>alert(1)</script> ⚠'}
        encoded = serialiser_html(value)
        self.assertNotIn('</script>', encoded)
        self.assertEqual(json.loads(encoded), value)

    def test_invalid_bounds_and_cuts_rejected(self):
        for end in [float('nan'), 4, .1]:
            with self.subTest(end=end):
                self.analysis['events'][0]['end'] = end
                with self.assertRaises(ValueError):
                    self.document()
        self.analysis['events'][0]['end'] = 1.25
        self.analysis['cuts'] = [-1]
        with self.assertRaises(ValueError):
            self.document()

    def test_editor_corrections_are_not_accepted_as_raw_timeline(self):
        with self.assertRaises(ValueError):
            verifier_events({'intervals': []}, 3)
        self.assertEqual(verifier_events({'events': [{'start': 0, 'end': 3.04, 'speaker': 0}]}, 3)[0]['end'], 3)


if __name__ == '__main__':
    unittest.main()
