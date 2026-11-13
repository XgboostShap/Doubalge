"""Voix VoiceStudio locales, reprise par réplique et export MP3."""
import copy
from array import array
import csv
import hashlib
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import wave
from urllib.parse import urlsplit

from llm import Cancelled
from storage import fingerprint, read, write, replace
import quality

VERSION = 'voicestudio-mp3-v2'
RATE = 24000
MAX_CHARS = 900


def defaults():
    return {'endpoint':'http://127.0.0.1:3900','model':'tts-1','voices':{},'speed':1.0,'pause_ms':350,
            'normalize_audio':True,'target_dbfs':-20,'scope_minutes':0}


def settings(value, speakers=()):
    if not isinstance(value,dict):raise ValueError('Paramètres des voix invalides.')
    result={**defaults(),**{k:v for k,v in value.items() if k in defaults()}}
    if not isinstance(result['endpoint'],str):raise ValueError('Adresse VoiceStudio requise.')
    parsed=urlsplit(result['endpoint'].strip())
    if (parsed.scheme not in ('http','https') or parsed.hostname not in ('127.0.0.1','localhost','::1') or
        parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.rstrip('/') not in ('','/v1')):
        raise ValueError('VoiceStudio doit être local : http://127.0.0.1:3900 par exemple.')
    try:parsed.port
    except ValueError:raise ValueError('Port VoiceStudio invalide.') from None
    result['endpoint']=parsed.scheme+'://'+parsed.netloc
    if not isinstance(result['model'],str) or not result['model'].strip() or len(result['model'])>160:raise ValueError('Modèle vocal invalide.')
    result['model']=result['model'].strip()
    if type(result['speed']) not in (float,int) or not .5<=result['speed']<=2:raise ValueError('Vitesse vocale : entre 0,5 et 2.')
    if type(result['pause_ms']) is not int or not 0<=result['pause_ms']<=2000:raise ValueError('Pause : entre 0 et 2 000 ms.')
    if type(result['normalize_audio']) is not bool:raise ValueError('Réglage de volume invalide.')
    if type(result['target_dbfs']) not in (float,int) or not -30<=result['target_dbfs']<=-14:raise ValueError('Volume cible : entre -30 et -14 dBFS.')
    if type(result['scope_minutes']) is not int or result['scope_minutes'] not in (0,3,5):raise ValueError('Choisissez le podcast complet ou un essai de 3 ou 5 minutes.')
    if not isinstance(result['voices'],dict):raise ValueError('Associez chaque intervenant à une voix VoiceStudio.')
    selected={}
    for name,voice in result['voices'].items():
        if not isinstance(name,str) or not name.strip() or len(name)>40:raise ValueError('Nom d’intervenant invalide.')
        if speakers and name not in speakers:continue
        if not isinstance(voice,str) or len(voice)>200 or any(ord(c)<32 for c in voice):raise ValueError('Référence de voix invalide.')
        if voice.strip():selected[name]=voice.strip()
    result['voices']=selected
    return result


