const assert = require('node:assert/strict');
require('../downloads.js');
(async () => {
  const data = { text: 'x'.repeat(256 * 1024 - 1) + '😀</script>' + 'y'.repeat(600000),
    media: 'data:video/mp4;base64,' + 'ABCD'.repeat(200000), optional: undefined,
    list: [true, 12.5, null, { label: 'Élodie "voix"' }] };
  const template = '<script id="data" type="application/json">__DATA__</script><script>window.ok=true</script>';
  const html = await DoubalgeDownloads.htmlBlob(template, '__DATA__', data).text();
  const raw = html.match(/<script id="data" type="application\/json">(.*?)<\/script>/s)[1];
  assert.deepEqual(JSON.parse(raw), JSON.parse(JSON.stringify(data)));
  assert.ok(!raw.includes('</script>'));
  assert.throws(() => DoubalgeDownloads.htmlBlob('__DATA____DATA__', '__DATA__', data));
  assert.throws(() => DoubalgeDownloads.htmlBlob(undefined, '__DATA__', data));
  console.log('Export par morceaux : médias longs, caractères Unicode entre deux morceaux, échappement HTML et gabarits invalides vérifiés.');
})().catch(error => { console.error(error); process.exit(1); });
