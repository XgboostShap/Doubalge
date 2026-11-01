/* Assemble les exports sans construire une chaîne contenant tous les médias. */
(() => {
  'use strict';
  const CHUNK = 256 * 1024;
  function* jsonParts(value) {
    if (typeof value === 'string') {
      yield '"';
      for (let at = 0; at < value.length; at += CHUNK)
        yield JSON.stringify(value.slice(at, at + CHUNK)).slice(1, -1).replace(/</g, '\\u003c');
      yield '"';
    } else if (Array.isArray(value)) {
      yield '[';
      for (let n = 0; n < value.length; n++) { if (n) yield ','; yield* jsonParts(value[n] ?? null); }
      yield ']';
    } else if (value && typeof value === 'object') {
      yield '{'; let separator = '';
      for (const [key, child] of Object.entries(value)) {
        if (child === undefined) continue;
        yield separator; yield* jsonParts(key); yield ':'; yield* jsonParts(child); separator = ',';
      }
      yield '}';
    } else yield JSON.stringify(value);
  }
  function htmlBlob(template, marker, data) {
    if (typeof template !== 'string' || template.split(marker).length !== 2)
      throw Error('Gabarit d’export absent ou incomplet. Actualise cet éditeur avec la dernière version de studio.');
    const at = template.indexOf(marker);
    return new Blob([template.slice(0, at), ...jsonParts(data), template.slice(at + marker.length)],
      { type: 'text/html;charset=utf-8' });
  }
  function download(blob, filename) {
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
    // Laisser au navigateur le temps de prendre en charge les fichiers volumineux.
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  globalThis.DoubalgeDownloads = { jsonParts, htmlBlob, download };
})();
