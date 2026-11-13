"""API VoiceStudio, fichiers MP3 réels, reprise et lecture HTTP avec déplacement."""
import io
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
import urllib.request

import audio_export
from app import App,Server
from llm import Cancelled
from storage import defaults,read,write


def wav_bytes(frequency=440,rate=22050):
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate)
        out.writeframes(b''.join(struct.pack('<h',int(3000*math.sin(2*math.pi*frequency*n/rate))) for n in range(rate//8)))
    return buffer.getvalue()


class VoiceHandler(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def respond(self,status,value,mime='application/json'):
        data=json.dumps(value).encode() if mime=='application/json' else value
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path=='/v1/audio/voices':
            self.respond(200,{'voices':[{'voice_id':'ref-sophie','name':'Sophie','type':'profile'},
                {'id':'ref-emma','name':'Emma','type':'profile'},{'voice_id':'alloy','name':'Alloy','type':'openai_alias'}]})
        else:self.respond(404,{'detail':'not found'})
    def do_POST(self):
        value=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.calls.append(value)
        if self.server.fail_at==len(self.server.calls):self.respond(503,{'detail':'interruption simulée'});return
        if self.server.bad_audio:self.respond(200,b'not a wave file','audio/wav');return
        if self.server.stall:
            self.send_response(200);self.send_header('Content-Length','999999');self.end_headers()
            self.wfile.write(wav_bytes()[:44]);self.wfile.flush();self.server.started.set();self.server.release.wait(10);return
        self.respond(200,wav_bytes(440 if value['voice']=='ref-sophie' else 660,22050 if value['voice']=='ref-sophie' else 48000),'audio/wav')


class VoiceServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self):
        super().__init__(('127.0.0.1',0),VoiceHandler);self.calls=[];self.fail_at=None;self.bad_audio=False
        self.thread=threading.Thread(target=self.serve_forever,daemon=True);self.thread.start()
        self.endpoint=f'http://127.0.0.1:{self.server_port}'
        self.stall=False;self.started=threading.Event();self.release=threading.Event()
    def close(self):self.release.set();self.shutdown();self.server_close();self.thread.join()


def final_script():
    return {'workflow_version':'grounded-editorial-v2','source_quality':'source-review-v4','content_checks_passed':True,'chapters':[
        {'id':'C1','title':'Les bases','opening_transition':'Bienvenue. Découvrons le réseau.',
         'turns':[{'speaker':'Emma','text':'La lumière transporte les données dans la fibre.','idea_ids':['I1']}]}]}


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name);self.server=VoiceServer()
        self.config={**audio_export.defaults(),'endpoint':self.server.endpoint,'voices':{'Sophie':'ref-sophie','Emma':'ref-emma'}}
    def tearDown(self):self.server.close();self.temp.cleanup()
    def renderer(self,cancelled=None):return audio_export.AudioRenderer(self.project,self.config,['Sophie','Emma'],cancelled)
    def test_only_created_voice_profiles_are_offered(self):
        self.assertEqual([v['id'] for v in audio_export.VoiceStudio(self.config).voices()],['ref-sophie','ref-emma'])
    def test_nonlocal_and_credential_urls_are_rejected(self):
        for endpoint in ['https://example.org','http://127.0.0.1:3900/?key=x','http://user:password@localhost:3900','file:///tmp/voice']:
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError):audio_export.settings({'endpoint':endpoint})
        self.assertEqual(audio_export.settings({'endpoint':self.server.endpoint+'/v1'})['endpoint'],self.server.endpoint)
    def test_long_text_is_not_lost_during_chunking(self):
        text=('Une phrase précise conserve ses chiffres, 1,5 dB, et son sens. '*200).strip()
        parts=audio_export.split_text(text)
        self.assertEqual(' '.join(parts),' '.join(text.split()));self.assertTrue(all(len(t)<=900 for t in parts))
    def test_old_unreviewed_script_cannot_be_read_as_final(self):
        value=final_script();value['workflow_version']='grounded-editorial-v1'
        with self.assertRaisesRegex(ValueError,'anciens contrôles'):self.renderer().render(value)
        self.assertFalse(self.server.calls)
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg requis pour ce test média')
    def test_mp3_uses_the_reference_of_each_speaker_and_is_resumable(self):
        value=final_script();self.server.fail_at=2
        with self.assertRaisesRegex(RuntimeError,'503'):self.renderer().render(value)
        self.assertFalse((self.project/'exports/podcast.mp3').exists())
        self.server.fail_at=None;result=self.renderer().render(value)
        self.assertEqual(len(self.server.calls),3)
        self.assertEqual([c['voice'] for c in self.server.calls],['ref-sophie','ref-emma','ref-emma'])
        self.assertTrue(all(c['response_format']=='wav' and c['language']=='fr' for c in self.server.calls))
        self.assertFalse(any('Sophie :' in c['input'] or 'Emma :' in c['input'] for c in self.server.calls))
        self.assertGreater(result['bytes'],1000);self.assertGreater(result['seconds'],.25)
        self.assertEqual(read(self.project/'exports/audio.json')['signature'],audio_export.signature(value,self.config,['Sophie','Emma']))
        before=len(self.server.calls);self.renderer().render(value);self.assertEqual(len(self.server.calls),before)
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg requis pour ce test média')
    def test_missing_profile_does_not_fall_back_to_a_default_voice(self):
        self.config['voices']['Emma']='profile-deleted'
        with self.assertRaisesRegex(ValueError,'introuvable'):self.renderer().render(final_script())
        self.assertFalse(self.server.calls)
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg requis pour ce test média')
    def test_invalid_audio_is_not_saved_as_a_complete_chunk(self):
        self.server.bad_audio=True
        with self.assertRaisesRegex(ValueError,'WAV valide'):self.renderer().render(final_script())
        self.assertFalse(list((self.project/'audio_cache').glob('*.wav')))
        self.assertFalse((self.project/'exports/podcast.mp3').exists())
    def test_cancellation_does_not_contact_the_speech_server(self):
        cancelled=threading.Event();cancelled.set()
        with self.assertRaises(Cancelled):self.renderer(cancelled).client.voices()
        self.assertFalse(self.server.calls)
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg requis pour ce test média')
    def test_cancellation_closes_an_active_voice_http_response(self):
        self.server.stall=True;renderer=self.renderer();errors=[]
        def render():
            try:renderer.render(final_script())
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=render);thread.start()
        try:
            self.assertTrue(self.server.started.wait(5));renderer.cancel();thread.join(5)
            self.assertFalse(thread.is_alive());self.assertIsInstance(errors[0],Cancelled)
            self.assertFalse((self.project/'exports/podcast.mp3').exists())
        finally:self.server.release.set();renderer.cancel();thread.join(5)
    def test_preparation_uses_the_bundled_uv_in_an_unseeded_environment(self):
        with patch('audio_export.encoder',side_effect=[ValueError('absent'),'ffmpeg-ready']), \
             patch('audio_export.Path.exists',return_value=True),patch('audio_export.run_process') as run:
            result=audio_export.prepare_encoder(threading.Event(),lambda _:None)
        self.assertEqual(result,'ffmpeg-ready')
        command=run.call_args.args[0]
        self.assertIn('uv',Path(command[0]).name);self.assertEqual(command[1:4],['pip','install','--python'])
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg requis pour ce test média')
    def test_background_audio_job_keeps_the_text_and_serves_seekable_mp3(self):
        app=App(self.project/'data');http=None
        try:
            identity=app.create({'name':'Audio','settings':defaults()})['id'];folder=app.project(identity)
            write(folder/'exports/podcast.json',final_script());(folder/'exports/podcast.txt').write_text('Texte à conserver.')
            app.save_audio_settings(folder,self.config);task=app.enqueue_audio(folder,{'action':'generate'})
            app.pending.join();state=app.summary(folder)
            self.assertEqual(state['task']['state'],'done',state['task']);self.assertTrue(state['audio']['available'])
            self.assertEqual((folder/'exports/podcast.txt').read_text(),'Texte à conserver.')
            http=Server(('127.0.0.1',0),app);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{http.server_port}/media/{identity}/podcast.mp3'
            request=urllib.request.Request(url,headers={'Range':'bytes=0-63'})
            with urllib.request.urlopen(request) as r:
                self.assertEqual(r.status,206);self.assertEqual(r.headers['Content-Type'],'audio/mpeg');self.assertEqual(len(r.read()),64)
            config={**self.config,'speed':1.2};app.save_audio_settings(folder,config)
            self.assertFalse(app.summary(folder)['audio']['available']);self.assertFalse((folder/'exports/podcast.mp3').exists())
            self.assertTrue(list((folder/'versions').glob('audio-*/podcast.mp3')))
        finally:
            if http:http.shutdown();http.server_close();thread.join()
            app.close()

if __name__=='__main__':unittest.main()
