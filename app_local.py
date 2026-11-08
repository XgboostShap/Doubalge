"""Interface locale DoublageBasic. Écoute exclusive sur la boucle locale."""
from __future__ import annotations
import argparse
import copy
import json
import mimetypes
import os
from pathlib import Path
import queue
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from edition import atomic_json, read_json, validate

ROOT = Path(__file__).resolve().parent
ID = re.compile(r'[a-f0-9]{32}')
SECRET = re.compile(r'hf_[A-Za-z0-9_-]+')

def scrub(text, token=''):
    if token:
        text = text.replace(token, '[JETON MASQUÉ]')
    return SECRET.sub('[JETON MASQUÉ]', text)


def stop_tree(process):
    if process is None or process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=15)


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, data):
        self.data = Path(data).resolve()
        self.projects = self.data / 'projets'
        self.projects.mkdir(parents=True, exist_ok=True)
        self.instance_lock = (self.data / '.server.lock').open('a+b')
        self.instance_lock.seek(0)
        if not self.instance_lock.read(1):
            self.instance_lock.write(b'0')
            self.instance_lock.flush()
        self.instance_lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.instance_lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.instance_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.instance_lock.close()
            raise RuntimeError('DoublageBasic utilise déjà ce dossier. Revenez à la fenêtre ouverte ou fermez son ancienne console.') from None
        self.lock = threading.RLock()
        self.pending = queue.Queue()
        self.token = ''
        self.csrf = secrets.token_urlsafe(32)
        self.process = None
        self.active = None
        self.stopping = False
        for folder in self.projects.iterdir():
            task = folder / 'tache.json'
            if task.exists():
                try:
                    status = read_json(task)
                    if status.get('status') in ('queued', 'running'):
                        status.update(status='interrupted', message='Traitement interrompu. Vous pouvez le reprendre.')
                        atomic_json(task, status)
                except (ValueError, OSError):
                    pass
        self.worker = threading.Thread(target=self.work, daemon=True)
        self.worker.start()

    def folder(self, ident):
        if not ID.fullmatch(ident):
            raise ValueError('Identifiant de projet invalide')
        folder = self.projects / ident
        if folder.is_symlink() or not (folder / 'projet.json').is_file():
            raise FileNotFoundError('Projet introuvable')
        return folder

    def task(self, folder):
        path = folder / 'tache.json'
        return read_json(path) if path.exists() else dict(status='idle')

    def idle(self, folder):
        if self.task(folder)['status'] in ('queued', 'running'):
            raise Conflict('Un traitement est en cours pour ce projet')

    def state(self):
        projects = []
        with self.lock:
            for folder in self.projects.iterdir():
                if not ID.fullmatch(folder.name) or folder.is_symlink():
                    continue
                try:
                    p = read_json(folder / 'projet.json')
                    p['task'] = self.task(folder)
                    p['exports'] = [f.name for f in sorted((folder / 'exports').glob('impro-*'))
                                    if f.is_file() and f.suffix in ('.mp4', '.html')]
                    p['has_source'] = (folder / 'original.mp4').exists()
                    projects.append(p)
                except (ValueError, OSError):
                    continue
        return dict(projects=projects, token_set=bool(self.token), csrf=self.csrf)

    def save(self, folder, body):
        self.idle(folder)
        p = read_json(folder / 'projet.json')
        if type(body.get('revision')) is not int or body['revision'] != p['revision']:
            raise Conflict('Une autre fenêtre a enregistré ce projet. Rechargez avant de continuer ; votre JSON peut être téléchargé dans l’éditeur.')
        previous = read_json(folder / 'corrections.json')
        edit = validate(body.get('corrections'), p, previous)
        # Garder une sauvegarde avant chaque modification humaine.
        stamp = f"{p['revision']:08d}"
        atomic_json(folder / 'sauvegardes' / (stamp + '.json'), previous)
        atomic_json(folder / 'corrections.json', edit)
        p['revision'] += 1
        atomic_json(folder / 'projet.json', p)
        return dict(revision=p['revision'])

    def enqueue(self, folder, action, options):
        self.idle(folder)
        if action not in ('analyze', 'resume', 'separate', 'export', 'refresh'):
            raise ValueError('Action inconnue')
        p = read_json(folder / 'projet.json')
        if action in ('analyze', 'resume') and p.get('ready'):
            raise Conflict('Ce projet est déjà analysé. Créez un autre projet pour refaire l’analyse et préserver vos corrections.')
        if action in ('separate', 'export') and not p.get('ready'):
            raise ValueError('Analyser ou importer les corrections avant cet export')
        if action in ('analyze', 'resume'):
            speakers = options.get('speakers')
            if speakers is not None and (type(speakers) is not int or not 1 <= speakers <= 100):
                raise ValueError('Nombre de voix : 1 à 100')
            if 'corrections' in options and not isinstance(options['corrections'], dict):
                raise ValueError('JSON de corrections invalide')
        # Une reprise réutilise la demande précédente, pas un fichier déjà découpé.
        if action == 'resume' and (folder / 'reprise.json').exists():
            options = read_json(folder / 'reprise.json')
        if action in ('analyze', 'resume'):
            atomic_json(folder / 'reprise.json', options)
        task = dict(id=uuid.uuid4().hex, status='queued', action=action, message='En attente', progress=0)
        atomic_json(folder / 'tache.json', task)
        atomic_json(folder / 'taches' / (task['id'] + '.json'), dict(action=action, options=options))
        self.pending.put((folder, task, options))
        return task

    def cancel(self, folder):
        task = self.task(folder)
        if task['status'] in ('queued', 'running'):
            task.update(status='cancelled', message='Annulé')
            atomic_json(folder / 'tache.json', task)
            if self.active == folder:
                stop_tree(self.process)
        return task

    def work(self):
        while True:
            item = self.pending.get()
            if item is None:
                return
            folder, task, options = item
            with self.lock:
                if self.stopping or self.task(folder)['status'] == 'cancelled':
                    continue
                task.update(status='running', message='Traitement en cours')
                atomic_json(folder / 'tache.json', task)
                token = self.token
                env = os.environ.copy()
                # Les secrets du cloud ne doivent pas devenir une configuration de l’application.
                for key in ('HF_TOKEN', 'PYANNOTE_TOKEN', 'TOkTok', 'HUGGING_FACE_HUB_TOKEN'):
                    env.pop(key, None)
                env.update(PYTHONUTF8='1', PYTHONUNBUFFERED='1', HF_HUB_DISABLE_TELEMETRY='1', PYANNOTE_METRICS_ENABLED='0')
                kwargs = dict(start_new_session=True) if os.name != 'nt' else dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                try:
                    process = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'local_pipeline.py'), str(folder)],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding='utf-8', errors='replace', env=env, **kwargs)
                    self.process, self.active = process, folder
                    json.dump(dict(action=task['action'], options=options, token=token), process.stdin)
                    process.stdin.close()
                except Exception as error:
                    task.update(status='error', message=scrub(str(error), token))
                    atomic_json(folder / 'tache.json', task)
                    continue
            try:
                with (folder / 'journal.txt').open('a', encoding='utf-8') as log:
                    log.write('\n--- ' + task['action'] + ' ---\n')
                    for line in process.stdout:
                        line = scrub(line, token)
                        log.write(line)
                        log.flush()
                code = process.wait()
                with self.lock:
                    if self.task(folder)['status'] != 'cancelled':
                        task.update(status='done' if code == 0 else 'error', progress=1 if code == 0 else 0,
                                    message='Terminé' if code == 0 else 'Échec : consulter le journal')
                        atomic_json(folder / 'tache.json', task)
            finally:
                process.stdout.close()
                with self.lock:
                    self.process, self.active = None, None

    def close(self):
        with self.lock:
            self.stopping = True
            if self.active:
                self.cancel(self.active)
        self.pending.put(None)
        self.worker.join(timeout=20)
        self.instance_lock.close()


