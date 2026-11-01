const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

async function downloadText(download) {
  const stream = await download.createReadStream(), parts = [];
  for await (const part of stream) parts.push(part);
  return Buffer.concat(parts).toString('utf8');
}

(async () => {
  const fixture = fs.readFileSync(process.argv[2], 'utf8');
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/usr/bin/chromium',
    headless: true, args: ['--no-sandbox'] });
  const failures = [];
  try {
    for (const [width, height] of [[1280, 600], [1280, 720], [1366, 768], [1920, 1080]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      page.on('pageerror', error => failures.push(error.message));
      await page.setContent(fixture);
      await page.waitForTimeout(100);
      const geometry = await page.evaluate(() => ({
        scroll: document.documentElement.scrollHeight, height: innerHeight,
        bottom: Math.max(...['video', 'timeline', 'cut-delete', 'delete', 'status'].map(
          id => document.getElementById(id).getBoundingClientRect().bottom)),
        timeline: $('timeline').getBoundingClientRect().height, room: $('scroll').clientHeight,
        wave: waveH,
      }));
      assert.ok(geometry.scroll <= height && geometry.bottom <= height, JSON.stringify(geometry));
      assert.ok(geometry.timeline <= geometry.room, 'Timeline tronquée');
      assert.ok(geometry.wave >= 40, 'Forme d’onde trop petite');
      await page.close();
      console.log(`Écran ${width}×${height} : tous les contrôles visibles.`);
    }

    const page = await browser.newPage({ viewport: { width: 1366, height: 768 }, acceptDownloads: true });
    page.on('pageerror', error => failures.push(error.message));
    await page.setContent(fixture);
    await page.waitForFunction(() => $('video').readyState >= 2);
    const automatic = await page.evaluate(() => JSON.stringify([DATA.automatic, DATA.automaticCuts]));
    await page.locator('#wave-options').click();
    await page.locator('#wave-size').selectOption('160');
    await page.locator('#wave-gain').evaluate(input => { input.value = 4; input.dispatchEvent(new Event('input')); });
    await page.locator('#wave-dialog [data-close]').click();
    assert.equal(await page.evaluate(() => waveGain), 4);
    await page.locator('[data-kind="edit"][data-id="e000000"]').click();
    await page.locator('#start').fill('0.12');
    await page.locator('#start').press('Tab');
    assert.equal(await page.evaluate(() => current().start), .12);
    await page.locator('#undo').click();
    assert.equal(await page.evaluate(() => current().start), .1);
    await page.locator('#redo').click();
    assert.equal(await page.evaluate(() => current().start), .12);

    // Drag réel du bloc vers une autre voix, puis ajustement de sa poignée.
    let box = await page.locator('[data-kind="edit"][data-id="e000000"]').boundingBox();
    const rh = await page.evaluate(() => RH);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 35, box.y + box.height / 2 + rh, { steps: 8 });
    await page.mouse.up();
    assert.equal(await page.evaluate(() => current().character), 'voice:1');
    const beforeBound = await page.evaluate(() => current().start);
    box = await page.locator('[data-kind="edit"][data-id="e000000"] [data-handle="left"]').boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 18, box.y + box.height / 2, { steps: 6 });
    await page.mouse.up();
    assert.ok(await page.evaluate(() => current().start) > beforeBound);
    console.log('Parole : saisie, annuler/rétablir, déplacement et bornes vérifiés.');

    await page.locator('#cut-select').selectOption('cut-0000');
    await page.locator('#cut-nudge-next').click();
    assert.equal(await page.evaluate(() => currentCut().time), .84);
    assert.equal(await page.evaluate(() => currentCut().reviewed), true);
    const beforeCut = await page.evaluate(() => currentCut().time);
    box = await page.locator('[data-kind="cut"][data-id="cut-0000"]').boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 25, box.y + box.height / 2, { steps: 6 });
    await page.mouse.up();
    assert.ok(await page.evaluate(() => currentCut().time) > beforeCut);
    await page.locator('#cut-time').fill('0.95');
    await page.locator('#cut-time').press('Tab');
    assert.equal(await page.evaluate(() => currentCut().time), .95);
    await page.locator('#compare-auto').check();
    assert.equal(await page.evaluate(() => JSON.stringify([DATA.automatic, DATA.automaticCuts])), automatic);
    console.log('Plans : déplacement, saisie, pas image et conservation de l’analyse initiale vérifiés.');

    await page.locator('#options-open').click();
    await page.locator('#remove-voices input[data-character="voice:0"]').check();
    await page.locator('#remove-voices input[data-character="voice:1"]').check();
    await page.locator('#keep-ambience').uncheck();
    await page.locator('#options-dialog [data-close]').click();
    // Ajout, nouvelle attribution et suppression doivent aussi traverser l’export.
    await page.locator('#seek').fill('2.85');
    await page.locator('#go').click();
    await page.locator('#add').click();
    await page.locator('#character').selectOption('voice:3');
    const addedId = await page.evaluate(() => current().id);
    assert.ok(addedId.startsWith('edit-'));
    await page.locator('[data-kind="edit"][data-id="e000004"]').click();
    await page.locator('#delete').click();
    // Les données de correction et le lecteur exporté doivent contenir les modifications courantes.
    await page.evaluate(() => { people[0].label = '</script><script>globalThis.__bad=true</script>'; });
    let pending = page.waitForEvent('download');
    await page.locator('#export').click();
    const corrections = JSON.parse(await downloadText(await pending));
    pending = page.waitForEvent('download');
    await page.locator('#impro').click();
    const html = await downloadText(await pending);
    const playerData = JSON.parse(html.match(/<script id="impro-data" type="application\/json">(.*?)<\/script>/s)[1]);
    assert.ok((await pending).suggestedFilename().startsWith('version-impro-test-edi-'));
    assert.deepEqual(playerData.intervals, corrections.intervals);
    assert.deepEqual(playerData.cuts, corrections.cuts);
    assert.deepEqual(playerData.audioMix, corrections.audioMix);
    assert.deepEqual(playerData.audioMix.removedCharacters, ['voice:0', 'voice:1']);
    assert.equal(playerData.audioMix.keepAmbience, false);
    assert.equal(playerData.characters[0].label, '</script><script>globalThis.__bad=true</script>');
    assert.equal(playerData.intervals.find(i => i.id === addedId).character, 'voice:3');
    assert.equal(playerData.intervals.some(i => i.id === 'e000004'), false);
    assert.equal(playerData.correctionSummary.added, 1);
    assert.equal(playerData.correctionSummary.removed, 1);
    assert.ok(playerData.correctionSummary.modified > 0);
    assert.ok(Number.isFinite(Date.parse(playerData.exportedAt)));
    assert.deepEqual(playerData.correctionSummary, corrections.correctionSummary);
    pending = page.waitForEvent('download');
    await page.locator('#spectacle').click();
    const showHtml = await downloadText(await pending);
    const showData = JSON.parse(showHtml.match(/<script id="show-data" type="application\/json">(.*?)<\/script>/s)[1]);
    assert.deepEqual(showData.scenes[0].data.intervals, corrections.intervals);
    assert.deepEqual(showData.scenes[0].data.audioMix, corrections.audioMix);
    const show = await browser.newPage();
    show.on('pageerror', error => failures.push(error.message));
    await show.setContent(showHtml);
    await show.waitForFunction(() => queue.length === 1 && !loading);
    assert.equal(await show.evaluate(() => globalThis.__bad), undefined);
    console.log('Exports : JSON et lecteur impro conservent les corrections et les choix audio cumulés.');

    const previewOpened = page.waitForEvent('popup');
    await page.locator('#reader-preview').click();
    const player = await previewOpened;
    player.on('pageerror', error => failures.push(error.message));
    await player.waitForFunction(() => document.getElementById('video').readyState >= 2);
    assert.deepEqual(await player.evaluate(() => DATA.intervals), corrections.intervals);
    assert.deepEqual(await player.evaluate(() => DATA.cuts), corrections.cuts);
    assert.equal(await player.evaluate(() => globalThis.__bad), undefined);
    await player.locator('#play').click();
    await player.waitForFunction(() => document.getElementById('video').currentTime > .1);
    await player.locator('#play').click();
    assert.ok(await player.evaluate(() => document.getElementById('video').paused));
    await page.locator('#add').click();
    assert.equal(await page.locator('#reader-preview').isVisible(), false, 'Un ancien export ne doit pas être proposé après une nouvelle correction.');
    console.log('Lecteur impro : vidéo autonome, lecture et pause vérifiées.');
    assert.deepEqual(failures, []);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.stack); process.exit(1); });
