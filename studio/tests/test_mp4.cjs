const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = require('playwright');

(async () => {
  const fixture = path.resolve(process.argv[2]);
  const root = path.resolve(__dirname, '../..');
  const server = spawn(process.env.PYTHON || 'python', ['-u', '-c',
    "import sys; sys.path.insert(0,'studio'); from serveur_editeur import create_server; s=create_server(sys.argv[1],0); print(s.editor_url,flush=True);\ntry: s.serve_forever()\nfinally: s.cleanup()", fixture], { cwd: root });
  let stderr = '';
  server.stderr.on('data', data => { stderr += data; });
  const url = await new Promise((resolve, reject) => {
    server.stdout.once('data', data => resolve(data.toString().trim()));
    server.once('exit', code => reject(Error(`Serveur arrêté (${code}) : ${stderr}`)));
  });
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/usr/bin/chromium', args: ['--no-sandbox'] });
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'doubalge-test-'));
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    assert.equal((await fetch(new URL('/status', url))).status, 403);
    assert.equal((await fetch(new URL('/../README-studio.md', url))).status, 403);
    await page.click('#mp4-open');
    await page.click('#mp4-start');
    await page.waitForFunction(() => document.getElementById('mp4-status').textContent.includes('une ou deux'));
    await page.locator('#mp4-dialog [data-close]').click();
    await page.click('#options-open');
    await page.locator('#remove-voices input[data-character="voice:0"]').check();
    await page.locator('#options-dialog [data-close]').click();
    await page.evaluate(() => change(() => {
      intervals[0].start = .3; intervals[0].character = 'voice:1'; cuts[0].time = 1.;
    }));
    const before = await page.evaluate(() => documentData());
    await page.click('#mp4-open');
    assert.match(await page.locator('#mp4-choices').innerText(), /Voix 1/);
    await page.click('#mp4-start');
    await page.waitForSelector('#mp4-download:visible', { timeout: 30000 });
    const waiting = page.waitForEvent('download');
    await page.click('#mp4-download');
    const download = await waiting;
    assert.match(download.suggestedFilename(), /^entrainement-.*\.mp4$/);
    const file = path.join(directory, 'result.mp4');
    await download.saveAs(file);
    const info = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_streams', '-of', 'json', file]));
    assert.deepEqual(info.streams.map(s => s.codec_name), ['h264', 'aac']);
    assert.deepEqual(await page.evaluate(() => documentData()), before);
    console.log('Éditeur → FFmpeg → téléchargement : vrai MP4 H.264/AAC, corrections et choix audio conservés.');
    // Le second export peut être annulé avant ou pendant la préparation du son.
    await page.click('#mp4-start');
    await page.waitForSelector('#mp4-cancel:enabled');
    await page.click('#mp4-cancel');
    await page.waitForFunction(() => document.getElementById('mp4-status').textContent.includes('Export annulé'), { timeout: 30000 });
    assert.deepEqual(await page.evaluate(() => documentData()), before);
    console.log('Progression, annulation, refus sans jeton et absence de changement des corrections vérifiés.');
    // L'HTML reste autonome : le parcours MP4 explique comment le rouvrir localement.
    const offline = await browser.newPage();
    offline.on('pageerror', error => errors.push(error.message));
    await offline.setContent(fs.readFileSync(fixture, 'utf8'));
    await offline.click('#mp4-open');
    assert.equal(await offline.locator('#mp4-start').isDisabled(), true);
    assert.match(await offline.locator('#mp4-status').innerText(), /Lancer-studio/);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
    server.kill('SIGINT');
    fs.rmSync(directory, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exit(1); });
