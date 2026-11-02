"""Essai réel de la fenêtre. Lancer explicitement avec pywebview installé.
Linux CI : QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS='--no-sandbox --disable-gpu'.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    import webview
    from application import Application
    from projet_local import Projet
    from serveur_editeur import load_document
    from export_html import donnees_media
    from make_fixture import create
    results = []
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        document = load_document(create(directory/'fixture')[0])
        if sys.platform != 'win32':
            # Qt Linux n'inclut pas les codecs propriétaires. Tester sa lecture avec VP8/Opus,
            # tout en conservant les entrées MP4 et les sorties H.264/AAC du rendu réel.
            from commun import FFMPEG
            webm=directory/'lecture-test.webm'
            subprocess.run([FFMPEG,'-v','error','-y','-i',str(directory/'fixture'/'source.mp4'),
                            '-c:v','libvpx','-c:a','libopus',str(webm)],check=True)
            document['media']=donnees_media(webm,'video/webm')
        project = Projet.create(directory/'projet',document)
        app = Application()
        app._window = webview.create_window('Doubalge test',url=app._home.as_uri(),js_api=app,width=1400,height=900)
        app._window.events.closing += app._closing
        def choose(kind,title,types=(),filename=''):
            return str(directory/('export.mp4' if filename.endswith('.mp4') else 'spectacle.html' if 'spectacle' in title else 'copie.json'))
        app._choose = choose
        def until(predicate,timeout=30):
            end = time.monotonic()+timeout
            while time.monotonic()<end:
                if predicate():
                    return
                time.sleep(.05)
            raise AssertionError('Attente expirée')
        def run():
            try:
                app._window.events._pywebviewready.wait(20)
                assert app._window.evaluate_js('document.title') == 'Doubalge'
                app._editor(project)
                app._window.events._pywebviewready.wait(20)
                until(lambda: app._window.evaluate_js("Boolean(document.getElementById('desktop-home'))"))
                assert app._window.evaluate_js("$('export').textContent") == 'Enregistrer le projet'
                app._window.resize(1100,650)
                time.sleep(.1)
                geometry=app._window.evaluate_js("({height:innerHeight,scroll:document.documentElement.scrollHeight,bottom:Math.max(...['video','timeline','cut-delete','delete','status'].map(id=>$(id).getBoundingClientRect().bottom))})")
                assert geometry['scroll']<=geometry['height'] and geometry['bottom']<=geometry['height'],geometry
                until(lambda:app._window.evaluate_js('video.readyState>=1'))
                app._window.evaluate_js('video.muted=true;video.play().catch(e=>message(e.message,true));')
                until(lambda:app._window.evaluate_js('video.currentTime>.05'))
                app._window.evaluate_js('video.pause();')
                app._window.evaluate_js("change(()=>{intervals[0].start=.15;intervals[0].reviewed=true;audioMix.removedCharacters=['voice:0'];});")
                until(lambda:Projet(project.path).edits['intervals'][0]['start']==.15)
                # Export MP4 via le bouton, le pont natif et le véritable moteur d'encodage.
                app._window.evaluate_js("$('mp4-open').click();$('mp4-start').click();")
                until(lambda:app._state['status'] in ('done','error'))
                assert app._state['status']=='done',app._state
                metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(directory/'export.mp4')]))
                assert [s['codec_name'] for s in metadata['streams']]==['h264','aac']
                app._window.evaluate_js("$('mp4-dialog').close();$('spectacle').click();")
                until(lambda:(directory/'spectacle.html').exists())
                assert '0.15' in (directory/'spectacle.html').read_text(encoding='utf-8')
                assert webview.http.global_server is None, 'Un serveur HTTP a été démarré'
                # Fermer immédiatement après une correction doit conserver le dernier état.
                app._window.evaluate_js("change(()=>{intervals[0].start=.2;});")
                results.append('Fenêtre native, pont Python, sauvegarde disque, MP4 et export spectacle vérifiés sans serveur HTTP.')
                app._window.destroy()
            except Exception:
                results.append(traceback.format_exc())
                print(results[-1],flush=True)
                app._allow_close=True
                app._window.destroy()
        try:
            webview.start(run,gui='edgechromium' if sys.platform=='win32' else 'qt',http_server=False,storage_path=str(directory/'webview'))
            assert app._allow_close,'La fermeture sauvegardée n’a pas abouti'
            assert len(results)==1 and results[0].startswith('Fenêtre native'),results
            assert Projet(project.path).edits['intervals'][0]['start']==.2
            print(results[0],flush=True)
            print('Dernière correction conservée après fermeture et réouverture du projet.',flush=True)
        finally:
            app.cleanup()


if __name__=='__main__':
    main()
