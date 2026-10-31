'use strict';
const $ = id => document.getElementById(id), master = $('master'), preview = $('preview');
const MODEL = DoubalgeShow, AUDIO = DoubalgeAudio, PUBLIC_PAGE = __PUBLIC_TEMPLATE_JSON__;
const PUBLIC_NAME = 'DoubalgePublic-' + (globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2));
let queue = [], activeId = null, loading = false, loadVersion = 0, publicWindow = null, publicWasOpen = false;
let black = true, playIntent = false, audioContext = null, audioState = null, graph = null, audioGeneration = 0, cards = [];
let previewCut = null, dirty = false;
const current = () => queue.find(e => e.id === activeId) || null;
const index = () => queue.findIndex(e => e.id === activeId);
const fmt = t => String(Math.floor(Math.max(0, t) / 60)).padStart(2, '0') + ':' + String(Math.floor(Math.max(0, t) % 60)).padStart(2, '0');
function message(text, error = false) { $('status').textContent = text; $('status').title = text; $('status').classList.toggle('error', error); }
function changed() { dirty = true; message('Programme modifié. Enregistre le spectacle pour conserver les scènes, les noms et les réglages.'); }
function stopAudio() { audioGeneration++; if (graph) graph.stop(); graph = null; }
function pause(makeBlack = false) { playIntent = false; stopAudio(); master.pause(); if (makeBlack) black = true; syncPublic(); buttons(); }
function fail(error) { pause(true); message(error.message || String(error), true); }
const action = fn => (...args) => { try { return Promise.resolve(fn(...args)).catch(fail); } catch (error) { fail(error); } };