class VoiceStudio:
    def __init__(self, config, cancelled=None):
        self.config=settings(config);self.cancelled=cancelled or threading.Event();self.active=None;self.active_socket=None
    def cancel(self):
        self.cancelled.set()
        sock=self.active_socket
        if sock:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
    def request(self,path,body=None,limit=32*1024**2):
        if self.cancelled.is_set():raise Cancelled()
        parsed=urlsplit(self.config['endpoint']);factory=http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection
        conn=factory(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),timeout=900 if body is not None else 15)
        self.active=conn;response=None
        try:
            raw=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
            headers={'Authorization':'Bearer local'}
            if raw is not None:headers['Content-Type']='application/json'
            conn.request('POST' if body is not None else 'GET',path,raw,headers)
            self.active_socket=conn.sock
            response=conn.getresponse()
            if response.status!=200:
                detail=response.read(2500).decode(errors='replace')
                error=RuntimeError('VoiceStudio répond HTTP '+str(response.status)+' : '+detail)
                error.status=response.status
                raise error
            chunks=[];size=0
            while True:
                if self.cancelled.is_set():raise Cancelled()
                chunk=response.read(64*1024)
                if not chunk:break
                size+=len(chunk)
                if size>limit:raise ValueError('Réponse VoiceStudio trop volumineuse pour une réplique.')
                chunks.append(chunk)
            return b''.join(chunks)
        except (OSError,http.client.HTTPException) as error:
            if self.cancelled.is_set():raise Cancelled() from error
            raise RuntimeError('VoiceStudio est inaccessible ou la synthèse a été interrompue. Ouvrez VoiceStudio et vérifiez son adresse API. Détail : '+str(error)) from error
        finally:
            if response is not None:response.close()
            self.active=None;self.active_socket=None;conn.close()
    def voices(self):
        try:value=json.loads(self.request('/v1/audio/voices',limit=2*1024**2))
        except RuntimeError as error:
            if getattr(error,'status',None)!=404:raise
            value=json.loads(self.request('/profiles',limit=2*1024**2))
        rows=value.get('voices',value.get('profiles',[])) if isinstance(value,dict) else value
        if not isinstance(rows,list):raise ValueError('La liste des voix VoiceStudio est invalide.')
        result=[];seen=set()
        for row in rows:
            if not isinstance(row,dict) or row.get('type')=='openai_alias':continue
            identifier=row.get('voice_id') or row.get('id');name=row.get('name') or row.get('voice_name') or identifier
            if not isinstance(identifier,str) or not identifier or not isinstance(name,str) or identifier in seen:continue
            seen.add(identifier);result.append({'id':identifier,'name':name,'language':row.get('language',''),'type':row.get('type','profile')})
        return result
    def health(self):
        try:self.request('/health',limit=2*1024**2)
        except RuntimeError as error:
            if getattr(error,'status',None)!=404:raise
    def speech(self,text,voice):
        if not text.strip() or len(text)>MAX_CHARS:raise ValueError('Réplique audio vide ou trop longue.')
        raw=self.request('/v1/audio/speech',{'model':self.config['model'],'input':text,'voice':voice,
            'response_format':'wav'})
        if len(raw)<44 or raw[:4]!=b'RIFF' or raw[8:12]!=b'WAVE':raise ValueError('VoiceStudio n’a pas renvoyé un fichier WAV valide.')
        return raw


def split_text(text):
    """Conserver toutes les phrases et tous les mots, avec une borne par appel."""
    parts=[];current=''
    for sentence in re.split(r'(?<=[.!?;])\s+',text.strip()):
        for word in sentence.split():
            if len(word)>MAX_CHARS:raise ValueError('Un mot du script est trop long pour être lu.')
            if len(current)+len(word)+1>MAX_CHARS:parts.append(current);current=''
            current=(current+' '+word).strip()
    if current:parts.append(current)
    return parts


def script_segments(final,speakers):
    result=[]
    for chapter in final['chapters']:
        if chapter['opening_transition'].strip():result.append({'speaker':speakers[0],'text':chapter['opening_transition'],'chapter':chapter['id'],'chapter_start':True})
        result.extend({'speaker':t['speaker'],'text':t['text'],'chapter':chapter['id'],'chapter_start':False} for t in chapter['turns'])
    if not result or any(r['speaker'] not in speakers or not isinstance(r['text'],str) or not r['text'].strip() for r in result):raise ValueError('Script audio incomplet ou intervenant inconnu.')
    return result

def selected_segments(final,config,speakers):
    segments=script_segments(final,speakers);minutes=config.get('scope_minutes',0)
    if not minutes:return segments
    chosen=[];count=0;budget=round(minutes*125*config.get('speed',1))
    for segment in segments:
        chosen.append(segment);count+=len(segment['text'].split())
        if count>=budget:break
    return chosen

def output_names(scope):
    stem='podcast' if scope==0 else 'essai-'+str(scope)+'min'
    return stem+'.mp3',('audio.json' if scope==0 else stem+'.json'),('rapport_audio.csv' if scope==0 else 'rapport_'+stem+'.csv')

def validate_script(final):
    if final.get('source_kind')=='provided_text':
        import voice_legacy
        fresh=voice_legacy.parse_dialogue(final.get('source_text',''))
        if fresh['input_hash']!=final.get('input_hash') or fresh['chapters']!=final.get('chapters') or fresh['speakers']!=final.get('speakers'):raise ValueError('Le texte audio a changé : réenregistrer le dialogue avant la lecture.')
        return
    if final.get('workflow_version')!='grounded-editorial-v2' or final.get('source_quality')!=quality.VERSION or not final.get('content_checks_passed'):
        raise ValueError('Ce script utilise les anciens contrôles. Réexaminez les résumés et reconstruisez le dialogue avant de générer le MP3.')

