/* Export FFmpeg local : la requête ne contient que les corrections, jamais une nouvelle analyse. */
(() => {
  let running = false, exportName = '', polling = false, exportedState = null;
  const status = text => { $('mp4-status').textContent = text; };
  async function api(path, body) {
    const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST',
      headers: { 'X-Doubalge-Token': globalThis.DOUBALGE_EXPORT_TOKEN, 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    if (!response.ok) { let message = 'Le service local ne répond plus. Garde Lancer-studio ouvert.';
      try { message = (await response.json()).error || message; } catch {} throw Error(message); }
    return path === '/video' ? response.blob() : response.json();
  }
  function estimate() {
    const bitrate = $('mp4-profile').value === 'mail' ? 514 : 1896;
    $('mp4-estimate').textContent = `Durée : ${fmt(duration)} · taille indicative : ${(duration * bitrate / 8000).toFixed(1)} Mo.`;
  }
  async function poll() {
    if (polling) return;
    polling = true;
    try {
      const state = await api('/status');
      $('mp4-progress').value = state.progress;
      running = state.status === 'running';
      $('mp4-start').disabled = running;
      $('mp4-cancel').disabled = !running;
      if (running) status(`Encodage sur ce PC : ${Math.round(state.progress * 100)} %…`);
      else if (state.status === 'done') { status('MP4 prêt avec les corrections figées au lancement. Télécharge-le puis vérifie l’image et le son avant de le partager.'); $('mp4-download').hidden = false; }
      else if (state.status === 'cancelled') status('Export annulé. Tes corrections sont conservées.');
      else if (state.status === 'error') status(state.error);
    } catch (error) { running = false; status(error.message); $('mp4-start').disabled = false; $('mp4-cancel').disabled = true; }
    finally { polling = false; }
    if (running) setTimeout(poll, 500);
  }
  $('mp4-open').onclick = () => {
    $('mp4-choices').textContent = 'Voix à doubler : ' + (audioMix.removedCharacters.map(label).join(', ') || 'aucune sélectionnée')
      + ' · Ambiance : ' + (audioMix.keepAmbience ? 'conservée' : 'retirée');
    estimate();
    if (!globalThis.DOUBALGE_EXPORT_TOKEN) status('Pour encoder sur ce PC : enregistre tes corrections JSON, ouvre Lancer-studio.cmd, choisis « Oui » puis cet éditeur HTML, et importe tes corrections. Aucun nouveau calcul IA.');
    else if (!running) {
      if (exportedState && exportedState !== JSON.stringify(documentData())) {
        $('mp4-download').hidden = true;
        status('Les corrections ont changé. Crée un nouveau MP4 pour les reprendre.');
      } else status('Prêt. Les corrections seront figées au clic sur « Créer le MP4 ».');
    }
    $('mp4-start').disabled = running || !globalThis.DOUBALGE_EXPORT_TOKEN || !DATA.duoAudio;
    if (!DATA.duoAudio) status('Cette scène ne contient pas les pistes séparées. Prépare-la avec le choix des voix et de l’ambiance, en fournissant ton JSON corrigé.');
    $('mp4-dialog').showModal();
  };
  $('mp4-options').onclick = () => { $('mp4-dialog').close(); $('options-dialog').showModal(); };
  $('mp4-profile').onchange = estimate;
  $('mp4-start').onclick = async () => {
    try {
      validate(documentData());
      if (![1, 2].includes(audioMix.removedCharacters.length)) throw Error('Choisis une ou deux voix à retirer dans « Options du lecteur ».');
      $('mp4-start').disabled = true; $('mp4-download').hidden = true;
      exportName = `entrainement-${DATA.analysis_id.slice(0,8)}-${exportStamp().filename}.mp4`;
      exportedState = JSON.stringify(documentData());
      status('Préparation du son et des repères…');
      await api('/export', { edits: documentData(), profile: $('mp4-profile').value });
      running = true; poll();
    } catch (error) { status(error.message); $('mp4-start').disabled = false; }
  };
  $('mp4-cancel').onclick = async () => {
    try { await api('/cancel', {}); status('Annulation en cours…'); } catch (error) { status(error.message); }
  };
  $('mp4-download').onclick = async () => {
    $('mp4-download').disabled = true;
    try { DoubalgeDownloads.download(await api('/video'), exportName); }
    catch (error) { status(error.message); }
    finally { $('mp4-download').disabled = false; }
  };
})();
