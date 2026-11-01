'use strict';
const DATA = JSON.parse(document.getElementById('impro-data').textContent);
const $ = id => document.getElementById(id), video = $('video'), preview = $('preview');
const cuts = DATA.cuts.slice().sort((a, b) => a.time - b.time), intervals = DATA.intervals, cards = [];
const AUDIO = DoubalgeAudio;
let audioMix = AUDIO.normaliseMix(DATA, DATA.characters), audition = null;
video.src = DATA.media; preview.src = DATA.media;
video.muted = !!DATA.duoAudio;
for (const [n, person] of DATA.characters.entries()) {
  const card = document.createElement('div'); card.className = 'portrait';
  card.style.setProperty('--color', person.color); card.dataset.character = person.id;
  if (person.photo) { const image = document.createElement('img'); image.src = 'data:image/jpeg;base64,' + person.photo;
    image.alt = person.label; card.append(image); }
  else { const symbol = document.createElement('span'); symbol.className = 'voice-symbol'; symbol.textContent = 'V' + (n + 1); card.append(symbol); }
  const caption = document.createElement('span'); caption.className = 'caption'; caption.textContent = person.label;
  card.append(caption); $('portraits').append(card); cards.push({ p: person, card, caption });
}
$('portraits').classList.toggle('audio-only', DATA.characters.every(p => !p.photo));
const pending = intervals.filter(i => !i.reviewed).length, pendingCuts = cuts.filter(c => !c.reviewed).length;
$('note').textContent = pending || pendingCuts ? `Repères provisoires : ${pending} passage(s) et ${pendingCuts} plan(s) restent à vérifier.` : 'Repères validés.';
if (DATA.exportedAt) {
  const summary = DATA.correctionSummary;
  $('note').textContent += ' Export du ' + new Date(DATA.exportedAt).toLocaleString('fr-FR')
    + (summary ? ` · ${summary.passages} passages, ${summary.added} ajoutés, ${summary.modified} modifiés, ${summary.removed} supprimés.` : '');
} else $('note').textContent += ' Fichier créé à la préparation de la scène. Exporte un nouveau lecteur depuis l’éditeur pour reprendre les corrections ultérieures.';
const fmt = t => String(Math.floor(t / 60)).padStart(2, '0') + ':' + String(Math.floor(t % 60)).padStart(2, '0');
let audioContext = null, audioReady = null, buffers = null, graph = null, generation = 0;

