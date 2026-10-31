/* Lecture des exports : on extrait le JSON, sans jamais exécuter le HTML importé. */
(() => {
  'use strict';
  const SCHEMA = 'doublagebasic.show.v1';
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  const identifier = x => typeof x === 'string' && /^[A-Za-z][A-Za-z0-9_-]*:[0-9]{1,4}$/.test(x);
  function media(value, kind) {
    const pattern = kind === 'video' ? /^data:video\/(?:mp4|webm);base64,[A-Za-z0-9+/=\r\n]+$/
      : /^data:audio\/(?:mp4|m4a|wav|x-wav|mpeg|ogg);base64,[A-Za-z0-9+/=\r\n]+$/;
    if (typeof value !== 'string' || !pattern.test(value)) throw Error('Le fichier doit intégrer ses médias, sans adresse réseau.');
    return value;
  }
  function scene(value, name = 'Scène') {
    if (!value || !finite(value.duration) || value.duration <= 0 || value.duration > 86400) throw Error('Durée de scène invalide.');
    if (!Array.isArray(value.characters) || value.characters.length > 100) throw Error('Voix de la scène invalides.');
    const ids = new Set();
    const characters = value.characters.map((p, n) => {
      if (!p || !identifier(p.id) || ids.has(p.id)) throw Error('Identifiant de voix invalide ou répété.');
      ids.add(p.id);
      let photo = null;
      if (p.photo) {
        if (typeof p.photo !== 'string' || !/^(?:data:image\/(?:jpeg|png);base64,)?[A-Za-z0-9+/=\r\n]+$/.test(p.photo)) throw Error('Portrait intégré invalide.');
        photo = p.photo;
      }
      return { id: p.id, label: String(p.label || `Voix ${n + 1}`).slice(0, 120),
        color: typeof p.color === 'string' && /^#[0-9a-f]{6}$/i.test(p.color) ? p.color : '#6f9fcd', photo };
    });
    const list = value.initial || value.intervals, cutList = value.initialCuts || value.cuts;
    if (!Array.isArray(list) || list.length > 10000 || !Array.isArray(cutList) || cutList.length > 10000) throw Error('Repères de scène invalides.');
    const intervals = list.map((i, n) => {
      if (!i || !finite(i.start) || !finite(i.end) || i.start < 0 || i.end > value.duration || i.end <= i.start
          || i.character !== null && !ids.has(i.character)) throw Error('Passage de parole invalide.');
      return { id: String(i.id || 'e' + n).slice(0, 100), start: i.start, end: i.end,
        character: i.character, reviewed: i.reviewed === true };
    });
    const cuts = cutList.map((c, n) => {
      if (!c || !finite(c.time) || c.time <= 0 || c.time >= value.duration) throw Error('Changement de plan invalide.');
      return { id: String(c.id || 'cut' + n).slice(0, 100), time: c.time, reviewed: c.reviewed === true };
    }).sort((a, b) => a.time - b.time);
    const result = { title: String(value.title || name).slice(0, 160), duration: value.duration,
      analysis_id: String(value.analysis_id || ''), source_sha256: String(value.source_sha256 || ''),
      characters, intervals, cuts,
      media: media(value.initial && value.duoAudio ? value.improMedia : value.media, 'video'),
      audioMix: DoubalgeAudio.normaliseMix(value, characters) };
    if (value.duoAudio) result.duoAudio = {
      dialogue: media(value.duoAudio.dialogue, 'audio'), background: media(value.duoAudio.background, 'audio'),
      fade: finite(value.duoAudio.fade) && value.duoAudio.fade > 0 && value.duoAudio.fade <= .1 ? value.duoAudio.fade : .01,
    };
    return result;
  }
  function entry(raw, fallback) {
    const data = scene(raw.data || raw, raw.title || fallback);
    const performers = Object.fromEntries(data.characters.map(p => [p.id, String(raw.performers?.[p.id] || '').slice(0, 100)]));
    return { id: globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + '-' + Math.random().toString(36).slice(2),
      title: String(raw.title || data.title).slice(0, 160), data, performers };
  }
  function programme(raw) {
    if (!raw || raw.schema !== SCHEMA || !Array.isArray(raw.scenes) || raw.scenes.length > 100) throw Error('Programme de spectacle invalide.');
    return { schema: SCHEMA, autoAdvance: raw.autoAdvance === true,
      volume: finite(raw.volume) && raw.volume >= 0 && raw.volume <= 1 ? raw.volume : 1,
      scenes: raw.scenes.map((item, n) => entry(item, `Scène ${n + 1}`)) };
  }
  function parse(text, filename = 'Scène') {
    const name = filename.replace(/\.[^.]+$/, '');
    let raw;
    if (text.trimStart().startsWith('{')) raw = JSON.parse(text);
    else {
      const found = text.match(/<script\b[^>]*\bid\s*=\s*["'](show-data|impro-data|editor-data)["'][^>]*>([\s\S]*?)<\/script\s*>/i);
      if (!found) throw Error('Choisissez un lecteur impro, un éditeur ou un programme exporté par Doubalge.');
      raw = JSON.parse(found[2]);
    }
    if (raw.schema === 'doublagebasic.timeline-edit.v1' && !raw.media) throw Error('Ce JSON contient des corrections, pas la vidéo. Importe-le dans l’éditeur puis exporte son lecteur impro.');
    const result = raw.schema === SCHEMA ? programme(raw) : { schema: SCHEMA, autoAdvance: false, scenes: [entry(raw, name)] };
    if (raw.initial) result.warning = 'Éditeur importé : seules les corrections intégrées au fichier sont disponibles. Pour inclure un brouillon récent, exporte son lecteur impro dans l’éditeur.';
    return result;
  }
  function serialize(entries, autoAdvance, volume = 1) {
    return { schema: SCHEMA, autoAdvance: !!autoAdvance, volume,
      scenes: entries.map(e => ({ title: e.title, data: e.data, performers: e.performers })) };
  }
  globalThis.DoubalgeShow = { SCHEMA, scene, programme, parse, serialize };
})();
