"""Serveur éphémère limité à l'éditeur choisi et à son export MP4."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import errno
import json
from pathlib import Path
import re
import secrets
import socket
import sys
import tempfile
import threading
import webbrowser
from urllib.parse import urlsplit

from export_html import SCHEMA, TEMPLATES, serialiser_html
from export_mp4 import Cancelled, render


def load_document(path):
    match = re.search(r'<script\b[^>]*\bid=["\']editor-data["\'][^>]*>(.*?)</script\s*>',
                      Path(path).read_text(encoding='utf-8-sig'), re.S | re.I)
    if not match:
        raise ValueError('Choisissez votre fichier OSS-editeur.html.')
    document = json.loads(match[1])
    if document.get('schema') != SCHEMA:
        raise ValueError('Éditeur incompatible.')
    return document


class LocalServer(ThreadingHTTPServer):
    # Sous Windows, SO_REUSEADDR peut laisser deux services partager le même port.
    allow_reuse_address = sys.platform != 'win32'

    def server_bind(self):
        if sys.platform == 'win32':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def create_server(editor, port=8765):
    document = load_document(editor)
    token = secrets.token_urlsafe(32)
    temporary = tempfile.TemporaryDirectory(prefix='doubalge-mp4-')
    state = {'status': 'idle', 'progress': 0}
    cancel = threading.Event()
    lock = threading.Lock()
    worker = None
    document['improTemplate'] = (TEMPLATES/'impro.html').read_text(encoding='utf-8')
    document['showTemplate'] = (TEMPLATES/'spectacle.html').read_text(encoding='utf-8')
    html = (TEMPLATES/'editeur.html').read_text(encoding='utf-8').replace('__EDITOR_DATA__', serialiser_html(document))
    html = html.replace('</body>', '<script>globalThis.DOUBALGE_EXPORT_TOKEN='+json.dumps(token)+';</script></body>')

    def encode(request):
        try:
            with tempfile.TemporaryDirectory(dir=temporary.name) as work:
                result = render(document, request, work, cancel, lambda n: state.update(progress=n))
                if cancel.is_set():
                    raise Cancelled()
                result.replace(Path(temporary.name)/'entrainement.mp4')
            state.update(status='done', progress=1)
        except Cancelled:
            state.update(status='cancelled')
        except Exception as error:
            state.update(status='error', error=str(error))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Aucun jeton dans les journaux.

        def reply(self, code, value, mime='application/json'):
            body = json.dumps(value, ensure_ascii=False).encode() if mime == 'application/json' else value
            self.send_response(code)
            self.send_header('Content-Type', mime+'; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def local_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',
                                                f'localhost:{self.server.server_port}')

        def authorised(self):
            return self.local_host() and self.headers.get('X-Doubalge-Token') == token

        def do_GET(self):
            path = urlsplit(self.path).path
            if not self.local_host():
                self.reply(403, {'error': 'Accès refusé.'})
            elif path in ('/', '/editeur', '/'+token):
                if self.headers.get('Sec-Fetch-Site') not in (None, 'none', 'same-origin'):
                    self.reply(403, {'error': 'Ouvrez l’adresse affichée par Lancer-studio.'})
                    return
                # Le jeton protège les commandes d'export, sans rendre l'URL de la page fragile.
                self.reply(200, html.encode(), 'text/html')
            elif re.fullmatch(r'/[A-Za-z0-9_-]{43}', path):
                self.reply(410, ('<!doctype html><meta charset="utf-8"><title>Doubalge</title>'
                    '<h1>Ancienne adresse de l’éditeur</h1><p>Cette adresse appartient à une autre session.</p>'
                    '<p><a href="/">Ouvrir la scène de cette fenêtre Lancer-studio</a>.</p>'
                    '<p>Pour une autre scène, choisissez son OSS-editeur.html dans Lancer-studio, sans refaire l’analyse.</p>').encode(), 'text/html')
            elif not self.authorised():
                self.reply(403, {'error': 'Accès refusé. Rouvrez la scène avec Lancer-studio.'})
            elif self.path == '/status':
                self.reply(200, state.copy())
            elif self.path == '/video' and state['status'] == 'done':
                path = Path(temporary.name)/'entrainement.mp4'
                self.send_response(200)
                self.send_header('Content-Type', 'video/mp4')
                self.send_header('Content-Length', str(path.stat().st_size))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                with path.open('rb') as source:
                    while chunk := source.read(1024*1024):
                        self.wfile.write(chunk)
            else:
                self.reply(404, {'error': 'Introuvable.'})

        def do_POST(self):
            nonlocal worker
            if not self.authorised():
                self.reply(403, {'error': 'Accès refusé.'})
                return
            if self.path == '/cancel':
                cancel.set()
                self.reply(200, {'ok': True})
                return
            if self.path != '/export':
                self.reply(404, {'error': 'Introuvable.'})
                return
            with lock:
                if worker and worker.is_alive():
                    self.reply(409, {'error': 'Un export est déjà en cours.'})
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 8*1024*1024:
                        raise ValueError('Demande trop volumineuse.')
                    request = json.loads(self.rfile.read(length))
                    if not isinstance(request, dict) or request.get('profile') not in ('mail', 'standard'):
                        raise ValueError('Profil invalide.')
                except (ValueError, TypeError) as error:
                    self.reply(400, {'error': str(error)})
                    return
                cancel.clear()
                state.clear()
                state.update(status='running', progress=0)
                worker = threading.Thread(target=encode, args=(request,), daemon=True)
                worker.start()
                self.reply(202, state.copy())

    try:
        server = LocalServer(('127.0.0.1', port), Handler)
    except OSError as error:
        if error.errno != errno.EADDRINUSE and getattr(error, 'winerror', None) not in (10048, 10013):
            temporary.cleanup()
            raise
        if port != 8765:
            temporary.cleanup()
            raise
        # Une autre scène ou application utilise le port : ouvrir une session isolée.
        server = LocalServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True

    def cleanup():
        cancel.set()
        if worker:
            worker.join()
        server.server_close()
        temporary.cleanup()
    server.cleanup = cleanup
    server.editor_url = f'http://127.0.0.1:{server.server_port}/'
    return server


def ouvrir(editor):
    server = create_server(editor)
    print('Éditeur prêt : '+server.editor_url, flush=True)
    print('Scène : '+str(Path(editor).resolve()), flush=True)
    print('Gardez cette fenêtre pour exporter les MP4. Ctrl+C pour fermer.', flush=True)
    print('Si le navigateur affiche une ancienne page, ouvrez l’adresse ci-dessus.', flush=True)
    if server.server_port != 8765:
        print('Le port habituel est occupé : cette scène utilise un autre port local.', flush=True)
    webbrowser.open(server.editor_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.cleanup()
