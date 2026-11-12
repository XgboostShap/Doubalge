"""Interface locale du générateur PDF → podcast pédagogique."""
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import secrets
import signal
import threading
import time
from urllib.parse import parse_qs, unquote, urlsplit
import uuid
import webbrowser
import zipfile

from llm import Ollama, Cancelled, endpoint_parts, models
import pipeline as pipeline_module
from pipeline import Pipeline, STEPS
from storage import defaults, fingerprint, invalidate, read, write

ROOT = Path(__file__).resolve().parent
APP_VERSION = '0.1.10'


def settings(value):
    if not isinstance(value,dict):
        raise ValueError('Paramètres invalides.')
    result = defaults()
    result.update({k:v for k,v in value.items() if k in result})
    for key in ('endpoint','model','audience'):
        if not isinstance(result[key],str) or not result[key].strip() or len(result[key])>2000:
            raise ValueError('Champ invalide : '+key)
        result[key] = result[key].strip()
    endpoint_parts(result['endpoint'])
    if type(result['minutes']) is not int or not 3<=result['minutes']<=180:
        raise ValueError('Choisissez une durée entre 3 et 180 minutes.')
    if type(result['num_ctx']) is not int or not 8192<=result['num_ctx']<=131072:
        raise ValueError('Le contexte doit être compris entre 8192 et 131072 tokens.')
    if type(result['temperature']) not in (float,int) or not 0<=result['temperature']<=1:
        raise ValueError('Température invalide.')
    people = result['speakers']
    if not isinstance(people,list) or not 2<=len(people)<=3 or any(not isinstance(p,str) or not p.strip() or len(p)>40 or '\n' in p or '\r' in p for p in people):
        raise ValueError('Indiquez deux ou trois intervenants, séparés par des virgules.')
    result['speakers'] = [p.strip() for p in people]
    if len(set(result['speakers']))!=len(people):
        raise ValueError('Les noms des intervenants doivent être différents.')
    return result


class Busy(ValueError):
    pass


