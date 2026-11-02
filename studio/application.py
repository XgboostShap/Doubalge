"""Fenêtre Doubalge et pont Python direct, sans serveur HTTP pour l'application."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import uuid

from export_html import TEMPLATES, ecrire_json, exporter, serialiser_html
from export_mp4 import Cancelled, render
from projet_local import Projet
from serveur_editeur import load_document

ROOT = Path(__file__).resolve().parent.parent
STUDIO = Path(__file__).resolve().parent


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
    else:
        try:
            os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:
            pass


class Application:
    def __init__(self):
        self._window = None
        self._project = None
        self._session = None
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._worker = None
        self._process = None
        self._state = {'status':'idle','progress':0,'logs':[]}
        self._temp = tempfile.TemporaryDirectory(prefix='doubalge-app-')
        self._allow_close = False
        self._page = 'home'
        self._ui = Path(self._temp.name)
        self._home = self._ui/'accueil.html'
        self._home.write_text((STUDIO/'app-layout.html').read_text(encoding='utf-8'),encoding='utf-8')
        self._approved = {}  # Les chemins viennent des dialogues natifs, pas du contenu importé.

    def _choose(self, kind, title, types=(), filename=''):
        import webview
        mode = {'file':webview.FileDialog.OPEN,'folder':webview.FileDialog.FOLDER,'save':webview.FileDialog.SAVE}[kind]
        result = self._window.create_file_dialog(mode,directory=str(ROOT),save_filename=filename,
                                                file_types=types,allow_multiple=False)
        if not result:
            return None
        return str(result[0] if isinstance(result,(list,tuple)) else result)

    def _require(self, session):
        if self._project is None or session != self._session:
            raise ValueError('Ce document appartient à un autre projet. Rouvrez le projet courant.')
        return self._project

    def _idle(self):
        if self._worker and self._worker.is_alive():
            raise ValueError('Un traitement est encore en cours. Annulez-le avant de changer de projet.')

    def _editor(self, project):
        project.acquire()
        if self._project and self._project is not project:
            self._project.release()
        self._project,self._session = project,uuid.uuid4().hex
        data = project.document()
        data['improTemplate'] = (TEMPLATES/'impro.html').read_text(encoding='utf-8')
        data['showTemplate'] = (TEMPLATES/'spectacle.html').read_text(encoding='utf-8')
        html = (TEMPLATES/'editeur.html').read_text(encoding='utf-8').replace('__EDITOR_DATA__',serialiser_html(data))
        settings = serialiser_html({'session':self._session,'project':str(project.path)})
        adapter = (STUDIO/'desktop.js').read_text(encoding='utf-8')
        html = html.replace('<head>','<head><script>globalThis.DOUBALGE_DESKTOP='+settings+';\n'+adapter+'</script>',1)
        editor = self._ui/'editeur.html'
        editor.write_text(html,encoding='utf-8')
        self._page = 'editor'
        self._window.load_url(editor.as_uri())
        return {'project':str(project.path),'session':self._session}

    def open_project(self):
        with self._lock:
            self._idle()
            path = self._choose('file','Ouvrir un projet',('Projet Doubalge (*.doubalge)',))
            return self._editor(Projet(path)) if path else None

    def import_editor(self):
        with self._lock:
            self._idle()
            source = self._choose('file','Importer une ancienne scène',('Éditeur HTML (*.html)',))
            if not source:
                return None
            document = load_document(source)  # On lit seulement le JSON ; aucun ancien script n'est exécuté.
            parent = self._choose('folder','Dossier où conserver le nouveau projet')
            if not parent:
                return None
            folder = Path(parent)/('scene-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            return self._editor(Projet.create(folder,document))

    def save_project(self, session, edits):
        with self._lock:
            project = self._require(session)
            return {'savedAt':project.save(edits),'project':str(project.path)}

    def import_corrections(self, session):
        with self._lock:
            project = self._require(session)
            source = self._choose('file','Importer des corrections',('Corrections JSON (*.json)',))
            if not source:
                return None
            edits = project.validate(json.loads(Path(source).read_text(encoding='utf-8-sig')))
            project.save(edits)
            return edits

    def export_json(self, session, edits):
        with self._lock:
            project = self._require(session)
            project.save(edits)
            path = self._choose('save','Copie indépendante des corrections',('Corrections JSON (*.json)',),
                                'timeline-corrigee-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
            if path:
                ecrire_json(Path(path),project.edits)
            return path

    def export_html(self, session, edits, kind):
        with self._lock:
            project = self._require(session)
            if kind not in ('player','show'):
                raise ValueError('Export inconnu.')
            project.save(edits)
            path = self._choose('save','Exporter pour le spectacle' if kind == 'show' else 'Exporter le lecteur autonome',
                                ('Lecteur HTML (*.html)',),'spectacle.html' if kind == 'show' else 'version-impro.html')
            if not path:
                return None
            with tempfile.TemporaryDirectory(dir=self._temp.name) as work:
                document = project.document()
                document['exportedAt'] = datetime.now(timezone.utc).isoformat()
                _,player = exporter(document,Path(work))
                source = Path(work)/'Spectacle.html' if kind == 'show' else player
                self._copy(source,Path(path))
            return path

    @staticmethod
    def _copy(source,destination):
        temporary = destination.with_name(destination.name+'.partial')
        try:
            shutil.copyfile(source,temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _job(self, task):
        self._idle()
        self._cancel.clear()
        self._state = {'status':'running','progress':0,'logs':[]}
        def work():
            try:
                path = task()
                if self._cancel.is_set():
                    raise Cancelled()
                self._state.update(status='done',progress=1,path=str(path))
            except Cancelled:
                self._state.update(status='cancelled')
            except Exception as error:
                self._state.update(status='error',error=str(error))
        self._worker = threading.Thread(target=work,daemon=True)
        self._worker.start()
        return {'status':'running'}

    def start_export(self, session, request):
        with self._lock:
            self._idle()
            project = self._require(session)
            edits = project.validate(request['edits'])
            if len(edits['audioMix']['removedCharacters']) not in (1,2):
                raise ValueError('Choisissez une ou deux voix à doubler.')
            if request.get('profile') not in ('mail','standard'):
                raise ValueError('Profil inconnu.')
            project.save(request['edits'])
            path = self._choose('save','Enregistrer la vidéo d’entraînement',('Vidéo MP4 (*.mp4)',),
                                'entrainement-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.mp4')
            if not path:
                raise ValueError('Enregistrement annulé.')
            document = project.document()
            request = copy.deepcopy(request)
            def task():
                with tempfile.TemporaryDirectory(dir=self._temp.name) as work:
                    output = render(document,request,work,self._cancel,lambda n:self._state.update(progress=n))
                    if self._cancel.is_set():
                        raise Cancelled()
                    self._copy(output,Path(path))
                return path
            return self._job(task)

    def job_status(self):
        return copy.deepcopy(self._state)

    def cancel_job(self):
        self._cancel.set()
        stop_process(self._process)
        return True

    def choose_source(self, field):
        choices = {'video':('Vidéo locale',('Vidéos (*.mp4;*.mkv;*.mov;*.avi;*.webm)',)),
                   'timeline':('Timeline existante',('JSON (*.json)',)),
                   'corrections':('Corrections prioritaires',('JSON (*.json)',))}
        if field not in choices:
            raise ValueError('Choix inconnu.')
        title,types = choices[field]
        path = self._choose('file',title,types)
        if path:
            self._approved[field] = path
        return path

    def prepare(self, options):
        with self._lock:
            self._idle()
            source = str(options.get('source','')).strip()
            if not source:
                raise ValueError('Choisissez une vidéo ou une URL YouTube.')
            if not source.startswith(('https://','http://')) and source != self._approved.get('video'):
                raise ValueError('Choisissez la vidéo avec le bouton Parcourir.')
            parent = self._choose('folder','Dossier où conserver le nouveau projet')
            if not parent:
                return None
            folder = Path(parent)/('scene-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            output = folder/'preparation'
            folder.mkdir()
            command = [sys.executable,'-X','utf8','-u',str(STUDIO/'lancer_studio.py'),'--sans-ouvrir',
                       '--video',source,'--sortie',str(output)]
            for name in ('timeline','corrections'):
                if options.get(name):
                    if options[name] != self._approved.get(name):
                        raise ValueError('Choisissez le JSON avec le bouton Parcourir.')
                    command.extend(['--'+name,options[name]])
            mode = options.get('detection','auto')
            count = options.get('characters',0)
            if mode not in ('auto','community-1','classique') or type(count) is not int or not 0 <= count <= 20:
                raise ValueError('Réglage de détection invalide.')
            command.extend(['--detection',mode,'--personnages',str(count)])
            if not options.get('separation',True):
                command.append('--sans-audio-separe')
            if options.get('cpu'):
                command.append('--cpu')
            def task():
                creation = {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session':True}
                self._process = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,encoding='utf-8',errors='replace',cwd=ROOT,**creation)
                if self._cancel.is_set():
                    stop_process(self._process)
                for line in self._process.stdout:
                    self._state['logs'] = (self._state['logs']+[line.rstrip()])[-120:]
                code = self._process.wait()
                self._process = None
                if self._cancel.is_set():
                    raise Cancelled()
                if code:
                    raise RuntimeError('Préparation interrompue. Consultez le journal ; les résultats intermédiaires sont conservés.')
                project = Projet.create(folder,load_document(output/'OSS-editeur.html'))
                return project.path
            return self._job(task)

    def open_prepared(self):
        with self._lock:
            self._idle()
            if self._state['status'] != 'done' or not str(self._state.get('path','')).endswith('.doubalge'):
                raise ValueError('Aucun nouveau projet préparé.')
            return self._editor(Projet(self._state['path']))

    def home(self, session, edits):
        with self._lock:
            self._idle()
            self.save_project(session,edits)
            self._project.release()
            self._project = None
            self._session = None
            self._page = 'home'
            self._window.load_url(self._home.as_uri())
            return True

    def close_saved(self, session=None, edits=None):
        if session:
            self.save_project(session,edits)
        self.cancel_job()
        self._allow_close = True
        return True

    def _closing(self):
        if self._allow_close:
            return True
        if self._page == 'home':
            self.cancel_job()
            return True
        # Les événements de fermeture bloquent le fil GUI : exécuter le JS ailleurs.
        def save_then_close():
            import time
            self._window.evaluate_js('globalThis.DoubalgeDesktop && DoubalgeDesktop.close()')
            while True:
                state = self._window.evaluate_js('({ready:DoubalgeDesktop.closeReady,failed:DoubalgeDesktop.closeFailed})')
                if state.get('failed'):
                    return
                if state.get('ready'):
                    self._window.destroy()
                    return
                time.sleep(.05)
        threading.Thread(target=save_then_close,daemon=True).start()
        return False

    def cleanup(self):
        self.cancel_job()
        if self._worker:
            self._worker.join()
        if self._project:
            self._project.release()
        self._temp.cleanup()


def main():
    parser = argparse.ArgumentParser(description='Doubalge — application locale')
    parser.add_argument('--projet',type=Path)
    args = parser.parse_args()
    try:
        import webview
    except ImportError as error:
        raise RuntimeError('Installez la fenêtre intégrée : .venv\\Scripts\\python.exe -m pip install -r studio\\requirements-app.txt') from error
    app = Application()
    app._window = webview.create_window('Doubalge — préparation et édition',url=app._home.as_uri(),js_api=app,
                                        width=1400,height=900,min_size=(1100,650))
    app._window.events.closing += app._closing
    def ready():
        if args.projet:
            app._editor(Projet(args.projet))
    try:
        webview.start(ready,gui='edgechromium' if os.name == 'nt' else None,http_server=False,storage_path=str(app._ui/'webview'),
                      localization={'global.quitConfirmation':'Quitter Doubalge ?'})
    finally:
        app.cleanup()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if sys.stderr is not None:
            print('[erreur] '+str(error),file=sys.stderr)
        if os.name == 'nt':
            try:
                import tkinter as tk
                from tkinter import messagebox
                root=tk.Tk();root.withdraw()
                messagebox.showerror('Doubalge — ouverture impossible',str(error)+'\n\nVérifiez les dépendances et le runtime Microsoft Edge WebView2.',parent=root)
                root.destroy()
            except Exception:
                pass
        sys.exit(1)