def pcm_stats(path):
    total=0;squares=0;peak=0
    with wave.open(str(path),'rb') as wav:
        while raw:=wav.readframes(64000):
            samples=array('h');samples.frombytes(raw)
            if sys.byteorder!='little':samples.byteswap()
            total+=len(samples);squares+=sum(s*s for s in samples)
            peak=max(peak,max((abs(s) for s in samples),default=0))
    if not total or not peak:raise ValueError('VoiceStudio a produit une réplique vide ou silencieuse.')
    return 20*math.log10(math.sqrt(squares/total)/32768),20*math.log10(peak/32768)


def signature(final,config,speakers):
    return fingerprint({'version':VERSION,'source_kind':final.get('source_kind','project'),'script':script_segments(final,speakers),'settings':settings(config,speakers)})


def encoder():
    executable=shutil.which('ffmpeg')
    if executable:return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError,RuntimeError):raise ValueError('Le moteur MP3 n’est pas encore préparé. Cliquez sur « Préparer le MP3 » (Internet nécessaire la première fois).') from None


def run_process(command,cancelled):
    if cancelled.is_set():raise Cancelled()
    with tempfile.TemporaryFile() as log:
        proc=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            while proc.poll() is None:
                if cancelled.wait(.1):
                    proc.terminate()
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()
                    raise Cancelled()
            if proc.returncode:
                log.seek(0);detail=log.read()[-3000:].decode(errors='replace')
                raise RuntimeError('Le traitement audio a échoué : '+detail)
        finally:
            if proc.poll() is None:proc.kill();proc.wait()


def prepare_encoder(cancelled,progress):
    try:return encoder()
    except ValueError:pass
    progress('Installation du moteur MP3 — premier téléchargement')
    uv=Path(__file__).resolve().parent/'.runtime'/('uv.exe' if os.name=='nt' else 'uv')
    if uv.exists():command=[str(uv),'pip','install','--python',sys.executable,'imageio-ffmpeg==0.6.0']
    else:
        if importlib.util.find_spec('pip') is None:
            run_process([sys.executable,'-m','ensurepip','--upgrade'],cancelled)
        command=[sys.executable,'-m','pip','install','--disable-pip-version-check','imageio-ffmpeg==0.6.0']
    run_process(command,cancelled)
    return encoder()