function publicAPI() {
  if (!publicWindow) return null;
  try {
    if (publicWindow.closed) {
      publicWindow = null;
      if (publicWasOpen) { publicWasOpen = false; pause(true); message('L’écran public a été fermé. Lecture arrêtée ; rouvre-le avant de reprendre.', true); }
      return null;
    }
    return publicWindow.DoubalgePublic || null;
  } catch { publicWindow = null; pause(true); message('L’écran public a changé de page. Rouvre la sortie public.', true); return null; }
}
function sceneKey() { return activeId ? activeId + '-' + loadVersion : null; }
function syncPublic() {
  const api = publicAPI();
  $('public-state').textContent = api ? api.ready ? black ? 'Écran public connecté — noir d’attente' : 'Écran public connecté — vidéo seule, son unique sur le PC' : 'Préparation de l’écran public…'
    : 'Écran public fermé — répétition locale possible';
  if (api) {
    api.sync({ key: sceneKey(), time: master.currentTime || 0, rate: master.playbackRate,
      playing: !master.paused && !master.ended && !loading, black: black || loading || !current() });
    if (api.error) { if (!black) pause(true); message(api.error, true); }
    else if (api.fullscreenError) message(api.fullscreenError, true);
  }
}
async function openPublic() {
  if (publicWindow && !publicWindow.closed) { publicWindow.focus(); return; }
  const win = window.open('', PUBLIC_NAME, 'popup,width=1000,height=650');
  if (!win) throw Error('Le navigateur a bloqué la fenêtre. Autorise les fenêtres pour cette page puis réessaie.');
  publicWindow = win; publicWasOpen = true;
  win.document.open(); win.document.write(PUBLIC_PAGE); win.document.close();
  for (let n = 0; n < 40 && !publicAPI(); n++) await new Promise(resolve => setTimeout(resolve, 50));
  const api = publicAPI();
  if (!api) throw Error('Impossible de préparer la fenêtre public.');
  api.load(current()?.data.media || null, sceneKey()); syncPublic();
  message('Déplace la fenêtre Public sur le second écran et active son plein écran. Le son reste unique sur ce PC.');
}
async function waitPublic(version) {
  for (let n = 0; n < 120; n++) {
    if (version !== loadVersion || !playIntent) return false;
    const api = publicAPI();
    if (api?.error) throw Error(api.error);
    if (!api || api.ready) return true;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw Error('L’écran public n’est pas prêt. Vérifie cette fenêtre avant de relancer.');
}
function metadata(video) {
  if (video.readyState >= 1) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(Error('Chargement vidéo trop long.')), 15000);
    const done = () => finish(), error = () => finish(Error('Cette scène ne peut pas être lue dans ce navigateur.'));
    function finish(problem) { clearTimeout(timer); video.removeEventListener('loadedmetadata', done); video.removeEventListener('error', error); problem ? reject(problem) : resolve(); }
    video.addEventListener('loadedmetadata', done); video.addEventListener('error', error);
  });
}
async function selectScene(id, autoplay = false) {
  const entry = queue.find(e => e.id === id); if (!entry) return;
  pause(true); const version = ++loadVersion; loading = true; activeId = id; previewCut = null;
  audioState = { data: entry.data, version, buffers: null, promise: null };
  master.muted = !!entry.data.duoAudio; master.volume = Number($('volume').value) / 100; master.playbackRate = 1;
  master.src = entry.data.media; master.load(); preview.src = entry.data.media; preview.load();
  const api = publicAPI(); if (api) api.load(entry.data.media, sceneKey());
  renderQueue(); renderRoles(); buttons();
  message('Préparation de ' + entry.title + '…');
  try {
    await metadata(master);
    if (version !== loadVersion) return;
    loading = false; master.currentTime = 0; $('seek').max = entry.data.duration;
    buttons(); update(); syncPublic();
    message(entry.title + ' prête. L’écran public reste noir jusqu’à Lire.');
    if (autoplay) await play();
  } catch (error) { if (version === loadVersion) { loading = false; fail(error); } }
}
function ensureContext() { if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)(); }
async function prepareAudio(state = audioState) {
  if (!state?.data.duoAudio) return;
  ensureContext();
  if (!state.promise) state.promise = Promise.all(['background', 'dialogue'].map(async key => {
    const response = await fetch(state.data.duoAudio[key]);
    return audioContext.decodeAudioData(await response.arrayBuffer());
  })).then(buffers => { state.buffers = buffers; }).catch(error => { state.promise = null; throw error; });
  await state.promise;
}
async function startAudio() {
  if (!current()?.data.duoAudio) return;
  const state = audioState, request = ++audioGeneration;
  try {
    ensureContext(); await Promise.all([prepareAudio(state), audioContext.resume()]);
    if (request !== audioGeneration || state !== audioState || master.paused || master.ended || master.seeking) return;
    if (graph) graph.stop();
    graph = AUDIO.createGraph(audioContext, state.buffers, state.data.intervals, state.data.audioMix, state.data.duration,
      { offset: master.currentTime, rate: master.playbackRate, volume: Number($('volume').value) / 100,
        fade: state.data.duoAudio.fade || .01 });
  } catch (error) { if (state === audioState) fail(error); }
}
async function play() {
  if (!current() || loading) return;
  if (playIntent || !master.paused) { pause(); return; }
  const version = loadVersion; playIntent = true; buttons();
  try {
    if (current().data.duoAudio) { ensureContext(); await Promise.all([prepareAudio(), audioContext.resume()]); }
    if (!await waitPublic(version) || version !== loadVersion || !playIntent) return;
    black = false; await master.play(); syncPublic();
  } catch (error) { if (version === loadVersion) fail(error); }
}
async function advance(delta) {
  if (loading) return;
  const next = queue[index() + delta];
  if (next) await selectScene(next.id, false);
}
function move(id, delta) {
  const from = queue.findIndex(e => e.id === id), to = from + delta;
  if (to < 0 || to >= queue.length) return;
  [queue[from], queue[to]] = [queue[to], queue[from]]; renderQueue(); buttons(); changed();
}
async function remove(id) {
  const old = queue.findIndex(e => e.id === id), wasActive = activeId === id;
  if (wasActive) pause(true);
  queue = queue.filter(e => e.id !== id); changed();
  if (wasActive && queue.length) await selectScene(queue[Math.min(old, queue.length - 1)].id);
  else if (wasActive) {
    activeId = null; loadVersion++; audioState = null; master.removeAttribute('src'); master.load();
    preview.removeAttribute('src'); preview.load(); publicAPI()?.load(null, null); renderRoles();
  }
  renderQueue(); buttons(); update();
}
function renderQueue() {
  $('queue').replaceChildren();
  for (const [position, entry] of queue.entries()) {
    const li = document.createElement('li'); li.className = 'scene'; li.classList.toggle('active', entry.id === activeId); li.dataset.id = entry.id;
    const name = document.createElement('input'); name.value = entry.title; name.setAttribute('aria-label', 'Titre de la scène ' + (position + 1));
    name.oninput = () => { entry.title = name.value.slice(0, 160); changed(); buttons(); };
    const description = document.createElement('small'); description.textContent = `${position + 1} · ${fmt(entry.data.duration)} · ${entry.data.characters.length} voix`;
    const actions = document.createElement('div'); actions.className = 'toolbar';
    for (const [text, key, handler, disabled] of [
      ['Préparer', 'prepare', () => selectScene(entry.id), loading],
      ['↑', 'up', () => move(entry.id, -1), position === 0],
      ['↓', 'down', () => move(entry.id, 1), position === queue.length - 1],
      ['Retirer', 'remove', () => remove(entry.id), false],
    ]) { const b = document.createElement('button'); b.textContent = text; b.dataset.action = key; b.disabled = disabled; b.onclick = action(handler); actions.append(b); }
    li.append(name, description, actions); $('queue').append(li);
  }
  $('queue-summary').textContent = queue.length ? `${queue.length} scène(s) · ${fmt(queue.reduce((sum, e) => sum + e.data.duration, 0))} au total` : 'Aucune scène';
}
function mixChanged() {
  changed(); stopAudio(); if (!master.paused) startAudio(); update();
}
function renderRoles() {
  $('roles').replaceChildren(); $('cards').replaceChildren(); cards = [];
  const entry = current(); $('ambience').disabled = $('unknown').disabled = !entry?.data.duoAudio; if (!entry) return;
  for (const [number, p] of entry.data.characters.entries()) {
    const role = document.createElement('div'); role.className = 'role'; role.style.setProperty('--voice', p.color);
    const label = document.createElement('label'), checkbox = document.createElement('input');
    checkbox.type = 'checkbox'; checkbox.dataset.character = p.id; checkbox.checked = !!entry.data.duoAudio && entry.data.audioMix.removedCharacters.includes(p.id);
    checkbox.disabled = !entry.data.duoAudio; label.append(checkbox, document.createTextNode(' Je joue ' + p.label));
    checkbox.onchange = () => { entry.data.audioMix.removedCharacters = [...$('roles').querySelectorAll('input[type=checkbox]:checked')].map(c => c.dataset.character); mixChanged(); };
    const tag = document.createElement('span'); tag.className = 'muted'; tag.textContent = 'voix du film retirée';
    const performer = document.createElement('input'); performer.type = 'text'; performer.maxLength = 100;
    performer.placeholder = 'Nom de l’improvisateur (facultatif)'; performer.value = entry.performers[p.id] || '';
    performer.setAttribute('aria-label', 'Improvisateur pour ' + p.label); performer.dataset.performer = p.id;
    performer.oninput = () => { entry.performers[p.id] = performer.value; changed(); };
    role.append(label, tag, performer); $('roles').append(role);
    const card = document.createElement('div'); card.className = 'card'; card.dataset.character = p.id; card.style.setProperty('--voice', p.color);
    if (p.photo) { const image = document.createElement('img'); image.src = p.photo.startsWith('data:') ? p.photo : 'data:image/jpeg;base64,' + p.photo; image.alt = p.label; card.append(image); }
    else { const symbol = document.createElement('span'); symbol.className = 'symbol'; symbol.textContent = 'V' + (number + 1); card.append(symbol); }
    const name = document.createElement('span'), state = document.createElement('div'); name.className = 'name'; state.className = 'state'; card.append(name, state); $('cards').append(card); cards.push({ p, card, name, state });
  }
  $('ambience').checked = entry.data.audioMix.keepAmbience; $('unknown').checked = entry.data.audioMix.keepUnknown;
  $('ambience').disabled = $('unknown').disabled = !entry.data.duoAudio;
  $('audio-note').textContent = entry.data.duoAudio ? 'Cases cochées : voix retirées du film. Les chevauchements et les résidus de séparation restent à vérifier.' : 'Sans pistes séparées : son intégré au fichier, réglages des voix indisponibles. Recrée cette scène avec la préparation audio si nécessaire.';
}
function buttons() {
  const entry = current(), at = index();
  for (const button of $('queue').querySelectorAll('[data-action=prepare]')) button.disabled = loading;
  $('play').disabled = $('stop').disabled = !entry || loading;
  $('previous').disabled = !entry || at <= 0 || loading; $('next').disabled = !entry || at >= queue.length - 1 || loading;
  $('play').textContent = playIntent && master.paused ? 'Annuler préparation' : master.paused ? 'Lire' : 'Pause';
  $('scene-title').textContent = entry ? `${at + 1} / ${queue.length} — ${entry.title}` : 'Ajoute les scènes préparées dans l’éditeur';
  $('seek').disabled = !entry || loading;
}
function update() {
  const entry = current(), t = master.currentTime || 0;
  $('clock').textContent = fmt(t) + ' / ' + fmt(entry?.data.duration || 0);
  if (document.activeElement !== $('seek')) $('seek').value = t;
  $('standby').hidden = !!entry && !loading;
  $('standby').textContent = !entry ? 'En attente d’une scène' : loading ? 'Préparation…' : 'Scène prête — Lire pour démarrer';
  if (!entry) { $('next-plan').hidden = true; $('next-voices').textContent = ''; return; }
  const soonNames = [];
  for (const { p, card, name, state } of cards) {
    const active = entry.data.intervals.some(i => i.character === p.id && i.start <= t && t < i.end);
    const soon = !active && entry.data.intervals.some(i => i.character === p.id && i.start - 1.5 <= t && t < i.start);
    const performer = entry.performers[p.id] || p.label, separated = !!entry.data.duoAudio,
      impro = separated && entry.data.audioMix.removedCharacters.includes(p.id);
    name.textContent = impro || !separated ? performer : p.label; name.title = p.label + (impro ? ' — ' + performer : '');
    state.textContent = active ? (!separated ? 'Parole' : impro ? 'À vous !' : 'Film')
      : soon ? (!separated ? 'Bientôt' : impro ? 'À vous bientôt' : 'Film bientôt') : p.label;
    card.style.opacity = active || soon && t % .5 < .25 ? '1' : '.35';
    card.dataset.state = active ? 'speaking' : soon ? 'upcoming' : 'idle';
    if (soon) soonNames.push(impro || !separated ? performer : p.label + ' (film)');
  }
  $('next-voices').textContent = soonNames.length ? 'Bientôt : ' + soonNames.join(' · ') : '';
  const next = entry.data.cuts.find(c => t < c.time + .25); $('next-plan').hidden = !next;
  if (next) {
    if (previewCut !== next.time && preview.readyState >= 1) { preview.currentTime = Math.min(entry.data.duration - .02, next.time + .08); previewCut = next.time; }
    const soon = t >= next.time - .5 && t < next.time, active = t >= next.time && t < next.time + .25;
    $('next-plan').style.opacity = active || soon && t % .5 < .25 ? '1' : '.35';
    $('plan-label').textContent = active ? 'Changement de plan' : soon ? 'Plan imminent' : 'Prochain plan';
  }
}
async function importFiles(files, replace = false) {
  const added = [], failures = [], warnings = []; let autoAdvance = false, volume = 1;
  for (const file of files) {
    try {
      if (!/\.(?:html|json)$/i.test(file.name)) throw Error('Choisis le lecteur HTML exporté, pas le fichier vidéo brut.');
      const parsed = MODEL.parse(await file.text(), file.name); added.push(...parsed.scenes); autoAdvance = parsed.autoAdvance;
      volume = parsed.volume ?? 1;
      if (parsed.warning) warnings.push(parsed.warning);
    }
    catch (error) { failures.push(file.name + ' : ' + error.message); }
  }
  if (!added.length) { message(failures.join(' · ') || 'Ce fichier ne contient aucune scène.', true); return; }
  if (queue.length + added.length > 100 && !replace || added.length > 100) throw Error('Le programme accepte au maximum 100 scènes.');
  if (replace) { pause(true); queue = []; activeId = null; $('auto-next').checked = autoAdvance; $('volume').value = volume * 100; }
  queue.push(...added); renderQueue(); changed();
  if (!current()) await selectScene(queue[0].id);
  if (failures.length) message(failures.join(' · '), true);
  else if (warnings.length) message(warnings.join(' · '));
}
function saveProgramme() {
  if (!queue.length) { message('Ajoute au moins une scène avant d’enregistrer.', true); return; }
  const documentCopy = document.documentElement.cloneNode(true);
  documentCopy.querySelector('#show-data').textContent = JSON.stringify(MODEL.serialize(queue, $('auto-next').checked, Number($('volume').value) / 100)).split('<').join(String.fromCharCode(92) + 'u003c');
  for (const id of ['master', 'preview']) documentCopy.querySelector('#' + id).removeAttribute('src');
  for (const id of ['queue', 'roles', 'cards']) documentCopy.querySelector('#' + id).replaceChildren();
  const url = URL.createObjectURL(new Blob(['<!doctype html>', documentCopy.outerHTML], { type: 'text/html;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url; link.download = 'spectacle.html'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); dirty = false; message('Spectacle enregistré avec toutes ses scènes et leurs réglages. Ouvre ce HTML pour le retrouver hors connexion.');
}
$('add-scenes').onclick = () => $('scene-files').click();
$('scene-files').onchange = action(async event => { await importFiles([...event.target.files]); event.target.value = ''; });
$('load-program').onclick = () => $('program-file').click();
$('program-file').onchange = action(async event => { await importFiles([...event.target.files], true); event.target.value = ''; });
$('save-program').onclick = action(saveProgramme); $('open-public').onclick = action(openPublic);
$('play').onclick = action(play); $('stop').onclick = () => { pause(true); master.currentTime = 0; syncPublic(); update(); };
$('previous').onclick = action(() => advance(-1)); $('next').onclick = action(() => advance(1));
$('ambience').onchange = () => { if (current()) { current().data.audioMix.keepAmbience = $('ambience').checked; mixChanged(); } };
$('unknown').onchange = () => { if (current()) { current().data.audioMix.keepUnknown = $('unknown').checked; mixChanged(); } };
$('volume').oninput = () => { master.volume = Number($('volume').value) / 100; if (graph) graph.master.gain.value = Number($('volume').value) / 100; changed(); };
$('auto-next').onchange = changed;
$('seek').oninput = () => { if (current()) { master.currentTime = Number($('seek').value); syncPublic(); } };
$('help').onclick = () => $('help-dialog').showModal(); $('close-help').onclick = () => $('help-dialog').close();
$('impro-fullscreen').onclick = action(async () => { if (document.fullscreenElement) await document.exitFullscreen(); else await $('stage').requestFullscreen(); });
master.addEventListener('play', () => { playIntent = true; black = false; startAudio(); buttons(); syncPublic(); });
master.addEventListener('playing', startAudio);
master.addEventListener('pause', () => { playIntent = false; stopAudio(); buttons(); syncPublic(); });
for (const event of ['seeking', 'waiting']) master.addEventListener(event, stopAudio);
for (const event of ['seeked', 'ratechange']) master.addEventListener(event, () => { if (!master.paused) startAudio(); syncPublic(); });
master.addEventListener('ended', action(async () => {
  if (!master.ended || loading) return;
  pause(true); const next = queue[index() + 1];
  if (next && $('auto-next').checked) await selectScene(next.id, true);
  else message(next ? 'Scène terminée. Prépare la suivante avec Suivante.' : 'Spectacle terminé.');
}));
document.addEventListener('keydown', action(event => {
  if (event.target.matches('input,button,select,textarea') || $('help-dialog').open) return;
  if (event.code === 'Space') { event.preventDefault(); return play(); }
  if (event.key.toLowerCase() === 'n') return advance(1);
  if (event.key.toLowerCase() === 'p') return advance(-1);
  if (event.key.toLowerCase() === 'b') pause(true);
}));
let lastSync = 0;
function animate() {
  update();
  if (graph && !master.paused && audioContext.currentTime - lastSync > .25) {
    lastSync = audioContext.currentTime;
    const expected = graph.origin.media + (audioContext.currentTime - graph.origin.context) * graph.origin.rate;
    if (Math.abs(expected - master.currentTime) > .08) startAudio();
  }
  requestAnimationFrame(animate);
}
setInterval(syncPublic, 100); requestAnimationFrame(animate);
function closeController() {
  stopAudio();
  try { if (publicWindow && !publicWindow.closed) publicWindow.DoubalgePublic?.load(null, null); } catch {}
}
window.addEventListener('pagehide', closeController);
window.addEventListener('beforeunload', closeController);
(async () => {
  const raw = JSON.parse($('show-data').textContent), program = MODEL.programme(raw);
  queue = program.scenes; $('auto-next').checked = program.autoAdvance; $('volume').value = program.volume * 100;
  renderQueue(); buttons(); if (queue.length) await selectScene(queue[0].id);
})().catch(fail);
