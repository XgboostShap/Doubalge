/* Adaptateur de la fenêtre de bureau : fichiers et commandes Python sans HTTP. */
(() => {
  'use strict';
  if (!globalThis.DOUBALGE_DESKTOP) return;
  const session = DOUBALGE_DESKTOP.session;
  let queue = Promise.resolve(), pending = 0, saveError = null;
  const ready = new Promise(resolve => {
    if (globalThis.pywebview?.api) resolve();
    else window.addEventListener('pywebviewready', resolve, {once:true});
  });
  async function call(method,...args) { await ready; return pywebview.api[method](...args); }
  function report(error) { message('Enregistrement impossible : '+error.message+'. Garde la fenêtre ouverte et réessaie.',true); }
  function changed() {
    const edits = documentData(); pending++;
    queue = queue.then(async()=>{
      try { await call('save_project',session,edits); saveError=null; message('Projet enregistré sur le PC.'); }
      catch(error) { saveError=error; report(error); }
      finally { pending--; }
    });
    return queue;
  }
  async function flush() {
    await queue;
    await call('save_project',session,documentData());
    saveError=null;
  }
  globalThis.DoubalgeDesktop = {
    changed, get pending(){return pending;},
    closeReady:false, closeFailed:false,
    async close() {
      this.closeReady=false; this.closeFailed=false;
      try { video.pause(); await flush(); await call('close_saved',session,documentData()); this.closeReady=true; }
      catch(error) { this.closeFailed=true; report(error); }
    },
    async mp4(path,body) {
      if(path==='/export') { await flush(); return call('start_export',session,body); }
      if(path==='/status') return call('job_status');
      if(path==='/cancel') return call('cancel_job');
      throw Error('Commande MP4 inconnue.');
    },
  };
  ready.then(()=>{
    $('export').textContent='Enregistrer le projet';
    $('export').onclick=async()=>{try{await flush();message('Projet enregistré : '+DOUBALGE_DESKTOP.project);}catch(error){report(error);}};
    $('import').onclick=async()=>{try{
      await flush(); const edits=await call('import_corrections',session); if(!edits)return;
      const loaded=validate(edits);
      for(const p of people){const name=edits.characters?.find(x=>x.id===p.id);if(name){p.label=name.label;p.color=name.color;}}
      change(()=>{restore(loaded);selected=null;selectedCut=null;});
      for(const p of people){
        const button=[...$('people').querySelectorAll('.person')].find(b=>b.dataset.character===p.id);
        if(button){button.querySelector('.name').textContent=p.label;button.style.setProperty('--person',p.color);}
        const option=[...$('character').options].find(o=>o.value===p.id);if(option)option.textContent=p.label;
        const input=[...$('remove-voices').querySelectorAll('input')].find(i=>i.dataset.character===p.id);
        if(input){input.parentElement.lastChild.textContent='Retirer '+p.label;input.parentElement.style.setProperty('--voice',p.color);}
      }
      await flush();
      message('Corrections importées et enregistrées dans le projet.');
    }catch(error){message(error.message,true);}};
    for(const [button,kind] of [['impro','player'],['spectacle','show']]){
      $(button).onclick=async()=>{try{
        await flush();const path=await call('export_html',session,documentData(),kind);
        if(path)message('Export enregistré : '+path);
      }catch(error){message(error.message,true);}};
    }
    $('spectacle').textContent='Exporter pour le spectacle';
    const home=document.createElement('button');home.id='desktop-home';home.textContent='Projets';
    home.onclick=async()=>{try{video.pause();await flush();await call('home',session,documentData());}catch(error){message(error.message,true);}};
    $('undo').before(home);
    const json=document.createElement('button');json.id='desktop-json';json.textContent='Copie JSON';
    json.onclick=async()=>{try{await flush();const path=await call('export_json',session,documentData());if(path)message('Copie enregistrée : '+path);}catch(error){message(error.message,true);}};
    $('import').after(json);
    $('reader-preview').hidden=true;
    $('mp4-download').hidden=true;
    $('mp4-cancel').closest('dialog').querySelector('p:last-child').textContent='La vidéo sera enregistrée à l’emplacement choisi sur ce PC. Aucun envoi de message n’est effectué.';
    message('Projet ouvert : '+DOUBALGE_DESKTOP.project+' · Les modifications seront enregistrées sur le PC.');
  }).catch(report);
})();