class App:
    def __init__(self, directory, client_factory=Ollama):
        self.directory = Path(directory).resolve()
        self.projects = self.directory/'projets';self.projects.mkdir(parents=True,exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.pending = queue.Queue()
        self.stop = threading.Event()
        self.cancels = {}
        self.task_errors = {}
        self.active = None
        self.runtime = {'version':APP_VERSION,'page_sources':getattr(pipeline_module,'SOURCE_PAGE_MODE','legacy'),
                        'summary_quality':getattr(pipeline_module,'SUMMARY_QUALITY_MODE','legacy'),
                        'app_dir':str(ROOT),'pid':os.getpid()}
        self.client_factory = client_factory
        for path in self.projects.glob('*/tache.json'):
            task = read(path)
            if task['state'] in ('running','queued'):
                task.update(state='interrupted',message='Interrompu à la fermeture. Les étapes terminées sont conservées.')
                write(path,task)
        self.worker = threading.Thread(target=self._loop,daemon=True);self.worker.start()

    def project(self, identifier):
        if not re.fullmatch('[a-f0-9]{32}',identifier):
            raise ValueError('Identifiant de projet invalide.')
        folder = self.projects/identifier
        if not (folder/'projet.json').is_file():
            raise FileNotFoundError('Projet introuvable.')
        return folder

    def idle(self, folder):
        path = folder/'tache.json'
        task = self.task_errors.get(folder.name) or (read(path) if path.exists() else {})
        if task.get('state') in ('queued','running'):
            raise Busy('Un traitement est en cours pour ce projet. Attendez sa fin ou annulez-le.')

    def create(self, body):
        if not isinstance(body.get('name'),str) or not body['name'].strip():
            raise ValueError('Donnez un nom au projet.')
        folder = self.projects/uuid.uuid4().hex
        folder.mkdir();(folder/'sources').mkdir()
        write(folder/'projet.json',{'id':folder.name,'name':body['name'].strip()[:150],
              'created':time.time(),'settings':settings(body.get('settings',{})),'pdfs':[]})
        return {'id':folder.name}

    def summary(self, folder):
        meta = read(folder/'projet.json')
        completed = [n for n in range(1,10) if (folder/'etapes'/f'{n:02}.json').exists()]
        task = self.task_errors.get(folder.name) or (read(folder/'tache.json') if (folder/'tache.json').exists() else None)
        if task and task['state']=='error' and task.get('app_version')!=APP_VERSION:
            task={**task,'message':'Ancien échec enregistré — cliquez sur Continuer pour reprendre avec la version '+APP_VERSION,
                  'from_previous_version':True}
        exports = [p.name for p in (folder/'exports').glob('podcast.*') if p.suffix in ('.md','.txt','.json')]
        parts = [p.name for p in sorted((folder/'etapes'/'parties').glob('*.md'))
                 if re.fullmatch(r'0[1-9]-[A-Za-z0-9-]+\.md',p.name) and p.with_suffix('.json').exists()]
        return {**meta,'completed':completed,'task':task,'exports':exports,'parts':parts,
                'next_step':next((n for n in range(1,10) if n not in completed),10)}

    def state(self):
        with self.lock:
            projects = [self.summary(p) for p in self.projects.iterdir() if p.is_dir() and re.fullmatch('[a-f0-9]{32}',p.name)]
            return {'token':self.token,'defaults':defaults(),'steps':STEPS,'runtime':self.runtime,
                    'projects':sorted(projects,key=lambda p:p['created'],reverse=True)}

    def enqueue(self, folder, body):
        with self.lock:
            if self.runtime['page_sources']!='pdf-page-v1':
                raise ValueError('Mise à jour incomplète : pipeline.py est encore ancien. Fermez le programme et utilisez Mettre-a-jour.cmd dans le correctif.')
            if self.runtime['summary_quality']!='source-review-v2':
                raise ValueError('Mise à jour incomplète : les contrôles de synthèse sont absents. Fermez le programme et utilisez le nouveau correctif.')
            self.idle(folder)
            meta = read(folder/'projet.json')
            if not meta['pdfs']:
                raise ValueError('Ajoutez au moins un PDF.')
            first, until = body.get('first',1), body.get('until',9)
            if type(first) is not int or type(until) is not int or not 1<=first<=until<=9:
                raise ValueError('Étapes invalides.')
            if first>1 and not (folder/'etapes'/f'{first-1:02}.json').exists():
                raise ValueError('L’étape précédente doit être terminée.')
            regenerate,refine = body.get('regenerate',False),body.get('refine',False)
            if type(regenerate) is not bool or type(refine) is not bool:
                raise ValueError('Option de régénération invalide.')
            if refine:
                if first!=2 or until!=2 or regenerate or not (folder/'etapes'/'02.json').exists():
                    raise ValueError('L’amélioration réutilise une étape 2 terminée, sans régénération forcée.')
                # Copie privée de l'extraction AVANT l'archivage des résultats.
                self.preserve_summaries(folder,meta)
            task = {'id':uuid.uuid4().hex,'first':first,'until':until,'state':'queued',
                    'message':'En attente','error':None,'regenerate':regenerate,'refine':refine,'app_version':APP_VERSION}
            cancel = threading.Event();self.cancels[task['id']] = cancel
            write(folder/'tache.json',task)
            self.task_errors.pop(folder.name,None)
            self.pending.put((folder,task,cancel))
            return task

    def _loop(self):
        while not self.stop.is_set():
            try:
                folder,task,cancel = self.pending.get(timeout=.2)
            except queue.Empty:
                continue
            client = None
            try:
                if cancel.is_set():
                    raise Cancelled()
                meta = read(folder/'projet.json')
                if task['regenerate']:
                    meta['cache_generation'] = uuid.uuid4().hex
                    write(folder/'projet.json',meta)
                config = {**meta['settings'],'_generation':meta.get('cache_generation','initial')}
                def progress(message):
                    task['message'] = message
                    match=re.match(r'Étape (\d+)/9',message)
                    if match:task['step']=int(match.group(1))
                    write(folder/'tache.json',task)
                task['state']='running';progress('Préparation du traitement')
                # Une simple reprise conserve les parties finies dans l'étape en cours.
                # Leurs empreintes contrôlent les paramètres et données d'origine.
                invalidate(folder,task['first'],partials=task['regenerate'] or task.get('refine',False))
                client = self.client_factory(config,folder/'cache',cancel,progress)
                self.active = (task['id'],client)
                Pipeline(folder,client,cancel,progress).run(task['first'],task['until'])
                task.update(state='done',message='Étapes terminées et enregistrées')
            except Cancelled:
                task.update(state='cancelled',message='Annulé. Les parties Markdown terminées et les réponses en cache sont conservées.')
            except Exception as error:
                task.update(state='error',message='Traitement arrêté',error=str(error)[-5000:])
            finally:
                self.active = None
                try:
                    write(folder/'tache.json',task)
                except OSError as error:
                    # Une erreur persistante de fichier ne doit pas tuer le worker
                    # ni laisser l'interface afficher « en cours » indéfiniment.
                    failed = {**task,'state':'error','message':'Enregistrement de l’avancement impossible',
                              'error':'Le fichier tache.json reste inaccessible. Fermez les autres fenêtres du programme, puis relancez. Détail : '+str(error)}
                    with self.lock:
                        self.task_errors[folder.name]=failed
                finally:
                    self.cancels.pop(task['id'],None)
                    self.pending.task_done()

    def cancel(self, folder):
        task = read(folder/'tache.json')
        event = self.cancels.get(task['id'])
        if event:
            event.set()
            if self.active and self.active[0]==task['id']:
                self.active[1].cancel()
        return {'cancel_requested':bool(event)}

    def update_settings(self, folder, body):
        with self.lock:
            self.idle(folder)
            meta = read(folder/'projet.json')
            new = settings(body)
            changed = {k for k in new if new[k]!=meta['settings'][k]}
            first = 10
            for key in changed:
                first = min(first,8 if key=='speakers' else 5 if key=='minutes' else 4 if key=='audience' else 2)
            if first<=9:
                if first==2:self.preserve_summaries(folder,meta)
                invalidate(folder,first)
                meta['settings']=new
                write(folder/'projet.json',meta)
            return {'invalidated_from':first if first<=9 else None}

    def preserve_summaries(self, folder, meta):
        if (folder/'etapes/01.json').exists() and (folder/'etapes/02.json').exists():
            write(folder/'reprises/02.json',{'source':fingerprint(read(folder/'etapes/01.json')['data']),
                  'generation':meta.get('cache_generation','initial'),'data':read(folder/'etapes/02.json')['data']})

    def close(self):
        self.stop.set()
        if self.active:
            self.active[1].cancel()
        self.worker.join(timeout=5)


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,app):
        self.app=app
        super().__init__(address,Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):
        pass

    @property
    def app(self):
        return self.server.app

    def respond(self,status,raw,mime='application/json; charset=utf-8',extra=()):
        self.send_response(status)
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header('Referrer-Policy','no-referrer')
        for key,value in extra:self.send_header(key,value)
        self.end_headers();self.wfile.write(raw)

    def json(self,value,status=200):
        self.respond(status,json.dumps(value,ensure_ascii=False,allow_nan=False).encode())

    def authorized(self,write_request=False):
        port=self.server.server_port
        if self.headers.get('Host') not in (f'127.0.0.1:{port}',f'localhost:{port}'):
            self.json({'error':'Adresse locale invalide.'},403);return False
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):
            self.json({'error':'Origine non autorisée.'},403);return False
        if write_request and not hmac.compare_digest(self.headers.get('X-Podcast-Token',''),self.app.token):
            self.json({'error':'Rechargez la page pour continuer.'},403);return False
        return True

    def size(self,maximum):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Content-Length requis.')
        size=int(self.headers.get('Content-Length','-1'))
        if not 0<=size<=maximum:
            raise ValueError('Taille de requête invalide ou trop importante.')
        return size

    def body(self):
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            raise ValueError('Requête JSON requise.')
        value=json.loads(self.rfile.read(self.size(1024*1024)))
        if not isinstance(value,dict):raise ValueError('Objet JSON requis.')
        return value

    def do_GET(self):
        if not self.authorized():return
        try:
            path=urlsplit(self.path).path
            if path=='/api/state':self.json(self.app.state());return
            static={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if path in static:
                name,mime=static[path];self.respond(200,(ROOT/'web'/name).read_bytes(),mime);return
            parts=path.split('/')
            if len(parts)==6 and parts[1:3]==['api','projects'] and parts[4]=='stages':
                folder=self.app.project(parts[3]);number=int(parts[5])
                if not 1<=number<=9:raise ValueError('Étape invalide.')
                self.json({'markdown':(folder/'etapes'/f'{number:02}.md').read_text(encoding='utf-8')});return
            if len(parts)==4 and parts[1]=='files':
                folder=self.app.project(parts[2]);name=parts[3]
                if re.fullmatch(r'0[1-9]\.(md|json)',name):file=folder/'etapes'/name
                elif re.fullmatch(r'partie-0[1-9]-[A-Za-z0-9-]+\.md',name):
                    file=folder/'etapes'/'parties'/name.removeprefix('partie-')
                    if not file.with_suffix('.json').exists():raise FileNotFoundError('Partie non terminée.')
                elif name in ('podcast.md','podcast.txt','podcast.json'):file=folder/'exports'/name
                elif name=='dossier.zip':
                    self.app.idle(folder)
                    file=folder/'dossier.zip'
                    with zipfile.ZipFile(file,'w',zipfile.ZIP_DEFLATED) as archive:
                        archive.write(folder/'projet.json','projet.json')
                        for sub in ('sources','etapes','memoire','exports','reprises'):
                            for f in (folder/sub).rglob('*'):
                                if f.is_file():archive.write(f,f.relative_to(folder))
                else:raise FileNotFoundError('Fichier inconnu.')
                self.send_file(file);return
            raise FileNotFoundError('Page introuvable.')
        except (BrokenPipeError,ConnectionResetError):pass
        except Busy as error:self.json({'error':str(error)},409)
        except (ValueError,OSError) as error:self.json({'error':str(error)},404)

    def send_file(self,path):
        if not path.is_file():raise FileNotFoundError('Le résultat n’est pas encore disponible.')
        mime='application/zip' if path.suffix=='.zip' else 'application/json' if path.suffix=='.json' else 'text/plain; charset=utf-8'
        self.send_response(200);self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(path.stat().st_size))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Disposition',f'attachment; filename="{path.name}"')
        self.end_headers()
        with path.open('rb') as f:
            while chunk:=f.read(256*1024):self.wfile.write(chunk)

    def do_POST(self):
        if not self.authorized(True):return
        try:
            self.connection.settimeout(120)
            path=urlsplit(self.path).path
            if path=='/api/models':self.json({'models':models(self.body().get('endpoint',defaults()['endpoint']))});return
            if path=='/api/projects':self.json(self.app.create(self.body()),201);return
            parts=path.split('/')
            if len(parts)!=5 or parts[1:3]!=['api','projects']:raise FileNotFoundError('Commande inconnue.')
            folder=self.app.project(parts[3]);action=parts[4]
            if action=='pdf':self.upload(folder);return
            body=self.body()
            if action=='run':self.json(self.app.enqueue(folder,body),202)
            elif action=='cancel':self.json(self.app.cancel(folder))
            elif action=='settings':self.json(self.app.update_settings(folder,body))
            else:raise FileNotFoundError('Commande inconnue.')
        except (BrokenPipeError,ConnectionResetError):pass
        except Busy as error:self.json({'error':str(error)},409)
        except FileNotFoundError as error:self.json({'error':str(error)},404)
        except (ValueError,KeyError,TypeError) as error:self.json({'error':str(error)},400)
        except (OSError,RuntimeError) as error:self.json({'error':str(error)},502)

    def upload(self,folder):
        with self.app.lock:
            self.app.idle(folder)
            if any((folder/'etapes').glob('*.json')):raise Busy('Créez un nouveau projet pour changer les PDF après le début du traitement.')
            size=self.size(100*1024**2)
            if size<5:raise ValueError('Le PDF est vide ou invalide.')
            name=unquote(self.headers.get('X-Filename','document.pdf')).replace('\\','/').split('/')[-1][:200]
            if not name.lower().endswith('.pdf'):raise ValueError('Choisissez un fichier PDF.')
            target=folder/'sources'/(uuid.uuid4().hex+'.pdf')
            digest=hashlib.sha256()
            try:
                with target.open('wb') as f:
                    first=self.rfile.read(5)
                    if first!=b'%PDF-':raise ValueError('Le fichier ne possède pas un en-tête PDF valide.')
                    f.write(first);digest.update(first);remaining=size-5
                    while remaining:
                        data=self.rfile.read(min(1024**2,remaining))
                        if not data:raise ValueError('Copie du PDF interrompue.')
                        f.write(data);digest.update(data);remaining-=len(data)
                meta=read(folder/'projet.json')
                if len(meta['pdfs'])>=30:raise ValueError('Maximum de 30 PDF par projet.')
                if any(p['sha256']==digest.hexdigest() for p in meta['pdfs']):raise ValueError('Ce PDF est déjà présent dans le projet.')
                meta['pdfs'].append({'file':target.name,'name':name,'sha256':digest.hexdigest(),'bytes':size})
                write(folder/'projet.json',meta)
            except Exception:
                target.unlink(missing_ok=True);raise
            self.json({'uploaded':size})


def main():
    parser=argparse.ArgumentParser(description='Podcast pédagogique local à partir de PDF')
    parser.add_argument('--data',type=Path,default=ROOT/'donnees')
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args();app=App(args.data)
    def interrupt(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,interrupt)
    try:
        try:server=Server(('127.0.0.1',args.port),app)
        except OSError:server=Server(('127.0.0.1',0),app)
        url=f'http://127.0.0.1:{server.server_port}/'
        print('Podcast pédagogique : '+url,flush=True)
        print('Gardez cette fenêtre ouverte. Ctrl+C pour arrêter.',flush=True)
        if not args.no_browser:webbrowser.open(url)
        try:server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:pass
        finally:server.server_close()
    finally:app.close()


if __name__=='__main__':main()
