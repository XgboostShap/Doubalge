import copy
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_local import create_server, scrub, stop_tree
from commun import FFMPEG
from edition import SCHEMA, read_json, sha256, validate
from duo import dialogue_mask


class LocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temp.name) / 'source.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=25',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=24000', '-t', '3',
                        '-c:v', 'libx264', '-c:a', 'aac', str(cls.source)], check=True)
        cls.server = create_server(Path(cls.temp.name) / 'data', 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.csrf = cls.server.store.csrf
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.store.close()
        cls.server.server_close()
        cls.temp.cleanup()

    def request(self, path, body=None, headers=None, method=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        send_headers = {'X-Doublage-Token': self.csrf}
        if headers:
            send_headers.update(headers)
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode()
            send_headers['Content-Type'] = 'application/json'
        conn.request(method or ('POST' if body is not None else 'GET'), path, body=body, headers=send_headers)
        response = conn.getresponse()
        raw = response.read()
        mime = response.getheader('Content-Type','')
        result = (response.status, json.loads(raw) if mime.startswith('application/json') else raw, dict(response.getheaders()))
        conn.close()
        return result

    def new(self):
        code, p, _ = self.request('/api/projects', {'name':'Essai'})
        self.assertEqual(code, 201)
        return p

    def ready(self):
        p = self.new()
        prefix = '/api/projects/' + p['id']
        self.assertEqual(self.request(prefix+'/source', self.source.read_bytes())[0], 200)
        edit = dict(schema=SCHEMA, analysis_id='test-local', source_sha256=sha256(self.source), duration=3.,
                    intervals=[dict(id='a',start=.2,end=1.5,character='voice:0',reviewed=True),
                               dict(id='b',start=1.,end=2.,character='voice:1',reviewed=False)],
                    cuts=[dict(id='c',time=1.,reviewed=False)])
        self.assertEqual(self.request(prefix+'/analyze', {'corrections':edit})[0], 200)
        self.wait(p['id'])
        code, value, _ = self.request(prefix)
        self.assertEqual(code, 200)
        return value['project'], value['corrections']

    def wait(self, ident):
        for _ in range(150):
            task = self.server.store.task(self.server.store.folder(ident))
            if task['status'] not in ('queued','running'):
                if task['status'] != 'done':
                    journal = self.server.store.folder(ident) / 'journal.txt'
                    self.fail(journal.read_text() if journal.exists() else str(task))
                return
            time.sleep(.1)
        self.fail('Traitement trop long')

    def test_host_origin_csrf(self):
        self.assertEqual(self.request('/api/state', headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/api/projects',{'name':'x'}, {'Origin':'http://evil.example'})[0],403)
        self.assertEqual(self.request('/api/projects',{'name':'x'}, {'X-Doublage-Token':'wrong'})[0],403)
        self.assertEqual(self.request('/api/state',headers={'Sec-Fetch-Site':'cross-site'})[0],403)

    def test_paths_and_ranges(self):
        p, _ = self.ready()
        prefix = '/files/'+p['id']+'/'
        self.assertEqual(self.request(prefix+'../projet.json')[0],404)
        self.assertEqual(self.request(prefix+'original.mp4')[0],404)
        self.assertEqual(self.request(prefix+'%2e%2e%2fprojet.json')[0],404)
        code, raw, headers = self.request(prefix+'lecture.mp4',headers={'Range':'bytes=3-24'})
        self.assertEqual(code,206)
        self.assertEqual(len(raw),22)
        self.assertTrue(headers['Content-Range'].startswith('bytes 3-24/'))
        self.assertEqual(self.request(prefix+'lecture.mp4',headers={'Range':'bytes=99999999-'})[0],416)
        self.assertEqual(self.request(prefix+'lecture.mp4',headers={'Range':'bytes=-10'})[0],206)

    def test_import_and_revision(self):
        p, edit = self.ready()
        folder = self.server.store.folder(p['id'])
        self.assertEqual(read_json(folder/'analyse.json')['raw_events'],None)
        self.assertEqual(sum(i['reviewed'] for i in edit['intervals']),1)
        wrong = copy.deepcopy(edit);wrong['source_sha256']='wrong'
        prefix = '/api/projects/'+p['id']
        self.assertEqual(self.request(prefix+'/corrections',{'revision':p['revision'],'corrections':wrong})[0],400)
        no_cuts = copy.deepcopy(edit);del no_cuts['cuts']
        code, value, _ = self.request(prefix+'/corrections',{'revision':p['revision'],'corrections':no_cuts})
        self.assertEqual(code,200)
        self.assertEqual(read_json(folder/'corrections.json')['cuts'],edit['cuts'])
        self.assertEqual(self.request(prefix+'/corrections',{'revision':p['revision'],'corrections':edit})[0],409)
        edit['cuts']=[]
        self.assertEqual(self.request(prefix+'/corrections',{'revision':value['revision'],'corrections':edit})[0],200)
        self.assertEqual(read_json(folder/'corrections.json')['cuts'],[])
        self.assertEqual(self.request(prefix+'/analyze',{})[0],409)
        self.assertTrue(list((folder/'sauvegardes').glob('*.json')))

    def test_bad_fingerprint_fails_before_preview(self):
        p = self.new();prefix='/api/projects/'+p['id']
        self.request(prefix+'/source',self.source.read_bytes())
        edit=dict(schema=SCHEMA,analysis_id='bad',source_sha256='bad',duration=3,intervals=[],cuts=[])
        self.request(prefix+'/analyze',{'corrections':edit})
        for _ in range(100):
            task=self.server.store.task(self.server.store.folder(p['id']))
            if task['status']=='error':break
            time.sleep(.05)
        self.assertEqual(task['status'],'error')
        self.assertFalse((self.server.store.folder(p['id'])/'lecture.mp4').exists())

    def test_voice_ids(self):
        p,_=self.ready();prefix='/api/projects/'+p['id']
        code,result,_=self.request(prefix+'/voices',dict(revision=p['revision'],label='Hors champ'))
        self.assertEqual(code,200)
        self.assertEqual(result['voice'],'voice:2')
        self.assertEqual(self.request(prefix+'/voices',dict(revision=result['revision'],voice='voice:2',label='Narration'))[0],200)

    def test_token_memory_only_and_scrub(self):
        fake='hf_'+'z'*32
        self.assertEqual(self.request('/api/token',{'token':fake})[0],200)
        code,state,_=self.request('/api/state')
        self.assertTrue(state['token_set']);self.assertNotIn(fake,json.dumps(state))
        self.assertNotIn(fake,scrub('error '+fake,fake))
        for path in self.server.store.data.rglob('*.json'):
            self.assertNotIn(fake,path.read_text())
        self.request('/api/token',{'token':''})

    def test_mask_overlaps(self):
        rows=[dict(start=0,end=2,character='voice:0'),dict(start=1,end=3,character='voice:1'),dict(start=2.5,end=3,character='voice:2')]
        mask=dialogue_mask(rows,'voice:0','play_one',3,100)
        self.assertFalse(mask[150]);self.assertTrue(mask[225]);self.assertTrue(mask[275])
        mask=dialogue_mask(rows,'voice:0','keep_one',3,100)
        self.assertTrue(mask[50]);self.assertFalse(mask[150])

    def test_process_tree_cancellation(self):
        if os.name=='nt':self.skipTest('Linux ici')
        child=subprocess.Popen([sys.executable,'-c','import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(120)"]); print(p.pid,flush=True);time.sleep(120)'],stdout=subprocess.PIPE,text=True,start_new_session=True)
        pid=int(child.stdout.readline())
        child.stdout.close()
        stop_tree(child)
        self.assertIsNotNone(child.returncode)
        status=Path('/proc')/str(pid)/'stat'
        self.assertTrue(not status.exists() or status.read_text().split()[2]=='Z')

    def test_second_server_cannot_share_data(self):
        with self.assertRaises(RuntimeError):
            create_server(self.server.store.data, 0)

    def test_cancel_queued_job_and_resume_options(self):
        p = self.new()
        folder = self.server.store.folder(p['id'])
        from edition import atomic_json
        atomic_json(folder/'tache.json',dict(status='queued',id='queued-test'))
        code, result, _ = self.request('/api/projects/'+p['id']+'/cancel',{})
        self.assertEqual(code,200)
        self.assertEqual(result['status'],'cancelled')

    def test_real_three_audio_exports_and_html(self):
        import numpy as np
        import soundfile as sf
        p,_=self.ready();folder=self.server.store.folder(p['id'])
        cache=folder/'duo-cache';cache.mkdir()
        t=np.arange(24000*3)/24000
        sf.write(cache/'dialogue.wav',.2*np.sin(2*np.pi*440*t),24000)
        sf.write(cache/'fond.wav',.2*np.sin(2*np.pi*110*t),24000)
        for mode in ('silent','play_one','keep_one'):
            self.assertEqual(self.request('/api/projects/'+p['id']+'/export',dict(mode=mode,voice='voice:0',quality='light',format='html' if mode=='keep_one' else 'mp4'))[0],200)
            self.wait(p['id'])
        exports=list((folder/'exports').glob('*.mp4'))
        self.assertEqual(len(exports),3)
        self.assertEqual(len(list((folder/'exports').glob('*.html'))),1)
        for path in exports:
            self.assertGreater(path.stat().st_size,1000)
            subprocess.run([FFMPEG,'-v','error','-i',str(path),'-f','null','-'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)

if __name__=='__main__':unittest.main()
