const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
async function text(download) {
  const stream = await download.createReadStream(), parts = [];
  for await (const part of stream) parts.push(part);
  return Buffer.concat(parts).toString('utf8');
}
(async () => {
  const root = path.resolve(__dirname, '../..'), fixture = path.resolve(process.argv[2]);
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/usr/bin/chromium',
    headless: true, args: ['--no-sandbox'] });
  const errors = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
    const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
    await page.setContent(fs.readFileSync(path.join(root, 'Spectacle.html'), 'utf8'));
    await page.locator('#scene-files').setInputFiles([path.join(fixture, 'OSS.html'), path.join(fixture, 'OSS-editeur.html')]);
    await page.waitForFunction(() => queue.length === 2 && !loading);
    for (const [width, height] of [[1280, 600], [1280, 720], [1366, 768], [1920, 1080]]) {
      await page.setViewportSize({ width, height });
      const layout = await page.evaluate(() => ({
        bottom: Math.max($('roles').getBoundingClientRect().bottom, $('status').getBoundingClientRect().bottom),
        stage: $('stage').getBoundingClientRect().height,
        width: document.documentElement.scrollWidth,
      }));
      assert.ok(layout.bottom <= height && layout.width <= width && layout.stage >= 140,
        `Commandes hors écran en ${width}×${height} : ${JSON.stringify(layout)}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    const [first, second] = await page.evaluate(() => queue.map(e => e.id));
    assert.notEqual(first, second);
    await page.locator('#roles input[data-character="voice:0"]').check();
    await page.locator('#roles input[data-performer="voice:0"]').fill('Alice');
    await page.locator('#ambience').uncheck();
    await page.locator(`.scene[data-id="${second}"] [data-action="prepare"]`).click();
    await page.waitForFunction(() => !loading);
    assert.deepEqual(await page.evaluate(() => current().data.audioMix.removedCharacters), []);
    assert.equal(await page.locator('#ambience').isChecked(), true);
    await page.locator(`.scene[data-id="${second}"] [data-action="up"]`).click();
    assert.deepEqual(await page.evaluate(() => queue.map(e => e.id)), [second, first]);
    await page.evaluate(() => { $('volume').value = 40; $('volume').dispatchEvent(new Event('input')); });
    console.log('Programme : import de lecteurs et éditeurs, ordre et réglages propres à chaque scène vérifiés.');

    const download = page.waitForEvent('download');
    await page.locator('#save-program').click();
    const saved = await text(await download);
    const program = JSON.parse(saved.match(/<script id="show-data" type="application\/json">(.*?)<\/script>/s)[1]);
    assert.equal(program.scenes.length, 2);
    assert.equal(program.volume, .4);
    assert.equal(program.scenes[1].performers['voice:0'], 'Alice');
    assert.equal(program.scenes[1].data.audioMix.keepAmbience, false);
    assert.equal((saved.match(/data:video\/mp4;base64,[A-Za-z0-9+/=]+/g) || []).length, 2, 'Les vidéos ne doivent pas être dupliquées par les aperçus.');
    assert.equal(program.scenes[0].data.showTemplate, undefined);
    const stage = await context.newPage(); stage.on('pageerror', error => errors.push(error.message));
    await stage.setContent(saved);
    await stage.waitForFunction(() => queue.length === 2 && !loading);
    assert.equal(await stage.locator('#volume').inputValue(), '40');
    const ids = await stage.evaluate(() => queue.map(e => e.id));
    const popupEvent = stage.waitForEvent('popup');
    await stage.locator('#open-public').click();
    const audience = await popupEvent; audience.on('pageerror', error => errors.push(error.message));
    await audience.waitForFunction(() => window.DoubalgePublic?.ready);
    await stage.locator('#play').click();
    await stage.waitForFunction(() => master.currentTime > .2 && !master.paused && graph !== null);
    await audience.waitForFunction(() => !document.querySelector('video').paused);
    let times = [await stage.evaluate(() => master.currentTime), await audience.evaluate(() => document.querySelector('video').currentTime)];
    assert.ok(Math.abs(times[0] - times[1]) < .18, 'Décalage des écrans : ' + times);
    assert.equal(await audience.evaluate(() => document.querySelector('video').muted), true);
    assert.equal(await audience.evaluate(() => document.querySelector('video').controls), false);
    assert.equal(await audience.locator('#cards').count(), 0);
    assert.equal(await audience.locator('input').count(), 0);
    assert.equal(await audience.locator('#fullscreen').isVisible(), false);
    assert.equal(await audience.evaluate(() => typeof window.DoubalgeAudio), 'undefined');
    await stage.locator('#play').click();
    await audience.waitForFunction(() => document.querySelector('video').paused);
    await stage.evaluate(() => { master.currentTime = 1.4; });
    await audience.waitForFunction(() => Math.abs(document.querySelector('video').currentTime - 1.4) < .1);
    console.log('Deux écrans : vidéo public sans repères, pause/recherche synchronisées, sortie public muette et audio unique vérifiés.');

    await stage.locator('#next').click(); await stage.waitForFunction(() => !loading);
    assert.equal(await stage.locator('#roles input[data-performer="voice:0"]').inputValue(), 'Alice');
    assert.equal(await stage.locator('#ambience').isChecked(), false);
    assert.equal(await stage.evaluate(() => master.paused && black), true);
    await audience.waitForFunction(() => document.querySelector('video').style.visibility === 'hidden');
    await stage.locator('#previous').click(); await stage.waitForFunction(() => !loading);
    await stage.locator('#play').click(); await stage.waitForFunction(() => !master.paused);
    await stage.evaluate(() => { master.currentTime = 2.85; });
    await stage.waitForFunction(() => master.ended && master.paused);
    assert.equal(await stage.evaluate(() => activeId), ids[0]);
    await audience.waitForFunction(() => document.querySelector('video').style.visibility === 'hidden');
    await stage.locator('#auto-next').check();
    await stage.locator('#play').click(); await stage.waitForFunction(() => !master.paused);
    await stage.evaluate(() => { master.currentTime = 2.85; });
    await stage.waitForFunction(id => activeId === id && !loading && !master.paused, ids[1]);
    await audience.waitForFunction(() => !document.querySelector('video').paused);
    assert.equal(await stage.locator('#roles input[data-character="voice:0"]').isChecked(), true);
    assert.equal(await stage.locator('#ambience').isChecked(), false);
    await stage.waitForFunction(() => graph && graph.background.gain.value === 0);
    await audience.close();
    await stage.waitForFunction(() => master.paused && graph === null);
    assert.match(await stage.locator('#status').textContent(), /fermé/);
    console.log('Transitions : attente manuelle, enchaînement automatique et arrêt si l’écran public ferme vérifiés.');

    const safety = await stage.evaluate(() => {
      const sample = queue[0].data;
      const imported = MODEL.parse('<script>window.__intrusion=true</script><script id="impro-data" type="application/json">'
        + JSON.stringify(sample) + '</script>', 'test.html');
      let blocked = false;
      try { MODEL.scene({ ...sample, media: 'https://example.com/video.mp4' }); } catch { blocked = true; }
      return { injected: window.__intrusion, count: imported.scenes.length, blocked };
    });
    assert.deepEqual(safety, { injected: undefined, count: 1, blocked: true });
    await context.setOffline(true);
    const offline = await context.newPage(); offline.on('pageerror', error => errors.push(error.message));
    await offline.setContent(saved); await offline.waitForFunction(() => queue.length === 2 && !loading);
    await offline.locator('#play').click(); await offline.waitForFunction(() => master.currentTime > .1 && graph !== null);
    await offline.locator('#play').click();
    const finalPopup = offline.waitForEvent('popup');
    await offline.locator('#open-public').click();
    const finalAudience = await finalPopup;
    await finalAudience.waitForFunction(() => window.DoubalgePublic?.ready);
    await offline.locator('#play').click();
    await finalAudience.waitForFunction(() => !document.querySelector('video').paused);
    await offline.close({ runBeforeUnload: true });
    await finalAudience.waitForFunction(() => document.querySelector('video').paused && document.querySelector('video').style.visibility === 'hidden');
    console.log('Sauvegarde autonome : ordre, noms, mixages et lecture hors connexion conservés ; aucun code HTML importé exécuté.');
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exit(1); });
