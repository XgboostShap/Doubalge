/* Moteur partagé : choix cumulables et mixage indépendant du fond sonore. */
(() => {
  'use strict';
  function normaliseMix(data, characters) {
    const known = new Set(characters.map(p => p.id));
    if (data.audioMix) return {
      removedCharacters: [...new Set(data.audioMix.removedCharacters || [])].filter(id => known.has(id)),
      keepAmbience: data.audioMix.keepAmbience !== false,
      keepUnknown: data.audioMix.keepUnknown !== false,
    };
    // Lecture des anciens lecteurs à choix d'un seul rôle.
    const chosen = data.keepCharacter || data.defaultCharacter;
    if (data.duoAudio && chosen) {
      const mode = data.duoMode || data.duoDefaultMode;
      return {
        removedCharacters: characters.filter(p => chosen === 'none' || chosen === 'background'
          || (mode === 'play_one' ? p.id === chosen : p.id !== chosen)).map(p => p.id),
        keepAmbience: chosen !== 'none', keepUnknown: false,
      };
    }
    return { removedCharacters: [], keepAmbience: true, keepUnknown: true };
  }
  function union(ranges) {
    const result = [];
    for (const [a, b] of ranges.sort((x, y) => x[0] - y[0] || x[1] - y[1])) {
      if (b <= a) continue;
      if (result.length && a <= result.at(-1)[1]) result.at(-1)[1] = Math.max(result.at(-1)[1], b);
      else result.push([a, b]);
    }
    return result;
  }
  function windows(intervals, mix, duration) {
    const removed = new Set(mix.removedCharacters);
    const wanted = mix.keepUnknown ? [[0, duration]] : union(intervals.filter(
      i => i.character !== null && !removed.has(i.character)).map(i => [i.start, i.end]));
    const blocked = union(intervals.filter(i => i.character === null ? !mix.keepUnknown
      : removed.has(i.character)).map(i => [i.start, i.end]));
    const result = [];
    let first = 0;
    for (const [a, b] of wanted) {
      let cursor = a;
      while (first < blocked.length && blocked[first][1] <= cursor) first++;
      for (let index = first; index < blocked.length; index++) {
        const [left, right] = blocked[index];
        if (left >= b) break;
        if (left > cursor) result.push([cursor, Math.min(left, b)]);
        cursor = Math.max(cursor, right);
        if (cursor >= b) break;
      }
      if (cursor < b) result.push([cursor, b]);
    }
    return result;
  }
  function schedule(gain, ranges, offset, now, rate, fade = .01) {
    gain.cancelScheduledValues(now);
    gain.setValueAtTime(0, now);
    for (const [start, end] of ranges) {
      if (end <= offset) continue;
      const f = Math.max(.00001, Math.min(fade, (end - start) / 2));
      const left = Math.max(start, offset), at = t => now + (t - offset) / rate;
      const level = Math.max(0, Math.min(1, (left - start) / f, (end - left) / f));
      gain.setValueAtTime(level, at(left));
      if (start + f > left) gain.linearRampToValueAtTime(1, at(start + f));
      if (end - f > left) gain.setValueAtTime(1, at(end - f));
      gain.linearRampToValueAtTime(0, at(end));
    }
  }
  function createGraph(context, buffers, intervals, mix, duration, options = {}) {
    const now = context.currentTime, offset = options.offset || 0, rate = options.rate || 1;
    const master = context.createGain(), voice = context.createGain(), background = context.createGain();
    master.gain.value = options.volume ?? 1;
    background.gain.value = mix.keepAmbience ? 1 : 0;
    voice.connect(master); background.connect(master); master.connect(context.destination);
    schedule(voice.gain, options.ranges || windows(intervals, mix, duration), offset, now, rate, options.fade);
    const sources = [];
    for (const [index, buffer] of buffers.entries()) {
      if (offset >= buffer.duration) continue;
      const source = context.createBufferSource(); source.buffer = buffer;
      source.playbackRate.value = rate; source.connect(index === 0 ? background : voice);
      source.start(now, offset); sources.push(source);
    }
    return { master, voice, background, sources, origin: { media: offset, context: now, rate },
      stop() { for (const source of sources) { try { source.stop(); } catch {} source.disconnect(); }
        voice.disconnect(); background.disconnect(); master.disconnect(); } };
  }
  globalThis.DoubalgeAudio = { normaliseMix, union, windows, createGraph };
})();