function keptIds() {
  return new Set(DATA.characters.filter(p => audition ? p.id === audition.character
    : !audioMix.removedCharacters.includes(p.id)).map(p => p.id));
}
function stopAudio() { generation++; if (graph) graph.stop(); graph = null; }
function ensureContext() {
  if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
}
async function prepareAudio() {
  if (!DATA.duoAudio) return;
  ensureContext();
  if (!audioReady) {
    $('audio-status').textContent = 'Préparation du son…';
    audioReady = Promise.all(['background', 'dialogue'].map(async key => {
      const response = await fetch(DATA.duoAudio[key]);
      return audioContext.decodeAudioData(await response.arrayBuffer());
    })).then(value => { buffers = value; $('audio-status').textContent = 'Son prêt.'; })
      .catch(error => { audioReady = null; $('audio-status').textContent = 'Son indisponible : ' + error.message; throw error; });
  }
  await audioReady;
}
async function startAudio() {
  if (!DATA.duoAudio) return;
  const request = ++generation;
  try {
    ensureContext();
    await Promise.all([prepareAudio(), audioContext.resume()]);
    if (request !== generation) return;
    if (graph) graph.stop(); graph = null;
    if (video.paused || video.ended || video.seeking) return;
    const mix = audition ? { removedCharacters: [], keepAmbience: false, keepUnknown: false } : audioMix;
    graph = AUDIO.createGraph(audioContext, buffers, intervals, mix, DATA.duration, {
      offset: video.currentTime, rate: video.playbackRate, volume: Number($('duo-volume').value) / 100,
      fade: DATA.duoAudio.fade || .01, ranges: audition ? [[audition.start, audition.end]] : null,
    });
    $('audio-status').textContent = 'Son synchronisé.';
  } catch (error) {
    stopAudio(); $('audio-status').textContent = 'Son indisponible : ' + error.message;
  }
}
function roleExplanation() {
  if (!DATA.duoAudio) return;
  const kept = DATA.characters.filter(p => !audioMix.removedCharacters.includes(p.id)).map(p => p.label);
  const removed = DATA.characters.filter(p => audioMix.removedCharacters.includes(p.id)).map(p => p.label);
  $('role-explanation').textContent = `Voix conservées : ${kept.join(', ') || 'aucune'}. Voix retirées : ${removed.join(', ') || 'aucune'}. Ambiance : ${audioMix.keepAmbience ? 'conservée' : 'retirée'}.`;
}
function renderMix() {
  for (const checkbox of $('remove-voices').querySelectorAll('input')) checkbox.checked = audioMix.removedCharacters.includes(checkbox.dataset.character);
  $('keep-ambience').checked = audioMix.keepAmbience; $('keep-unknown').checked = audioMix.keepUnknown;
  roleExplanation();
}
function changeMix() {
  audition = null; stopAudio(); renderMix(); if (!video.paused) startAudio(); update();
}
if (DATA.duoAudio) {
  $('duo-controls').hidden = false;
  for (const person of DATA.characters) {
    const label = document.createElement('label'), checkbox = document.createElement('input');
    checkbox.type = 'checkbox'; checkbox.dataset.character = person.id;
    label.style.setProperty('--voice', person.color); label.append(checkbox, document.createTextNode('Retirer ' + person.label));
    checkbox.onchange = () => {
      audioMix.removedCharacters = [...$('remove-voices').querySelectorAll('input:checked')].map(c => c.dataset.character);
      changeMix();
    };
    $('remove-voices').append(label);
  }
  $('keep-ambience').onchange = () => { audioMix.keepAmbience = $('keep-ambience').checked; changeMix(); };
  $('keep-unknown').onchange = () => { audioMix.keepUnknown = $('keep-unknown').checked; changeMix(); };
  $('keep-all').onclick = () => { audioMix = { removedCharacters: [], keepAmbience: true, keepUnknown: true }; changeMix(); };
  $('remove-all').onclick = () => { audioMix.removedCharacters = DATA.characters.map(p => p.id); audioMix.keepUnknown = false; changeMix(); };
  $('duo-volume').oninput = () => { if (graph) graph.master.gain.value = Number($('duo-volume').value) / 100; };
  for (const name of ['play', 'playing']) video.addEventListener(name, startAudio);
  for (const name of ['pause', 'seeking', 'waiting']) video.addEventListener(name, stopAudio);
  video.addEventListener('ended', () => { stopAudio(); audition = null; });
  for (const name of ['seeked', 'ratechange']) video.addEventListener(name, () => { if (!video.paused) startAudio(); });
  for (const person of DATA.characters) {
    if (!person.reference) continue;
    $('voice-references').hidden = false;
    const button = document.createElement('button'); button.textContent = 'Écouter ' + person.label;
    button.onclick = async () => {
      try {
        video.pause(); stopAudio(); audition = { character: person.id, start: person.reference.start, end: person.reference.end };
        video.currentTime = audition.start; ensureContext();
        await Promise.all([prepareAudio(), audioContext.resume()]); await video.play();
      } catch (error) { audition = null; $('audio-status').textContent = error.message; }
    };
    $('voice-references').append(button);
  }
  renderMix();
} else $('original-audio-note').hidden = false;

