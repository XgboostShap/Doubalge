'use strict';
const el=id=>document.getElementById(id);
let csrf='',current=null,state=null,editorRevision=null,refreshing=false,editorLoad=Promise.resolve();
function notice(error){el('notice').textContent=error.message||String(error);el('notice').hidden=false;}
el('notice').onclick=()=>el('notice').hidden=true;
async function api(path,body){const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Doublage-Token':csrf},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw Error(value.error||'Erreur de requête');return value;}
async function flush(){await editorLoad;const bridge=el('editor').contentWindow?.localBridge;if(!el('editor').hidden&&bridge)await bridge.flush();}
async function refresh(){if(refreshing)return;refreshing=true;try{
 state=await api('/api/state');csrf=state.csrf;
 el('token-state').textContent=state.token_set?'Jeton chargé en mémoire pour cette session.':'Aucun jeton en mémoire.';
 el('projects').replaceChildren();
 if(!state.projects.length)el('projects').textContent='Vos scènes apparaîtront ici. Les projets restent enregistrés après fermeture.';
 for(const p of state.projects){const box=document.createElement('article');box.className='project';const title=document.createElement('b');title.textContent=p.name;const text=document.createElement('p');text.textContent=p.task.message||'À préparer';const button=document.createElement('button');button.textContent=p.ready?'Ouvrir la scène':'Voir le traitement';button.onclick=()=>openProject(p.id).catch(notice);box.append(title,text,button);el('projects').append(box);}
 if(current){const p=state.projects.find(p=>p.id===current);if(p)renderProject(p);}
 }catch(e){notice(e);}finally{refreshing=false;}}
function renderProject(p){
 el('project-title').textContent=p.name;el('task-status').textContent=p.task.message||'Prêt';
 const busy=['queued','running'].includes(p.task.status);
 el('cancel').disabled=!busy;el('resume').hidden=p.ready||busy;el('resume').disabled=!p.has_source&&!p.url;
 el('export-start').disabled=busy;el('separate').disabled=busy;el('save-voice').disabled=busy;
 el('export-area').hidden=!p.ready;
 el('waiting').hidden=p.ready;el('editor').hidden=!p.ready;
 if(p.ready&&editorRevision===null){editorLoad=new Promise(resolve=>{el('editor').onload=()=>resolve();});el('editor').src='/files/'+p.id+'/editeur.html';editorRevision=p.revision;fillVoices(p);}
 el('downloads').replaceChildren();for(const name of p.exports){const a=document.createElement('a');a.href='/files/'+p.id+'/'+name;a.textContent='Télécharger '+name;a.download=name;el('downloads').append(a);}
}
function fillVoices(p){const prev=el('voice').value;el('voice').replaceChildren();el('voice-edit').replaceChildren(new Option('Ajouter une voix',''));for(const [id,name] of Object.entries(p.voices)){el('voice').add(new Option(name,id));el('voice-edit').add(new Option(name,id));}if(p.voices[prev])el('voice').value=prev;}
async function openProject(id){await flush();current=id;editorRevision=null;el('editor').src='about:blank';el('dashboard').hidden=true;el('workspace').hidden=false;await refresh();}
el('home').onclick=async()=>{try{await flush();el('editor').contentWindow?.document.querySelector('video')?.pause();current=null;el('workspace').hidden=true;el('dashboard').hidden=false;await refresh();}catch(e){notice(e);}};
el('settings').onclick=()=>el('token-dialog').showModal();el('token-close').onclick=()=>el('token-dialog').close();
el('token-form').onsubmit=async event=>{event.preventDefault();try{await api('/api/token',{token:el('hf-token').value.trim()});el('hf-token').value='';el('token-dialog').close();await refresh();}catch(e){notice(e);}};
el('new-project').onsubmit=async event=>{event.preventDefault();el('prepare').disabled=true;try{
 const video=el('video-file').files[0],url=el('url').value.trim();if(Boolean(video)===Boolean(url))throw Error('Choisissez une vidéo locale ou une URL YouTube.');
 const options={};const correction=el('correction-file').files[0];if(correction){if(correction.size>8*1024*1024)throw Error('JSON trop volumineux');options.corrections=JSON.parse(await correction.text());}
 if(el('speakers').value)options.speakers=Number(el('speakers').value);
 const p=await api('/api/projects',{name:el('name').value,url});
 if(video){el('creation-status').textContent='Copie de la vidéo dans le projet…';const response=await fetch('/api/projects/'+p.id+'/source',{method:'POST',headers:{'X-Doublage-Token':csrf,'Content-Type':'application/octet-stream'},body:video});if(!response.ok)throw Error((await response.json()).error);}
 await api('/api/projects/'+p.id+'/analyze',options);el('creation-status').textContent='';await openProject(p.id);
 }catch(e){notice(e);}finally{el('prepare').disabled=false;}};
async function command(action,body={}){await api('/api/projects/'+current+'/'+action,body);await refresh();}
el('cancel').onclick=()=>command('cancel').catch(notice);el('resume').onclick=()=>command('resume').catch(notice);
el('separate').onclick=async()=>{try{await flush();await command('separate');}catch(e){notice(e);}};
el('export-start').onclick=async()=>{el('export-start').disabled=true;try{await flush();await command('export',{mode:el('audio-mode').value,voice:el('voice').value,quality:el('quality').value,format:el('format').value});}catch(e){notice(e);el('export-start').disabled=false;}};
el('save-voice').onclick=async()=>{try{await flush();const detail=await api('/api/projects/'+current);await command('voices',{revision:detail.project.revision,voice:el('voice-edit').value||null,label:el('voice-name').value});editorRevision=null;el('voice-name').value='';await refresh();}catch(e){notice(e);}};
el('voice-edit').onchange=()=>{const p=state.projects.find(p=>p.id===current);el('voice-name').value=p.voices[el('voice-edit').value]||'';};
el('log-open').onclick=async()=>{try{const response=await fetch('/files/'+current+'/journal.txt');el('logs').textContent=response.ok?await response.text():'Le journal apparaîtra au début du traitement.';el('log-dialog').showModal();}catch(e){notice(e);}};el('log-close').onclick=()=>el('log-dialog').close();
addEventListener('message',event=>{if(event.origin===location.origin&&event.source===el('editor').contentWindow&&event.data?.type==='doublage-export'){el('export-area').scrollIntoView({behavior:'smooth'});}});
refresh();setInterval(refresh,2000);
