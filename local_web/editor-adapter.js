(() => {
  let revision=LOCAL_CONFIG.revision, chain=Promise.resolve(), failure=null, pending=0;
  async function send(edits){
    const response=await fetch('/api/projects/'+LOCAL_CONFIG.project+'/corrections',{method:'POST',headers:{'Content-Type':'application/json','X-Doublage-Token':LOCAL_CONFIG.csrf},body:JSON.stringify({revision,corrections:edits})});
    const result=await response.json();if(!response.ok)throw Error(result.error);revision=result.revision;
  }
  function enqueue(edits){
    pending++;
    const operation=chain.then(async()=>{
      try{if(failure)throw failure;await send(edits);message('Enregistré dans le projet sur ce PC.');}
      catch(e){failure=e;message(e.message+' Téléchargez une copie JSON avant de recharger.',true);throw e;}
      finally{pending--;}
    });
    chain=operation.catch(()=>{});
    return operation;
  }
  function changed(){return enqueue(documentData()).catch(()=>{});}
  async function flush(){await enqueue(documentData());return revision;}
  globalThis.DoubalgeDesktop={changed};
  globalThis.localBridge={flush,get pending(){return pending;}};
  const jsonButton=$('export').cloneNode(true);jsonButton.id='copy-json';jsonButton.textContent='Copie JSON';jsonButton.onclick=$('export').onclick;$('export').after(jsonButton);
  $('export').textContent='Enregistrer dans le projet';$('export').onclick=async()=>{try{await flush();message('Enregistré sur ce PC.');}catch(e){message(e.message,true);}};
  function exports(){video.pause();parent.postMessage({type:'doublage-export',project:LOCAL_CONFIG.project},location.origin);}
  $('impro').onclick=exports;$('impro').textContent='Exporter HTML';$('mp4-open').onclick=exports;
  $('spectacle').hidden=true;$('reader-preview').hidden=true;
  $('no-duo-note').textContent='Écoutez ici le son original. Les modes audio d’improvisation se règlent dans le panneau d’export de l’application.';
  // Le lecteur et les sauvegardes de ce projet sont servis uniquement par le PC.
  addEventListener('beforeunload',event=>{if(pending||failure){event.preventDefault();event.returnValue='';}});
  message('Corrections enregistrées automatiquement sur ce PC. Les propositions restent à vérifier.');
})();