let previewCut = null;
function update() {
  const t = video.currentTime || 0, flash = t % .5 < .25;
  if (audition && t >= audition.end) { video.pause(); stopAudio(); audition = null; roleExplanation(); }
  const kept = keptIds();
  for (const { p, card, caption } of cards) {
    const active = intervals.filter(i => i.character === p.id && i.start <= t && t < i.end);
    const soon = !active.length && intervals.some(i => i.character === p.id && i.start - 1.5 <= t && t < i.start);
    const role = DATA.duoAudio ? kept.has(p.id) ? 'Film' : 'À vous' : '';
    card.style.opacity = active.length || soon && flash ? '1' : '.35';
    caption.textContent = active.length ? `${role || 'Parole'}${active.some(i => !i.reviewed) ? ' ?' : ''}`
      : soon ? `${role ? role + ' · ' : ''}Bientôt` : (role ? role + ' · ' : '') + p.label;
    card.dataset.state = active.length ? 'speaking' : soon ? 'upcoming' : 'idle';
  }
  $('unknown').hidden = !intervals.some(i => i.character === null && i.start <= t && t < i.end);
  const next = cuts.find(c => t < c.time + .25); $('plan').hidden = !next;
  if (next) {
    if (previewCut !== next.time && preview.readyState >= 1) { preview.currentTime = Math.min(DATA.duration - .02, next.time + .08); previewCut = next.time; }
    const active = t >= next.time && t < next.time + .25, soon = t >= next.time - .5 && t < next.time;
    $('plan').style.opacity = active || soon && flash ? '1' : '.35';
    $('plan-label').textContent = active ? 'Changement de plan' : soon ? 'Plan imminent' : 'Prochain plan';
  }
  $('clock').textContent = fmt(t) + ' / ' + fmt(DATA.duration);
}
async function play() {
  if (video.paused) {
    try { if (DATA.duoAudio) { ensureContext(); await Promise.all([prepareAudio(), audioContext.resume()]); } await video.play(); }
    catch (error) { $('note').textContent = error.message; }
  } else { video.pause(); stopAudio(); }
}
$('play').onclick = play;
$('restart').onclick = () => { stopAudio(); audition = null; video.currentTime = 0; roleExplanation(); update(); };
$('fullscreen').onclick = async () => {
  try { if (document.fullscreenElement) await document.exitFullscreen(); else await $('stage').requestFullscreen(); }
  catch { $('note').textContent = 'Le plein écran est indisponible dans ce navigateur.'; }
};
for (const name of ['timeupdate', 'seeked']) video.addEventListener(name, update);
video.addEventListener('error', () => { $('note').textContent = 'Ouvrez ce fichier dans Chrome, Edge ou Firefox.'; });
document.addEventListener('keydown', e => { if (e.code === 'Space' && !e.target.matches('button,input,select,textarea')) { e.preventDefault(); play(); } });
let lastSync = 0;
function animate() {
  update();
  if (graph && !video.paused && audioContext.currentTime - lastSync > .25) {
    lastSync = audioContext.currentTime;
    const expected = graph.origin.media + (audioContext.currentTime - graph.origin.context) * graph.origin.rate;
    if (Math.abs(expected - video.currentTime) > .08) startAudio();
  }
  requestAnimationFrame(animate);
}
update(); requestAnimationFrame(animate);
if (DATA.showTemplate) {
  $('spectacle').hidden = false;
  $('spectacle').onclick = () => {
    const data = { ...DATA, audioMix: { ...audioMix, removedCharacters: [...audioMix.removedCharacters] } };
    delete data.showTemplate;
    const program = { schema: 'doublagebasic.show.v1', autoAdvance: false,
      scenes: [{ title: data.title || 'Scène', data, performers: {} }] };
    const serialized = JSON.stringify(program).split('<').join(String.fromCharCode(92) + 'u003c');
    const html = DATA.showTemplate.replace('__SHOW_DATA__', () => serialized);
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = 'spectacle.html'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $('note').textContent = 'Spectacle exporté. Ouvre-le pour ajouter les autres scènes et préparer l’écran public.';
  };
}
