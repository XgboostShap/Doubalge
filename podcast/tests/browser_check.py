"""Test de l'interface réelle, avec un serveur Ollama simulé explicitement."""
import json
import os
from pathlib import Path
import sys
import shutil
import tempfile
import threading

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from playwright.sync_api import sync_playwright
from app import APP_VERSION,App,Server
from fixtures import StubServer,make_pdf
from storage import invalidate,read,write

with tempfile.TemporaryDirectory(prefix='podcast-browser-') as temp:
    temp=Path(temp);stub=StubServer();app=App(temp/'data');server=Server(('127.0.0.1',0),app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        pdf1=make_pdf(temp/'optique.pdf');pdf2=make_pdf(temp/'laser.pdf','Laser')
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),headless=True,args=['--no-sandbox'])
            context=browser.new_context(accept_downloads=True,viewport={'width':1500,'height':1050})
            page=context.new_page();errors=[];external=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:external.append(r.url) if not r.url.startswith(f'http://127.0.0.1:{server.server_port}') and r.url.startswith(('http:','https:')) else None)
            page.goto(f'http://127.0.0.1:{server.server_port}/');page.wait_for_function('() => state!==null')
            assert APP_VERSION in page.locator('.badge').inner_text()
            page.locator('#name').fill('Test d’intégration — fournisseur simulé')
            page.locator('#pdfs').set_input_files([str(pdf1),str(pdf2)])
            page.locator('#model-settings summary').click();page.locator('#endpoint').fill(stub.endpoint);page.locator('#model').fill('mistral:test')
            page.locator('#check-model').click();page.wait_for_function('() => document.querySelector("#model-status").textContent.includes("mistral:test")')
            page.locator('#create').click();page.wait_for_function('() => current()?.pdfs.length===2')
            identifier=page.evaluate('selected');folder=app.project(identifier)
            page.evaluate('() => {state.runtime=null;render()}')
            assert page.locator('#continue').is_disabled()
            assert 'ancienne instance' in page.locator('#notice').inner_text().lower()
            page.evaluate('() => refresh()')
            page.wait_for_function('() => Boolean(state.runtime?.version)')
            page.locator('#run-step').click();page.wait_for_function('() => current()?.completed.includes(1)&&current()?.task.state==="done"')
            page.wait_for_function('() => document.querySelector("#preview").textContent.includes("pages 1")')
            assert 'pages 1' in page.locator('#preview').inner_text()
            stub.fail_on=('dialogue','C2')
            page.locator('#continue').click();page.wait_for_function('() => current()?.task.state==="error"&&current()?.completed.length===7',timeout=60000)
            page.locator('#steps button').nth(7).click()
            page.wait_for_function('() => document.querySelectorAll("#part-links a").length===1')
            assert page.locator('#download-md').is_hidden()
            page.locator('#saved-parts summary').click()
            with page.expect_download() as download:page.locator('#part-links a').click()
            partial=temp/'chapitre-1.md';download.value.save_as(partial)
            assert 'Sophie' in partial.read_text()
            before=len([p for task,p in stub.calls if task=='dialogue' and p['chapter']['id']=='C1'])
            page.locator('#continue').click();page.wait_for_function('() => current()?.task.state==="done"&&current()?.completed.length===9',timeout=60000)
            after=len([p for task,p in stub.calls if task=='dialogue' and p['chapter']['id']=='C1'])
            assert before==after==1
            assert page.locator('#steps button').count()==9
            with page.expect_download() as download:page.locator('#export-links a').filter(has_text='Texte du dialogue').click()
            output=temp/'podcast.txt';download.value.save_as(output)
            script=output.read_text();assert 'Sophie :' in script and 'Emma :' in script
            with page.expect_download() as download:page.locator('#export-links a').filter(has_text='Données et rapport JSON').click()
            output_json=temp/'podcast.json';download.value.save_as(output_json)
            assert json.loads(output_json.read_text())['all_planned_ids_present']
            assert len(read(folder/'etapes/01.json')['data']['documents'])==2
            calls=[payload for task,payload in stub.calls if task=='dialogue'];assert calls[1]['memory']['last_turns']
            # Rechargement d'un projet dont l'étape 2 date d'avant ce correctif.
            legacy=read(folder/'etapes/02.json');legacy['data'].pop('quality_version',None)
            for doc in legacy['data']['documents']:
                for part in doc['parts']:part.pop('quality_version',None)
            invalidate(folder,2)
            write(folder/'etapes/02.json',legacy);(folder/'etapes/02.md').write_text('Ancien résumé par pages')
            meta=read(folder/'projet.json');meta.pop('summary_quality',None);write(folder/'projet.json',meta)
            page.evaluate('() => refresh()');page.wait_for_function('() => current()?.completed.length===2')
            assert page.locator('#quality-upgrade').is_visible()
            before_extract=len([p for task,p in stub.calls if task=='part_summary'])
            page.locator('#refine').click();page.wait_for_function('() => current()?.task.state==="done"&&current()?.summary_quality==="source-review-v2"',timeout=60000)
            assert len([p for task,p in stub.calls if task=='part_summary'])==before_extract
            assert page.locator('#quality-upgrade').is_hidden()
            page.wait_for_function('() => document.querySelector("#preview").textContent.includes("Problème posé")')
            assert (folder/'reprises/02.json').exists()
            page.locator('#continue').click();page.wait_for_function('() => current()?.task.state==="done"&&current()?.completed.length===9',timeout=60000)
            page.locator('#steps button').nth(3).click();page.wait_for_function('() => document.querySelector("#preview").textContent.includes("PDF2")')
            page.locator('#steps button').nth(5).click();page.locator('#run-step').click()
            page.wait_for_function('() => current()?.task.state==="done"&&current()?.completed.length===6',timeout=60000)
            assert page.locator('#final-exports').is_hidden()
            assert list((folder/'versions').rglob('export-podcast.txt'))
            page.locator('#continue').click();page.wait_for_function('() => current()?.task.state==="done"&&current()?.completed.length===9',timeout=60000)
            page.locator('#steps button').nth(8).click()
            page.wait_for_function('() => document.querySelector("#preview").textContent.includes("Rapport de révision")')
            (ROOT/'dist').mkdir(exist_ok=True);page.screenshot(path=str(ROOT/'dist/interface-verifiee.png'),full_page=True)
            # Annulation d'une vraie lecture HTTP en cours : pas seulement du bouton.
            stub.stall=True;stub.started.clear()
            page.locator('#steps button').nth(1).click();page.locator('#run-step').click()
            assert stub.started.wait(10)
            page.wait_for_function('() => current()?.task.state==="running"')
            page.locator('#cancel').click();page.wait_for_function('() => current()?.task.state==="cancelled"',timeout=10000)
            assert read(folder/'etapes/01.json')
            assert not errors,errors
            assert not external,external
            browser.close()
            print('Navigateur OK : neuf étapes, ancien projet amélioré sans refaire les extractions, synthèses structurées, Markdown partiel, reprise, exports, archives et annulation ; aucune erreur JS ou requête externe.')
    finally:
        stub.close();server.shutdown();server.server_close();app.close();thread.join()