class AudioRenderer:
    def __init__(self,project,config,speakers,cancelled=None,progress=None):
        self.project=Path(project);self.config=settings(config,speakers);self.speakers=speakers
        self.cancelled=cancelled or threading.Event();self.progress=progress or (lambda _:None)
        self.client=VoiceStudio(self.config,self.cancelled)
    def cancel(self):self.client.cancel()
    def validate_voices(self,names):
        self.client.health()
        available={v['id'] for v in self.client.voices()}
        for name in names:
            voice=self.config['voices'].get(name)
            if not voice:raise ValueError('Choisissez la voix VoiceStudio de '+name+'.')
            if voice not in available:raise ValueError('La référence de voix de '+name+' est introuvable dans VoiceStudio. Rechargez la liste et choisissez son profil.')
    def chunk(self,text,voice,ffmpeg):
        key=fingerprint({'protocol':VERSION,'endpoint':self.config['endpoint'],'model':self.config['model'],
            'voice':voice,'speed':self.config['speed'],'text':text,'rate':RATE,
            'normalize_audio':self.config['normalize_audio'],'target_dbfs':self.config['target_dbfs']})
        cache=self.project/'audio_cache';cache.mkdir(exist_ok=True)
        path=cache/(key+'.wav');meta=path.with_suffix('.json')
        if path.exists() and meta.exists():
            try:
                expected=read(meta)
                if hashlib.sha256(path.read_bytes()).hexdigest()==expected['sha256']:
                    with wave.open(str(path),'rb') as wav:
                        if wav.getframerate()==RATE and wav.getnchannels()==1 and wav.getsampwidth()==2:return path,wav.getnframes()
            except (OSError,ValueError,KeyError,wave.Error):pass
        self.progress('Synthèse avec la voix choisie — '+str(len(text))+' caractères')
        raw=self.client.speech(text,voice)
        with tempfile.TemporaryDirectory(prefix='replique-',dir=cache) as temporary:
            temporary=Path(temporary);source=temporary/'source.wav';source.write_bytes(raw);normalized=temporary/'normalise.wav'
            tempo=['-af','atempo='+str(self.config['speed'])] if self.config['speed']!=1 else []
            run_process([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(source),*tempo,'-ar',str(RATE),'-ac','1','-c:a','pcm_s16le',str(normalized)],self.cancelled)
            with wave.open(str(normalized),'rb') as wav:frames=wav.getnframes()
            mean,peak=pcm_stats(normalized)
            if self.config['normalize_audio']:
                gain=min(max(-18,min(18,self.config['target_dbfs']-mean)),-1-peak)
                adjusted=temporary/'volume.wav'
                run_process([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(normalized),'-af','volume='+str(round(gain,4))+'dB','-c:a','pcm_s16le',str(adjusted)],self.cancelled)
                replace(adjusted,normalized)
            replace(normalized,path)
        write(meta,{'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'frames':frames})
        return path,frames
    def compose(self,segments,destination):
        ffmpeg=encoder();self.validate_voices({s['speaker'] for s in segments})
        (self.project/'audio_cache').mkdir(exist_ok=True)
        destination.parent.mkdir(exist_ok=True,parents=True)
        total_frames=0;count=0;rows=[];warnings=[]
        with tempfile.TemporaryDirectory(prefix='montage-',dir=self.project/'audio_cache') as temporary:
            temporary=Path(temporary);joined=temporary/'podcast.wav'
            with wave.open(str(joined),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(RATE)
                for index,segment in enumerate(segments,1):
                    if self.cancelled.is_set():raise Cancelled()
                    self.progress('Audio — réplique '+str(index)+'/'+str(len(segments))+' — '+segment['speaker'])
                    gap=800 if segment.get('chapter_start') and index>1 else self.config['pause_ms'] if index>1 else 0
                    silence=round(RATE*gap/1000)
                    if silence:out.writeframes(b'\0\0'*silence);total_frames+=silence
                    reply_frames=0
                    for text in split_text(segment['text']):
                        path,frames=self.chunk(text,self.config['voices'][segment['speaker']],ffmpeg)
                        with wave.open(str(path),'rb') as wav:
                            while raw:=wav.readframes(64*1024):
                                if self.cancelled.is_set():raise Cancelled()
                                out.writeframes(raw)
                        total_frames+=frames;reply_frames+=frames;count+=1
                    seconds=reply_frames/RATE;word_count=len(segment['text'].split())
                    warning=''
                    if word_count>=12 and (seconds<word_count/(6.5*self.config['speed']) or seconds>word_count/(.5*self.config['speed'])):
                        warning='Durée atypique : vérifier à l’écoute que la réplique est complète.'
                        warnings.append('Réplique '+str(index)+' ('+segment['speaker']+') : '+warning)
                    rows.append({'reply':index,'speaker':segment['speaker'],'words':word_count,'seconds':round(seconds,2),'warning':warning})
            self.progress('Assemblage du podcast et encodage MP3')
            output=temporary/'podcast.mp3'
            run_process([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(joined),'-c:a','libmp3lame','-b:a','192k','-id3v2_version','3',str(output)],self.cancelled)
            if self.cancelled.is_set():raise Cancelled()
            replace(output,destination)
        return {'seconds':round(total_frames/RATE,2),'chunks':count,'bytes':destination.stat().st_size,
                'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'rows':rows,'warnings':warnings}
    def render(self,final):
        validate_script(final)
        (self.project/'audio_cache').mkdir(exist_ok=True)
        audio_name,meta_name,csv_name=output_names(self.config['scope_minutes'])
        result=self.compose(selected_segments(final,self.config,self.speakers),self.project/'exports'/audio_name)
        result.update(signature=signature(final,self.config,self.speakers),voices=copy.deepcopy(self.config['voices']),version=VERSION,
            source_kind=final.get('source_kind','project'),scope_minutes=self.config['scope_minutes'],filename=audio_name,report_file=csv_name)
        from storage import write_text
        import io
        buffer=io.StringIO();writer=csv.writer(buffer,delimiter=';');writer.writerow(['Réplique','Voix','Mots','Durée (s)','Alerte'])
        for row in result['rows']:writer.writerow([row[k] for k in ('reply','speaker','words','seconds','warning')])
        write_text(self.project/'exports'/csv_name,'\ufeff'+buffer.getvalue())
        write(self.project/'exports'/meta_name,result)
        return result
    def preview(self,speaker):
        if speaker not in self.speakers:raise ValueError('Intervenant inconnu.')
        (self.project/'audio_cache').mkdir(exist_ok=True)
        result=self.compose([{'speaker':speaker,'text':'Bonjour. Voici un aperçu de cette voix pour le podcast.'}],self.project/'audio_cache/apercu.mp3')
        result.update(speaker=speaker,settings_hash=fingerprint(self.config));write(self.project/'audio_cache/apercu.json',result)
        return result
