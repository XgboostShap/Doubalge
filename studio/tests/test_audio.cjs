const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/usr/bin/chromium',
    headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent(fs.readFileSync(process.argv[2], 'utf8'));
    const results = await page.evaluate(async () => {
      const rate = 24000, duration = 3, positions = [.3, .9, 1.5, 2.45, 2.85];
      const decoder = new OfflineAudioContext(1, duration * rate, rate);
      const buffers = await Promise.all(['background', 'dialogue'].map(async key => {
        const response = await fetch(DATA.duoAudio[key]);
        return decoder.decodeAudioData(await response.arrayBuffer());
      }));
      const amplitude = (samples, t, frequency) => {
        const start = Math.round(t * rate), count = rate / 10;
        let sine = 0, cosine = 0;
        for (let i = 0; i < count; i++) {
          const phase = 2 * Math.PI * frequency * i / rate;
          sine += samples[start + i] * Math.sin(phase);
          cosine += samples[start + i] * Math.cos(phase);
        }
        return 2 * Math.hypot(sine, cosine) / count;
      };
      const outputs = [];
      for (let mask = 0; mask < 16; mask++) for (const ambience of [false, true]) for (const unknown of [false, true]) {
        const mix = { removedCharacters: DATA.characters.filter((p, n) => mask & (1 << n)).map(p => p.id),
          keepAmbience: ambience, keepUnknown: unknown };
        const context = new OfflineAudioContext(1, duration * rate, rate);
        const graph = DoubalgeAudio.createGraph(context, buffers, DATA.intervals, mix, duration);
        const rendered = await context.startRendering(), samples = rendered.getChannelData(0);
        outputs.push({ mask, ambience, unknown,
          voices: positions.map(t => amplitude(samples, t, 440)),
          background: positions.map(t => amplitude(samples, t, 110)) });
        graph.stop();
      }
      return outputs;
    });
    const activeRoles = [[0], [0, 3], [1], [2], []];
    const baseline = results.find(r => r.mask === 0 && r.ambience && r.unknown);
    for (const result of results) for (let index = 0; index < activeRoles.length; index++) {
      const audible = activeRoles[index].length ? activeRoles[index].every(n => !(result.mask & (1 << n))) : result.unknown;
      const voiceRatio = result.voices[index] / baseline.voices[index];
      const backgroundRatio = result.background[index] / baseline.background[index];
      assert.ok(audible ? voiceRatio > .7 : voiceRatio < .12, JSON.stringify({ ...result, index, audible, voiceRatio }));
      assert.ok(result.ambience ? backgroundRatio > .7 : backgroundRatio < .12,
        JSON.stringify({ ...result, index, backgroundRatio }));
    }
    console.log('64 combinaisons rendues : voix cumulées, ambiance indépendante, inconnus et chevauchements vérifiés par mesure du signal.');
    await page.waitForFunction(() => $('video').readyState >= 2);
    assert.equal(await page.evaluate(() => $('video').muted), true, 'Le son original doit être coupé en mode mixage.');
    await page.locator('#play').click();
    await page.waitForFunction(() => graph !== null);
    await page.locator('#remove-voices input[data-character="voice:0"]').check();
    await page.locator('#remove-voices input[data-character="voice:1"]').check();
    await page.locator('#keep-ambience').uncheck();
    await page.waitForFunction(() => graph && graph.background.gain.value === 0);
    assert.deepEqual(await page.evaluate(() => audioMix.removedCharacters), ['voice:0', 'voice:1']);
    await page.locator('#play').click();
    await page.waitForFunction(() => graph === null && $('video').paused);
    await page.evaluate(() => { $('video').currentTime = 1.5; $('video').playbackRate = 1.5; });
    await page.waitForFunction(() => !$('video').seeking);
    assert.equal(await page.evaluate(() => graph), null);
    await page.locator('#play').click();
    await page.waitForFunction(() => graph && graph.origin.rate === 1.5);
    await page.evaluate(() => { $('video').currentTime = .4; });
    await page.waitForFunction(() => graph && graph.origin.media >= .39 && graph.origin.media < .8);
    await page.locator('#play').click();
    await page.waitForFunction(() => graph === null && $('video').paused);
    await page.locator('#remove-all').click();
    assert.equal(await page.evaluate(() => audioMix.removedCharacters.length), 4);
    assert.equal(await page.evaluate(() => audioMix.keepUnknown), false);
    await page.locator('#keep-all').click();
    assert.deepEqual(await page.evaluate(() => audioMix), { removedCharacters: [], keepAmbience: true, keepUnknown: true });
    assert.deepEqual(errors, []);
    console.log('Lecteur réel : choix en direct, pause, recherche, vitesse, tout retirer et tout conserver vérifiés.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exit(1); });
