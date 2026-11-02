// Le formulaire URL doit lancer la préparation sans demander un fichier local.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM||'/usr/bin/chromium',args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1372,height:887}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<html></html>');
  await page.evaluate(()=>{
   window.calls=[];
   window.pywebview={api:{
    release_info:async()=>({version:'2026.11.02.2',folder:'D:\\Doubalge'}),
    preparation_settings:async()=>({destination:'D:\\Doubalge\\projets'}),
    choose_destination:async()=>{calls.push('destination');return {destination:'D:\\Mes scènes'};},
    choose_source:async field=>{calls.push(field);return 'D:\\Videos\\scene.mp4';},
    prepare:async options=>{calls.push({prepare:options});return {status:'running'};},
    job_status:async()=>({status:'done',progress:1,logs:['[source] Téléchargement terminé']}),
   }};
  });
  await page.setContent(fs.readFileSync(path.resolve(__dirname,'../app-layout.html'),'utf8'));
  await page.waitForFunction(()=>document.getElementById('destination').value.includes('projets'));
  assert.match(await page.locator('#release-info').innerText(),/2026\.11\.02\.2/);
  await page.click('#new');
  const url='https://www.youtube.com/watch?v=C4MqQfiJR7c';
  await page.fill('#source',url);
  assert.equal(await page.locator('#local-video').isDisabled(),true);
  assert.match(await page.locator('#source-help').innerText(),/téléchargée directement/);
  await page.click('#start');
  await page.waitForSelector('#edit:visible');
  let calls=await page.evaluate(()=>window.calls);
  assert.deepEqual(calls.map(c=>typeof c==='string'?c:'prepare'),['prepare']);
  assert.equal(calls[0].prepare.source,url);
  assert.match(await page.locator('#logs').innerText(),/Téléchargement terminé/);
  await page.click('#destination-choose');
  await page.waitForFunction(()=>document.getElementById('destination').value==='D:\\Mes scènes');
  await page.fill('#source','');
  assert.equal(await page.locator('#local-video').isEnabled(),true);
  await page.click('#local-video');
  await page.waitForFunction(()=>document.getElementById('source').value.endsWith('scene.mp4'));
  calls=await page.evaluate(()=>window.calls);
  assert.deepEqual(calls.slice(1),['destination','video']);
  assert.deepEqual(errors,[]);
  console.log('URL → préparation directe : aucun dialogue de fichier/dossier. Choix de vidéo locale et destination uniquement par leurs boutons explicites.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
