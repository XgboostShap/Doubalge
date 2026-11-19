"""Parcours réel de vérification dans Chromium ; génération simulée explicitement."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from playwright.sync_api import sync_playwright
from app import App,Server
from fixtures import FakeClient,make_pdf
from pipeline import Pipeline
from issues import ReviewRequired
from storage import read,write


with tempfile.TemporaryDirectory(prefix='podcast-review-browser-') as temporary:
    root=Path(temporary);app=App(root/'data',FakeClient);server=Server(('127.0.0.1',0),app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        project=app.project(app.create({'name':'Vérification des sources'})['id'])
        make_pdf(project/'sources/a.pdf')
        meta=read(project/'projet.json');meta['pdfs']=[{'file':'a.pdf','name':'Optique.pdf'}]
        meta['audio_settings']={'voices':{'Sophie':'local-a','Emma':'local-b'}};write(project/'projet.json',meta)
        Pipeline(project,FakeClient()).run(1,9)
        ideas=[i for d in read(project/'etapes/02.json')['data']['documents'] for p in d['parts'] for i in p['ideas']]
        app.flag_source(project,{'id':ideas[0]['id']});app.flag_source(project,{'id':ideas[1]['id']})
        with sync_playwright() as browser_tools:
            browser=browser_tools.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
            page=context.new_page();errors=[];external=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:external.append(request.url) if not request.url.startswith(('http://127.0.0.1:','data:','blob:')) else None)
            url=f'http://127.0.0.1:{server.server_port}'
            page.goto(url);page.locator('#projects button').click()
            page.wait_for_function('() => current()?.reviews.length===2')
            assert page.locator('#continue').is_disabled()
            assert not app.summary(project)['exports']
            assert context.request.get(url+f'/files/{project.name}/podcast.txt').status==404
            response=context.request.get(url+f'/sources/{project.name}/PDF1.pdf',headers={'Range':'bytes=0-4'})
            assert response.status==206 and response.body()==b'%PDF-'
            assert response.headers['content-type']=='application/pdf'
            first=page.locator('.review-item').nth(0);second=page.locator('.review-item').nth(1)
            first.locator('summary').click();second.locator('summary').click()
            second.locator('textarea').last.fill('Brouillon conservé pendant la première décision.')
            first.locator('textarea').last.fill('Citation et idée comparées à la page du PDF.')
            first.get_by_role('button',name='Valider cette correction de la source',exact=True).click()
            page.wait_for_function('() => current()?.reviews.length===1')
            assert page.locator('.review-item textarea').last.input_value()=='Brouillon conservé pendant la première décision.'
            assert page.locator('#continue').is_disabled()
            output=Path(os.environ.get('PODCAST_CHECK_OUTPUT',str(root/'screens')));output.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(output/'verifications-source.png'),full_page=True)
            page.get_by_role('button',name='Valider cette correction de la source',exact=True).click()
            page.wait_for_function('() => current()?.reviews.length===0&&current()?.next_step===3')
            assert page.locator('#continue').is_enabled()
            page.locator('#continue').click()
            page.wait_for_function('() => current()?.task.state==="done"&&current()?.completed.length===9',timeout=60000)
            assert read(project/'projet.json')['audio_settings']['voices']==meta['audio_settings']['voices']
            page.locator('#source-reader summary').click()
            page.wait_for_function('() => document.querySelector("#retained-ideas").options.length>0')
            page.locator('#flag-source').click();page.wait_for_function('() => current()?.reviews.length===1')
            assert page.locator('#review-panel').is_visible()
            # Un projet sans idée retenue doit pouvoir reprendre l’étape 2 après le groupe de décisions.
            empty_project=app.project(app.create({'name':'Sources à réexaminer'})['id'])
            make_pdf(empty_project/'sources/a.pdf');empty_meta=read(empty_project/'projet.json')
            empty_meta['pdfs']=[{'file':'a.pdf','name':'Optique.pdf'}];write(empty_project/'projet.json',empty_meta)
            class RejectAll(FakeClient):
                def ask(self,task,payload,*args,**kwargs):
                    if task=='review_facts':return {'decisions':{i['id']:{'status':'uncertain','reason':'Appui incertain à réexaminer.'} for i in payload['candidates']}}
                    return super().ask(task,payload,*args,**kwargs)
            try:Pipeline(empty_project,RejectAll()).run(1,2)
            except ReviewRequired:pass
            else:raise AssertionError('Les sources doivent attendre une vérification.')
            for item in app.summary(empty_project)['reviews']:app.resolve_review(empty_project,{'id':item['id'],'action':'retry'})
            page.evaluate('() => refresh()');page.wait_for_function('() => state.projects.length===2')
            page.locator('#projects button').filter(has_text='Sources à réexaminer').click()
            page.wait_for_function('() => current()?.source_diagnostic.empty&&current()?.next_step===2')
            assert page.locator('#continue').is_enabled()
            page.locator('#continue').click()
            page.wait_for_function('() => current()?.task.state==="done"&&current()?.completed.length===9',timeout=60000)
            assert not external and not errors,(external,errors)
            result={'interface':'Chromium réel','generation':'Fournisseur simulé, aucune validation scientifique implicite',
                    'grouped_reviews':True,'draft_preserved_between_decisions':True,'source_pdf_ranges':True,
                    'blocked_unverified_export':True,'resume_3_to_9':True,'voices_preserved':True,
                    'manual_flag_after_automatic_acceptance':True,'external_page_requests':external,'javascript_errors':errors}
            result['zero_retained_source_retry_from_interface']=True
            (output/'parcours-verifications.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
            print(json.dumps(result,ensure_ascii=False));browser.close()
    finally:
        app.close();server.shutdown();server.server_close();thread.join()