def editor_html(folder, csrf):
    p = read_json(folder / 'projet.json')
    edit = read_json(folder / 'corrections.json')
    baseline = read_json(folder / 'analyse.json')
    sys.path.insert(0, str(ROOT / 'studio'))
    from export_html import TEMPLATES, COLORS, serialiser_html
    data = dict(schema=edit['schema'], analysis_id=p['analysis_id'], source_sha256=p['source_sha256'],
                duration=p['duration'], fps=25, title=p['name'],
                characters=[dict(id=key, label=name, color=COLORS[n % len(COLORS)], photo=None)
                            for n, (key, name) in enumerate(p['voices'].items())],
                initial=edit['intervals'], initialCuts=edit['cuts'], automatic=baseline['intervals'],
                automaticCuts=baseline['cuts'], peaks=read_json(folder / 'onde.json'),
                media='lecture.mp4', improMedia='lecture.mp4',
                improTemplate=(TEMPLATES/'impro.html').read_text(encoding='utf-8'),
                showTemplate=(TEMPLATES/'spectacle.html').read_text(encoding='utf-8'))
    template = (TEMPLATES / 'editeur.html').read_text(encoding='utf-8')
    config = serialiser_html(dict(project=p['id'], revision=p['revision'], csrf=csrf))
    # Le drapeau évite de restaurer un ancien brouillon de navigateur.
    template = template.replace('<head>', '<head><script>globalThis.DOUBALGE_DESKTOP=true;globalThis.LOCAL_CONFIG='+config+';globalThis.DoubalgeDesktop={changed(){}};</script>', 1)
    template = template.replace('__EDITOR_DATA__', serialiser_html(data))
    adapter = (ROOT / 'local_web/editor-adapter.js').read_text(encoding='utf-8')
    return template.replace('</body>', '<script>'+adapter+'</script></body>').encode('utf-8')


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != 'nt'
    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def create_server(data=None, port=8765):
    store = Store(data or ROOT / 'donnees')
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def setup(self):
            super().setup()
            self.connection.settimeout(60)
        def log_message(self, *args):
            pass
        def headers_common(self):
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "frame-ancestors 'self'")
            self.send_header('X-Frame-Options', 'SAMEORIGIN')
        def reply(self, code, value, mime='application/json'):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if mime == 'application/json' else value
            self.send_response(code)
            self.headers_common()
            self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') or mime == 'application/json' else ''))
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def local(self):
            port = self.server.server_port
            hosts = (f'127.0.0.1:{port}', f'localhost:{port}')
            if self.headers.get('Host') not in hosts:
                raise PermissionError('Host refusé')
            origin = self.headers.get('Origin')
            if origin and origin not in tuple('http://' + host for host in hosts):
                raise PermissionError('Origine refusée')
            if self.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
                raise PermissionError('Accès externe refusé')
        def file(self, path, download=False):
            if path.is_symlink() or not path.is_file():
                raise FileNotFoundError()
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            range_header = self.headers.get('Range')
            if range_header:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header)
                if not match or not any(match.groups()):
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                a, b = match.groups()
                if not a:
                    start = max(0, size - int(b))
                else:
                    start = int(a)
                    end = min(size - 1, int(b)) if b else size - 1
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.headers_common()
            self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(max(0, end - start + 1)))
            if status == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            if download:
                self.send_header('Content-Disposition', 'attachment; filename="' + path.name + '"')
            self.end_headers()
            with path.open('rb') as stream:
                stream.seek(start)
                left = end - start + 1
                while left > 0:
                    block = stream.read(min(left, 1024 * 1024))
                    if not block:
                        break
                    self.wfile.write(block)
                    left -= len(block)
        def dispatch_get(self):
            self.local()
            path = unquote(urlsplit(self.path).path)
            if path == '/api/state':
                return self.reply(200, store.state())
            if path in ('/', '/index.html', '/app.js', '/style.css'):
                return self.file(ROOT / 'local_web' / ('index.html' if path == '/' else path[1:]))
            match = re.fullmatch(r'/api/projects/([a-f0-9]{32})', path)
            if match:
                with store.lock:
                    folder = store.folder(match[1])
                    p = read_json(folder / 'projet.json')
                    edit_path = folder / 'corrections.json'
                    return self.reply(200, dict(project=p, corrections=read_json(edit_path) if edit_path.exists() else None))
            match = re.fullmatch(r'/files/([a-f0-9]{32})/([^/]+)', path)
            if match:
                with store.lock:
                    folder, name = store.folder(match[1]), match[2]
                    if name == 'editeur.html':
                        return self.reply(200, editor_html(folder, store.csrf), 'text/html')
                    if name in ('lecture.mp4', 'journal.txt', 'corrections.json'):
                        target, download = folder / name, name == 'corrections.json'
                    elif re.fullmatch(r'impro-[a-f0-9]{12}\.(mp4|html)', name):
                        target, download = folder / 'exports' / name, True
                    else:
                        raise FileNotFoundError()
                return self.file(target, download)
            raise FileNotFoundError()
        def do_GET(self):
            self.handle_error(self.dispatch_get)
        def json_body(self):
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8 * 1024 * 1024:
                raise ValueError('Requête JSON trop volumineuse ou vide')
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Envoi incomplet')
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError('Objet JSON attendu')
            return body
        def dispatch_post(self):
            self.local()
            if not secrets.compare_digest(self.headers.get('X-Doublage-Token', ''), store.csrf):
                raise PermissionError('Protection de session invalide. Rechargez la page.')
            path = urlsplit(self.path).path
            if path == '/api/token':
                token = self.json_body().get('token', '')
                if not isinstance(token, str) or len(token) > 512 or token and not re.fullmatch(r'hf_[A-Za-z0-9]+', token):
                    raise ValueError('Jeton Hugging Face invalide')
                with store.lock:
                    store.token = token
                return self.reply(200, dict(ok=True))
            if path == '/api/projects':
                body = self.json_body()
                url = body.get('url', '').strip()
                if url:
                    parsed = urlsplit(url)
                    if parsed.scheme != 'https' or parsed.hostname not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be') or parsed.username or parsed.password:
                        raise ValueError('Utiliser une URL HTTPS YouTube')
                name = body.get('name', 'Nouveau projet')
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
                    raise ValueError('Nom de projet invalide')
                with store.lock:
                    ident = uuid.uuid4().hex
                    folder = store.projects / ident
                    folder.mkdir()
                    p = dict(id=ident, name=scrub(name.strip()), url=url, revision=0, ready=False, voices={})
                    atomic_json(folder / 'projet.json', p)
                return self.reply(201, p)
            match = re.fullmatch(r'/api/projects/([a-f0-9]{32})/(source|analyze|resume|separate|corrections|voices|export|cancel)', path)
            if not match:
                raise FileNotFoundError()
            ident, action = match.groups()
            folder = store.folder(ident)
            if action == 'source':
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8 * 1024**3:
                    raise ValueError('Vidéo attendue, maximum 8 Go')
                with store.lock:
                    store.idle(folder)
                    p = read_json(folder / 'projet.json')
                    if p['ready'] or (folder / 'original.mp4').exists():
                        raise Conflict('La source de ce projet est déjà définie')
                    tmp = folder / 'upload.tmp'
                    try:
                        with tmp.open('wb') as stream:
                            remaining = length
                            while remaining:
                                chunk = self.rfile.read(min(1024 * 1024, remaining))
                                if not chunk:
                                    raise ValueError('Envoi vidéo interrompu')
                                stream.write(chunk)
                                remaining -= len(chunk)
                        os.replace(tmp, folder / 'original.mp4')
                    finally:
                        tmp.unlink(missing_ok=True)
                return self.reply(200, dict(ok=True))
            body = self.json_body()
            with store.lock:
                if action == 'corrections':
                    result = store.save(folder, body)
                elif action == 'voices':
                    store.idle(folder)
                    p = read_json(folder / 'projet.json')
                    if body.get('revision') != p['revision']:
                        raise Conflict('Projet modifié dans une autre fenêtre')
                    label = body.get('label')
                    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80:
                        raise ValueError('Nom de voix invalide')
                    key = body.get('voice')
                    if key is None:
                        indices = [int(v.split(':')[1]) for v in p['voices']]
                        key = f'voice:{max(indices, default=-1) + 1}'
                        if int(key.split(':')[1]) > 9999:
                            raise ValueError('Limite de voix atteinte')
                    elif key not in p['voices']:
                        raise ValueError('Voix inconnue')
                    p['voices'][key] = scrub(label.strip())
                    p['revision'] += 1
                    atomic_json(folder / 'projet.json', p)
                    result = dict(revision=p['revision'], voice=key)
                elif action == 'cancel':
                    result = store.cancel(folder)
                else:
                    result = store.enqueue(folder, 'analyze' if action == 'analyze' else action, body)
            return self.reply(200, result)
        def do_POST(self):
            self.handle_error(self.dispatch_post)
        def handle_error(self, action):
            try:
                action()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True
            except Exception as error:
                code = 409 if isinstance(error, Conflict) else 403 if isinstance(error, PermissionError) else 404 if isinstance(error, FileNotFoundError) else 400 if isinstance(error, (ValueError, TypeError, KeyError)) else 500
                self.close_connection = True
                self.reply(code, dict(error=scrub(str(error), store.token) if code != 500 else 'Erreur interne ; vérifier le dossier de données'))
    try:
        server = Server(('127.0.0.1', port), Handler)
    except OSError:
        if port != 8765:
            store.close()
            raise
        server = Server(('127.0.0.1', 0), Handler)
    server.store = store
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data', type=Path)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    server = create_server(args.data, args.port)
    address = f'http://127.0.0.1:{server.server_port}/'
    print('DoublageBasic : ' + address, flush=True)
    print('Fermez cette console pour arrêter le serveur. Les projets restent enregistrés.', flush=True)
    if not args.no_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.store.close()
        server.server_close()

if __name__ == '__main__':
    main()
