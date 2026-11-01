"""Ouverture locale, ancienne adresse et port occupé : aucune nouvelle analyse."""
import errno
import http.client
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_html import SCHEMA
from serveur_editeur import create_server, LocalServer


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.editor = Path(self.temp.name)/'OSS-editeur.html'
        self.editor.write_text('<script id="editor-data" type="application/json">'+json.dumps(
            {'schema':SCHEMA,'analysis_id':'scene-test','characters':[]})+'</script>',encoding='utf-8')
        self.server = create_server(self.editor,0)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.cleanup()
        self.temp.cleanup()

    def request(self, path='/', headers=None):
        conn = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        conn.request('GET',path,headers=headers or {})
        response = conn.getresponse()
        result = response.status, response.read().decode(), response.headers
        conn.close()
        return result

    def test_open_without_url_token_and_export_still_protected(self):
        for path in ['/', '/editeur', '/?retour=1']:
            status, html, headers = self.request(path)
            self.assertEqual(status,200)
            self.assertIn('scene-test',html)
            self.assertEqual(headers['X-Frame-Options'],'DENY')
        token = re.search(r'globalThis.DOUBALGE_EXPORT_TOKEN="([^"]+)"',html)[1]
        self.assertEqual(self.request('/status')[0],403)
        self.assertEqual(self.request('/status',{'X-Doubalge-Token':'ancienne-session'})[0],403)
        self.assertEqual(self.request('/status',{'X-Doubalge-Token':token})[0],200)
        self.assertEqual(self.server.editor_url,f'http://127.0.0.1:{self.server.server_port}/')

    def test_stale_session_has_recovery_page(self):
        status,html,_ = self.request('/'+'x'*43)
        self.assertEqual(status,410)
        self.assertIn('Ancienne adresse',html)
        self.assertIn('href="/"',html)
        self.assertNotIn('scene-test',html)

    def test_forged_host_and_cross_site_page_blocked(self):
        self.assertEqual(self.request('/',{'Host':'autre-site.example'})[0],403)
        self.assertEqual(self.request('/',{'Sec-Fetch-Site':'cross-site'})[0],403)
        self.assertEqual(self.request('/',{'Sec-Fetch-Site':'none'})[0],200)
        self.assertEqual(self.request('/',{'Host':f'localhost:{self.server.server_port}'})[0],200)

    def test_occupied_default_port_uses_separate_listener(self):
        calls = []
        def bind(address,handler):
            calls.append(address)
            if address[1] == 8765:
                raise OSError(errno.EADDRINUSE,'Port occupé')
            return LocalServer(address,handler)
        with patch('serveur_editeur.LocalServer',side_effect=bind):
            second = create_server(self.editor)
        try:
            self.assertEqual(calls,[('127.0.0.1',8765),('127.0.0.1',0)])
            self.assertNotEqual(second.server_port,self.server.server_port)
        finally:
            second.cleanup()


if __name__ == '__main__':
    unittest.main()
