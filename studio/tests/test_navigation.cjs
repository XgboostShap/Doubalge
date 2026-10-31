const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

(async () => {
  const html = fs.readFileSync(process.argv[2], 'utf8');
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/usr/bin/chromium',
    headless: true, args: ['--no-sandbox'] });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 }, acceptDownloads: true });
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent(html);
    await page.waitForFunction(() => video.readyState >= 2);
    const baseline = await page.evaluate(() => JSON.stringify(snapshot()));
    assert.equal(await page.locator('#zoom').inputValue(), '180s');
    assert.ok(Math.abs(await page.evaluate(() => timelineView().visible) - 180) < .1);
    for (const [width, height] of [[1280, 600], [1280, 720], [1366, 768], [1920, 1080]]) {
      await page.setViewportSize({ width, height });
      await page.waitForFunction(() => Math.abs(timelineView().visible - 180) < .1);
      const geometry = await page.evaluate(() => ({
        page: document.documentElement.scrollHeight,
        bottom: Math.max(...['timeline-position', 'cut-delete', 'delete', 'status'].map(id => $(id).getBoundingClientRect().bottom)),
        video: $('video').getBoundingClientRect().right,
        form: $('selection-title').getBoundingClientRect().left,
        voices: $('people').getBoundingClientRect().bottom,
        references: $('voice-references').getBoundingClientRect().top,
      }));
      assert.ok(geometry.page <= height && geometry.bottom <= height, JSON.stringify(geometry));
      assert.ok(geometry.video < geometry.form, 'Les corrections doivent occuper l’espace à droite de la vidéo.');
      assert.ok(geometry.voices <= geometry.references, 'Les extraits repères ne doivent pas recouvrir les boutons de voix.');
    }
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.waitForFunction(() => Math.abs(timelineView().visible - 180) < .1);
    const slider = await page.locator('#timeline-position').boundingBox();
    await page.mouse.click(slider.x + slider.width * .85, slider.y + slider.height / 2);
    await page.waitForFunction(() => timelineView().start > 250);
    assert.equal(await page.locator('#follow-playback').isChecked(), false);
    assert.equal(await page.evaluate(() => video.currentTime), 0);
    assert.equal(await page.evaluate(() => JSON.stringify(snapshot())), baseline);
    const labels = await page.locator('#timeline-labels').boundingBox();
    const scroll = await page.locator('#scroll').boundingBox();
    assert.ok(Math.abs(labels.x - scroll.x) < 1, 'Les noms des voix doivent rester visibles.');
    console.log('Vidéo de 8 min 24 : vue de trois minutes, navigation indépendante et noms des voix fixes vérifiés.');

    const id = await page.evaluate(() => intervals.find(i => i.start > 400).id);
    await page.locator(`[data-kind="edit"][data-id="${id}"]`).click();
    const before = await page.evaluate(() => ({ start: current().start, end: current().end, scale: timelineView().scale }));
    const block = await page.locator(`[data-kind="edit"][data-id="${id}"]`).boundingBox();
    await page.mouse.move(block.x + block.width / 2, block.y + block.height / 2);
    await page.mouse.down();
    await page.mouse.move(block.x + block.width / 2 + 30, block.y + block.height / 2, { steps: 8 });
    await page.mouse.up();
    const moved = await page.evaluate(() => current().start);
    assert.ok(Math.abs(moved - before.start - 30 / before.scale) < .05, `Déplacement après défilement : ${moved}`);
    await page.locator('#undo').click();
    assert.equal(await page.evaluate(() => current().start), before.start);
    await page.locator('#redo').click();
    assert.equal(await page.evaluate(() => current().start), moved);
    await page.locator('#zoom').selectOption('30s');
    assert.ok(Math.abs(await page.evaluate(() => timelineView().visible) - 30) < .1);
    const handle = await page.locator(`[data-kind="edit"][data-id="${id}"] [data-handle="right"]`).boundingBox();
    const originalEnd = await page.evaluate(() => current().end);
    await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
    await page.mouse.down();
    await page.mouse.move(handle.x + handle.width / 2 + 20, handle.y + handle.height / 2, { steps: 6 });
    await page.mouse.up();
    assert.ok(await page.evaluate(() => current().end) > originalEnd);
    await page.locator('#cut-select').selectOption('cut-0004');
    assert.equal(await page.evaluate(() => currentCut().time), 400);
    await page.locator('#cut-nudge-next').click();
    assert.equal(await page.evaluate(() => currentCut().time), 400.04);
    console.log('Après défilement : sélection, déplacement réel, poignée, annuler/rétablir et correction de plan vérifiés.');

    await page.locator('#zoom').selectOption('180s');
    await page.locator('#timeline-next').click();
    const endView = await page.evaluate(() => timelineView());
    assert.ok(Math.abs(endView.start + endView.visible - 504.69) < .2);
    const lastId = await page.evaluate(() => intervals.at(-1).id);
    await page.locator('#list-open').click();
    await page.locator('#rows tr').last().locator('button').click();
    assert.equal(await page.evaluate(() => selected), lastId);
    assert.ok(await page.locator(`[data-kind="edit"][data-id="${lastId}"]`).isVisible());
    const startBeforeResize = await page.evaluate(() => timelineView().start);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.waitForFunction(start => Math.abs(timelineView().start - start) < .2, startBeforeResize);
    await page.locator('#zoom').selectOption('1');
    assert.equal(await page.locator('#timeline-position').isDisabled(), true);
    await page.locator('#zoom').selectOption('180s');
    await page.evaluate(() => { panTimeline(0); video.currentTime = 181; });
    await page.waitForFunction(() => video.currentTime >= 181);
    assert.ok(await page.evaluate(() => timelineView().start) < .1);
    await page.locator('#timeline-cursor').click();
    assert.ok(await page.evaluate(() => { const v = timelineView(); return v.start < video.currentTime && video.currentTime < v.start + v.visible; }));
    await page.evaluate(() => { panTimeline(0); });
    await page.locator('#follow-playback').check();
    assert.ok(await page.evaluate(() => timelineView().start) > 0);
    await page.evaluate(() => { panTimeline(0, false); video.currentTime = 179.9; });
    await page.locator('#play').click();
    await page.waitForFunction(() => video.currentTime > 180.2 && timelineView().start > 0);
    await page.locator('#play').click();
    assert.equal(await page.evaluate(() => video.paused), true);
    if (process.env.SCREENSHOT) await page.screenshot({ path: process.env.SCREENSHOT });
    console.log('Fin de vidéo, redimensionnement, vue entière, retour au curseur et suivi pendant la lecture vérifiés.');
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exit(1); });
