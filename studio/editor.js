
'use strict';
const DATA=JSON.parse(document.getElementById('editor-data').textContent);
const $=id=>document.getElementById(id), video=$('video'), svg=$('timeline');
const clone=x=>JSON.parse(JSON.stringify(x)), round=x=>Math.round(x*100)/100;
const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration=DATA.duration, people=DATA.characters, known=new Set(people.map(p=>p.id));
let audioMix=DoubalgeAudio.normaliseMix(DATA,people);
let waveSize=96,waveGain=2;
let lastReaderURL=null,lastExportState=null;
const person=id=>people.find(p=>p.id===id), label=id=>person(id)?.label||'Inconnu / hors champ';
const color=id=>person(id)?.color||'#758398';
const fmt=t=>{const n=Math.round(Math.max(0,t)*100);return String(Math.floor(n/6000)).padStart(2,'0')+':'+String(Math.floor(n/100)%60).padStart(2,'0')+'.'+String(n%100).padStart(2,'0');};
let intervals=clone(DATA.initial), cuts=clone(DATA.initialCuts||[]), selected=null, selectedCut=null, activeCharacter=null, undo=[], redo=[], zoom=Math.max(1,duration/180), drag=null, stopAt=null, W=1000;
const lanes=[...people.map(p=>p.id),null], LEFT=92;
let RH=26, editTop=20, cutTop=0, waveTop=0, waveH=38, H=0, timelineScale=1, timelineStart=0, timelineWidth=0;
const storageKey='doublage-editeur-plans-'+DATA.analysis_id, base=JSON.stringify({intervals:DATA.initial,cuts:DATA.initialCuts||[]});
function message(text,error=false){$('status').textContent=text;$('status').title=text;$('status').classList.toggle('error',error);}
function snapshot(){return {intervals:clone(intervals),cuts:clone(cuts),audioMix:clone(audioMix)};}
function restore(state){intervals=clone(state.intervals);cuts=clone(state.cuts);if(state.audioMix)audioMix=clone(state.audioMix);}
function documentData(){return {schema:DATA.schema,analysis_id:DATA.analysis_id,source_sha256:DATA.source_sha256,duration,characters:people.map(p=>({id:p.id,label:p.label,color:p.color})),...snapshot()};}
function editSummary(){const baseline=DATA.automatic?.length?DATA.automatic:DATA.initial,originals=new Map(baseline.map(i=>[i.id,i])),ids=new Set(intervals.map(i=>i.id));return {basis:DATA.automatic?.length?'automatic':'initial',passages:intervals.length,added:intervals.filter(i=>!originals.has(i.id)).length,modified:intervals.filter(i=>{const old=originals.get(i.id);return old&&['start','end','character','reviewed'].some(k=>i[k]!==old[k]);}).length,removed:baseline.filter(i=>!ids.has(i.id)).length};}
function summaryText(s=editSummary()){return `${s.passages} passages · ${s.added} ajoutés · ${s.modified} modifiés · ${s.removed} supprimés`;}
function exportStamp(){const date=new Date();return {exportedAt:date.toISOString(),correctionSummary:editSummary(),filename:date.toISOString().replace(/[-:]/g,'').replace(/\..*$/,'').replace('T','-')};}
function validateCuts(list){if(!Array.isArray(list)||list.length>10000)throw Error('Liste de plans invalide.');const ids=new Set();const result=list.map(c=>{if(!c||typeof c.id!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(c.id)||ids.has(c.id))throw Error('Identifiant de plan invalide ou répété.');ids.add(c.id);if(typeof c.time!=='number'||!Number.isFinite(c.time)||c.time<=0||c.time>=duration||typeof c.reviewed!=='boolean')throw Error('Chaque plan doit être à l’intérieur de la vidéo et avoir un état de validation.');return {id:c.id,time:c.time,reviewed:c.reviewed};}).sort((a,b)=>a.time-b.time||a.id.localeCompare(b.id));if(result.some((c,n)=>n&&Math.abs(c.time-result[n-1].time)<.005))throw Error('Deux changements de plan ne peuvent pas occuper le même instant.');return result;}
function validate(d){
 if(!d||d.schema!==DATA.schema||d.analysis_id!==DATA.analysis_id||d.source_sha256!==DATA.source_sha256)throw Error('Ce fichier concerne une autre vidéo ou une autre analyse.');
 if(typeof d.duration!=='number'||!Number.isFinite(d.duration)||Math.abs(d.duration-duration)>.01||!Array.isArray(d.intervals)||d.intervals.length>10000)throw Error('Durée ou liste d’intervalles invalide.');
 const ids=new Set();const clean=d.intervals.map(i=>{if(!i||typeof i.id!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(i.id)||ids.has(i.id))throw Error('Identifiant invalide ou répété.');ids.add(i.id);
 if(typeof i.start!=='number'||typeof i.end!=='number'||!Number.isFinite(i.start)||!Number.isFinite(i.end)||i.start<0||i.end>duration||i.end<=i.start)throw Error('Chaque intervalle doit avoir 0 ≤ début < fin ≤ durée.');
 if(i.character!==null&&!known.has(i.character))throw Error('Personnage inconnu.');if(typeof i.reviewed!=='boolean')throw Error('État de validation invalide.');return {id:i.id,start:i.start,end:i.end,character:i.character,reviewed:i.reviewed};});return {intervals:clean,cuts:validateCuts(Object.hasOwn(d,'cuts')?d.cuts:cuts),audioMix:validateMix(d.audioMix??audioMix)};}
function persist(){try{localStorage.setItem(storageKey,JSON.stringify({base,document:documentData()}));message('Brouillon enregistré dans ce navigateur. Enregistrez les corrections pour les conserver.');}catch(e){message('Sauvegarde locale indisponible : téléchargez les corrections avant de fermer cette page.',true);}}
try{const saved=JSON.parse(localStorage.getItem(storageKey));if(saved&&saved.base===base){restore(validate(saved.document));message('Votre brouillon local a été restauré.');}}catch(e){}
function sort(){intervals.sort((a,b)=>a.start-b.start||a.end-b.end||a.id.localeCompare(b.id));cuts.sort((a,b)=>a.time-b.time||a.id.localeCompare(b.id));}
function commit(before){sort();if(JSON.stringify(before)===JSON.stringify(snapshot()))return;validate(documentData());undo.push(before);if(undo.length>100)undo.shift();redo=[];persist();render();}
function change(action){const before=snapshot();try{action();commit(before);}catch(e){restore(before);message(e.message,true);render();}}
function current(){return intervals.find(i=>i.id===selected);}
function currentCut(){return cuts.find(c=>c.id===selectedCut);}
function seek(t){stopAt=null;video.currentTime=Math.max(0,Math.min(duration,t));if(!drag)revealTime(video.currentTime);updateCursor();}
function choose(id){video.pause();selected=id;selectedCut=null;if(current()){activeCharacter=current().character;seek(current().start);}render();}
function chooseCut(id){video.pause();selectedCut=id;selected=null;if(currentCut())seek(currentCut().time);render();}
function newId(){return 'edit-'+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));}
function play(){if(video.paused)video.play().catch(e=>message('Lecture impossible : ouvrir ce fichier HTML dans un navigateur normal.',true));else video.pause();}
function listen(){const i=current();if(!i)return;seek(i.start);stopAt=i.end;video.play().catch(e=>message(e.message,true));}
function addRange(a,b){const start=round(Math.max(0,Math.min(a,b))),end=round(Math.min(duration,Math.max(a,b)));if(end<=start){message('Choisir un intervalle non vide.',true);return;}change(()=>{const i={id:newId(),start,end,character:activeCharacter,reviewed:activeCharacter!==null};intervals.push(i);selected=i.id;selectedCut=null;});}
function split(){const i=current(), t=round(video.currentTime);if(!i)return;if(t<=i.start||t>=i.end){message('Placez le curseur à l’intérieur de l’intervalle à scinder.',true);return;}change(()=>{const right={...i,id:newId(),start:t};i.end=t;intervals.push(right);});}
function remove(){if(!current())return;change(()=>{intervals=intervals.filter(i=>i.id!==selected);selected=null;});}
function merge(){const i=current();if(!i)return;sort();const next=intervals[intervals.indexOf(i)+1];if(!next||next.character!==i.character){message('Le prochain intervalle doit appartenir au même personnage.',true);return;}change(()=>{i.end=Math.max(i.end,next.end);i.reviewed=i.reviewed&&next.reviewed;intervals=intervals.filter(x=>x.id!==next.id);});}
function assign(character){activeCharacter=character;if(current())change(()=>{current().character=character;current().reviewed=true;});else render();}
function addCut(){const t=round(video.currentTime);change(()=>{cuts.push({id:newId(),time:t,reviewed:true});selectedCut=cuts[cuts.length-1].id;selected=null;});}
function removeCut(){if(!currentCut())return;change(()=>{cuts=cuts.filter(c=>c.id!==selectedCut);selectedCut=null;});}
function timeAt(event){const r=svg.getBoundingClientRect();return Math.max(0,Math.min(duration,(event.clientX-r.left-LEFT)/(W-LEFT-12)*duration));}
function pointY(event){return event.clientY-svg.getBoundingClientRect().top;}
function xAt(t){return LEFT+t/duration*(W-LEFT-12);}
function timelineView(){const box=$('scroll'),scale=(W-LEFT-12)/duration,visible=Math.min(duration,Math.max(0,box.clientWidth-LEFT-12)/scale);return {start:box.scrollLeft/scale,visible,max:Math.max(0,duration-visible),scale};}
function syncNavigation(){
 if($('scroll').clientWidth!==timelineWidth)return;
 const view=timelineView(),position=$('timeline-position');
 timelineStart=view.start;
 position.max=view.max;position.value=Math.min(view.max,view.start);position.disabled=view.max<.01;
 const text=fmt(view.start).slice(0,5)+' – '+fmt(Math.min(duration,view.start+view.visible)).slice(0,5)+' / '+fmt(duration).slice(0,5);
 $('visible-range').textContent=text;position.setAttribute('aria-valuetext',text);
 $('timeline-back').disabled=view.start<.01;$('timeline-next').disabled=view.start>=view.max-.01;
 $('timeline-labels')?.setAttribute('transform',`translate(${$('scroll').scrollLeft},0)`);
}
function panTimeline(start,manual=true){if(manual)$('follow-playback').checked=false;const view=timelineView();$('scroll').scrollLeft=Math.max(0,Math.min(view.max,start))*view.scale;syncNavigation();}
function revealTime(t,center=false){const view=timelineView();if(center||t<view.start||t>view.start+view.visible-.1)panTimeline(t-view.visible*(center ? .5 : .15),false);}
function renderTimeline(){
 const previousStart=timelineStart;
 const available=Math.max(160,$('scroll').clientHeight-16),CUT_H=26;
 W=LEFT+Math.max(1,$('scroll').clientWidth-LEFT-12)*zoom+12;
 timelineScale=(W-LEFT-12)/duration;
 timelineWidth=$('scroll').clientWidth;
 RH=Math.max(16,Math.min(42,Math.floor((available-waveSize-90)/lanes.length)));
 editTop=20;cutTop=editTop+lanes.length*RH+8;waveTop=cutTop+CUT_H+8;
 waveH=Math.max(40,Math.min(waveSize,available-waveTop-22));H=waveTop+waveH+22;
 svg.setAttribute('width',W);svg.setAttribute('height',H);svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
 let content='<defs><pattern id="unreviewed" width="7" height="7" patternUnits="userSpaceOnUse"><path d="M-2 2L2-2M0 7L7 0M5 9L9 5" stroke="#fff" stroke-opacity=".18"/></pattern></defs>';
 content+='<text x="3" y="12" fill="#b9c9df" font-size="11">Paroles</text>';
 lanes.forEach((id,lane)=>{const y=editTop+lane*RH;content+=`<rect x="${LEFT}" y="${y}" width="${W-LEFT-12}" height="${RH-3}" fill="#111925"/><text x="4" y="${y+Math.min(15,RH-4)}" fill="${color(id)}" font-size="11">${esc(id===null?'Inconnu':label(id))}</text>`;});
 function blocks(list,kind){for(const i of list){const lane=lanes.indexOf(i.character);if(lane<0)continue;const x=xAt(i.start),width=Math.max(3,xAt(i.end)-x),y=editTop+lane*RH,sel=kind==='edit'&&i.id===selected;
 content+=`<g class="segment ${kind}" data-id="${esc(i.id)}" data-kind="${kind}"><rect x="${x}" y="${y}" width="${width}" height="${RH-5}" rx="3" fill="${color(i.character)}" fill-opacity="${kind==='auto'?.16:.88}" stroke="${sel?'#fff':color(i.character)}" stroke-dasharray="${kind==='auto'?'3 2':'none'}" stroke-width="${sel?2:1}"/>`;
 if(kind==='edit'&&!i.reviewed)content+=`<rect x="${x}" y="${y}" width="${width}" height="${RH-5}" fill="url(#unreviewed)" pointer-events="none"/>`;
 if(kind==='edit'&&width>74&&RH>20)content+=`<text x="${x+7}" y="${y+14}" fill="#fff" font-size="10">${esc(fmt(i.start))}</text>`;
 content+=`<title>${esc(label(i.character))} · ${fmt(i.start)}–${fmt(i.end)}${i.reviewed?' · validé':' · à vérifier'}</title>`;
 if(sel)content+=`<rect class="handle" data-handle="left" x="${x-3}" y="${y-2}" width="9" height="${RH-1}" fill="white"/><rect class="handle" data-handle="right" x="${x+width-5}" y="${y-2}" width="9" height="${RH-1}" fill="white"/>`;
 content+='</g>';}}
 if($('compare-auto').checked)blocks(DATA.automatic,'auto');blocks(intervals,'edit');
 content+=`<rect x="${LEFT}" y="${cutTop}" width="${W-LEFT-12}" height="${CUT_H}" fill="#111925"/><text x="3" y="${cutTop+17}" fill="#fff" font-size="11">Plans</text>`;
 if($('compare-auto').checked)for(const c of DATA.automaticCuts||[]){const x=xAt(c.time);content+=`<line x1="${x}" x2="${x}" y1="${cutTop}" y2="${cutTop+CUT_H}" stroke="#7b8a9e" stroke-dasharray="3 3" pointer-events="none"/>`;}
 for(const c of cuts){const x=xAt(c.time),y=cutTop+CUT_H/2,sel=c.id===selectedCut;content+=`<g class="segment cut" data-kind="cut" data-id="${esc(c.id)}"><rect x="${x-10}" y="${cutTop-3}" width="20" height="${CUT_H+6}" fill="transparent"/><path d="M${x} ${y-8}L${x+7} ${y}L${x} ${y+8}L${x-7} ${y}Z" fill="${c.reviewed?'#fff':'#64768e'}" stroke="${sel?'#ffe044':'#fff'}" stroke-width="${sel?3:1}"/><title>${fmt(c.time)} · ${c.reviewed?'validé':'à vérifier'}</title></g>`;}
 content+=`<text x="3" y="${waveTop+16}" fill="#b9c9df" font-size="11">Son</text><rect x="${LEFT}" y="${waveTop}" width="${W-LEFT-12}" height="${waveH}" fill="#0e1721"/>`;
 let path='';DATA.peaks.forEach((v,n)=>{const x=LEFT+n/Math.max(1,DATA.peaks.length-1)*(W-LEFT-12),a=Math.max(0,Math.min(1,v*waveGain))*(waveH/2-3);path+=`M${x.toFixed(1)} ${(waveTop+waveH/2-a).toFixed(1)}V${(waveTop+waveH/2+a).toFixed(1)}`;});content+=`<path id="waveform" d="${path}" stroke="#52d3de" stroke-width="1" pointer-events="none"/>`;
 const i=current();if(i)content+=`<rect x="${xAt(i.start)}" y="${waveTop}" width="${Math.max(1,xAt(i.end)-xAt(i.start))}" height="${waveH}" fill="${color(i.character)}" fill-opacity=".17" pointer-events="none"/>`;
 const step=[1,2,5,10,15,30,60,120,300,600].find(n=>n>=duration/(7*zoom))||600;
 for(let t=0;t<=duration;t+=step){const x=xAt(t);content+=`<line x1="${x}" x2="${x}" y1="${waveTop+waveH}" y2="${waveTop+waveH+4}" stroke="#9badc4"/><text x="${x}" y="${waveTop+waveH+17}" fill="#9badc4" font-size="10" text-anchor="middle">${fmt(t).slice(0,5)}</text>`;}
 content+=`<line id="playhead" class="cursor" x1="0" x2="0" y1="0" y2="${waveTop+waveH}" stroke="#ffe044" stroke-width="2"/><rect id="range" class="cursor" x="0" y="${editTop}" height="${lanes.length*RH}" width="0" fill="#fff" fill-opacity=".16"/>`;
 content+=`<g id="timeline-labels" pointer-events="none"><rect x="0" y="0" width="${LEFT-2}" height="${H}" fill="#1b2230"/><text x="3" y="12" fill="#b9c9df" font-size="11">Paroles</text>`;
 lanes.forEach((id,lane)=>{content+=`<text x="4" y="${editTop+lane*RH+Math.min(15,RH-4)}" fill="${color(id)}" font-size="11">${esc(id===null?'Inconnu':label(id))}</text>`;});
 content+=`<text x="3" y="${cutTop+17}" fill="#fff" font-size="11">Plans</text><text x="3" y="${waveTop+16}" fill="#b9c9df" font-size="11">Son</text></g>`;
 svg.innerHTML=content;$('scroll').scrollLeft=previousStart*timelineScale;syncNavigation();updateCursor();
}
function renderForm(){const i=current();if(!i)selected=null;$('selection-title').textContent=i?`${label(i.character)} · ${fmt(i.start)} → ${fmt(i.end)}`:'Sélectionnez un intervalle à corriger';for(const name of ['character','start','end','reviewed','listen','split','merge','delete'])$(name).disabled=!i;
 $('start').value=i?i.start:'';$('end').value=i?i.end:'';$('character').value=i?(i.character??'unknown'):'unknown';$('reviewed').checked=!!i?.reviewed;$('undo').disabled=!undo.length;$('redo').disabled=!redo.length;
 for(const button of $('people').querySelectorAll('button'))button.classList.toggle('chosen',(button.dataset.character||null)===activeCharacter);
}
function renderRows(){const rows=$('rows');rows.replaceChildren();for(const [n,i] of intervals.entries()){const tr=document.createElement('tr');tr.classList.toggle('selected',i.id===selected);
 const td=document.createElement('td'),button=document.createElement('button');button.textContent=n+1;button.setAttribute('aria-label','Sélectionner intervalle '+(n+1));button.onclick=()=>{choose(i.id);if($('list-dialog').open)$('list-dialog').close();};td.append(button);tr.append(td);
 for(const text of [label(i.character),fmt(i.start),fmt(i.end),i.reviewed?'Validé':'À vérifier']){const cell=document.createElement('td');cell.textContent=text;tr.append(cell);}rows.append(tr);}
 $('count').textContent=intervals.length+' intervalles · '+intervals.filter(i=>!i.reviewed).length+' à vérifier';}
function renderCuts(){const select=$('cut-select');select.replaceChildren(new Option('Sélectionner un plan',''));for(const [n,c] of cuts.entries())select.add(new Option(`Plan ${n+1} · ${fmt(c.time)}${c.reviewed?' ✓':' ?'}`,c.id));if(!currentCut())selectedCut=null;select.value=selectedCut||'';const c=currentCut();for(const name of ['cut-time','cut-reviewed','cut-before','cut-after','cut-delete','cut-cursor','cut-nudge-back','cut-nudge-next'])$(name).disabled=!c;$('cut-time').value=c?c.time:'';$('cut-reviewed').checked=!!c?.reviewed;$('cut-count').textContent=cuts.length+' changement(s) de plan · '+cuts.filter(c=>!c.reviewed).length+' à vérifier';}
function render(){sort();renderForm();renderCuts();renderTimeline();renderRows();renderMix();$('edit-summary').textContent=summaryText();$('reader-preview').hidden=!lastReaderURL||lastExportState!==JSON.stringify(snapshot());}
function updateCursor(){const t=video.currentTime||0,x=xAt(t),cursor=$('playhead');if(cursor){cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);}$('clock').textContent=fmt(t)+' / '+fmt(duration);
 if(document.activeElement!==$('seek'))$('seek').value=round(t);
 for(const button of $('people').querySelectorAll('button')){const character=button.dataset.character||null,active=intervals.some(i=>i.character===character&&i.start<=t&&t<i.end),soon=!active&&intervals.some(i=>i.character===character&&i.start-1.5<=t&&t<i.start);button.classList.toggle('speaking',active);button.classList.toggle('upcoming',soon);const status=button.querySelector('small');status.textContent=active?'Parole en cours':soon?'Bientôt':'Cliquer pour affecter';}
 if(stopAt!==null&&t>=stopAt){video.pause();stopAt=null;}
 if(!video.paused&&zoom>1&&!drag&&$('follow-playback').checked)revealTime(t);
}
svg.addEventListener('pointerdown',event=>{if(event.button!==0||event.clientX<$('scroll').getBoundingClientRect().left+LEFT)return;const target=event.target.closest('[data-id]'),time=timeAt(event);if(target){const id=target.dataset.id;if(target.dataset.kind==='cut-auto'){seek((DATA.automaticCuts||[]).find(c=>c.id===id).time);return;}if(target.dataset.kind==='cut'){video.pause();selectedCut=id;selected=null;const c=currentCut();drag={mode:'cut',id,time,start:c.time,before:snapshot(),moved:false};seek(c.time);svg.setPointerCapture(event.pointerId);render();return;}if(target.dataset.kind==='auto'){seek(time);selectedCut=null;selected=intervals.find(i=>i.start<=time&&time<i.end)?.id||null;render();return;}video.pause();selected=id;selectedCut=null;const i=current();activeCharacter=i.character;const before=snapshot();drag={mode:event.target.dataset.handle||'move',id,time,start:i.start,end:i.end,character:i.character,before,moved:false};seek(i.start);svg.setPointerCapture(event.pointerId);render();}
 else if(event.shiftKey){drag={mode:'range',time,endTime:time,moved:false};svg.setPointerCapture(event.pointerId);seek(time);}
 else{seek(time);}});
svg.addEventListener('pointermove',event=>{if(!drag)return;const t=timeAt(event),delta=t-drag.time;if(Math.abs(delta)<.01&&!drag.moved)return;drag.moved=true;
 if(drag.mode==='range'){drag.endTime=t;const range=$('range');range.setAttribute('x',xAt(Math.min(t,drag.time)));range.setAttribute('width',Math.abs(xAt(t)-xAt(drag.time)));return;}
 if(drag.mode==='cut'){const c=currentCut();if(!c)return;c.time=round(Math.max(.01,Math.min(duration-.01,drag.start+delta)));c.reviewed=true;seek(c.time);renderTimeline();renderCuts();return;}
 const i=current();if(!i)return;if(drag.mode==='left')i.start=round(Math.max(0,Math.min(drag.end-.01,t)));else if(drag.mode==='right')i.end=round(Math.min(duration,Math.max(drag.start+.01,t)));else{const length=drag.end-drag.start;const start=Math.max(0,Math.min(duration-length,drag.start+delta));i.start=round(start);i.end=Math.min(duration,round(start+length));const lane=Math.floor((pointY(event)-editTop)/RH);if(lane>=0&&lane<lanes.length){i.character=lanes[lane];if(i.character!==drag.character)i.reviewed=true;activeCharacter=i.character;}}
 renderTimeline();renderForm();});
svg.addEventListener('pointerup',event=>{if(!drag)return;const ending=drag;drag=null;if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);if(ending.mode==='range'){if(ending.moved)addRange(ending.time,ending.endTime);else render();}else{try{commit(ending.before);}catch(e){restore(ending.before);message(e.message,true);}render();}});
svg.addEventListener('pointercancel',()=>{if(drag?.before)restore(drag.before);drag=null;render();});
svg.addEventListener('dblclick',()=>listen());
for(const p of [...people,{id:null,label:'Inconnu / hors champ',color:'#758398'}]){const b=document.createElement('button');b.className='person';b.dataset.character=p.id||'';b.style.setProperty('--person',p.color);if(p.photo){const img=document.createElement('img');img.src='data:image/jpeg;base64,'+p.photo;img.alt=p.label;b.append(img);}const text=document.createElement('span'),name=document.createElement('span'),small=document.createElement('small');name.className='name';name.textContent=p.label;small.textContent='Cliquer pour affecter';text.append(name,small);b.append(text);b.onclick=()=>assign(p.id);$('people').append(b);const option=document.createElement('option');option.value=p.id??'unknown';option.textContent=p.label;$('character').append(option);}
$('character').onchange=()=>assign($('character').value==='unknown'?null:$('character').value);
for(const bound of ['start','end'])$(bound).onchange=()=>{const i=current();if(!i)return;const value=$(bound).value.trim()===''?NaN:round(Number($(bound).value));if(!Number.isFinite(value)||value<0||value>duration||(bound==='start'?value>=i.end:value<=i.start)){message('Bornes invalides : le début doit précéder la fin et rester dans la vidéo.',true);return;}change(()=>{i[bound]=value;});};
$('reviewed').onchange=()=>change(()=>{current().reviewed=$('reviewed').checked;});
$('play').onclick=play;$('listen').onclick=listen;$('split').onclick=split;$('merge').onclick=merge;$('delete').onclick=remove;
$('add').onclick=()=>{const start=Math.min(Math.max(0,video.currentTime),duration-.01);addRange(start,Math.min(duration,start+1));};
$('go').onclick=()=>{const t=Number($('seek').value);if(Number.isFinite(t))seek(t);};$('seek').max=duration;$('seek').onkeydown=e=>{if(e.key==='Enter')$('go').click();};
$('zoom').onchange=()=>{const value=$('zoom').value;zoom=value.endsWith('s')?Math.max(1,duration/Number(value.slice(0,-1))):Number(value);renderTimeline();revealTime(video.currentTime||0,true);};
$('scroll').addEventListener('scroll',syncNavigation);
$('scroll').addEventListener('pointerdown',event=>{if(event.target===$('scroll'))$('follow-playback').checked=false;});
$('scroll').addEventListener('wheel',event=>{if(!event.ctrlKey&&!event.metaKey&&(event.deltaX||event.shiftKey)){event.preventDefault();$('follow-playback').checked=false;$('scroll').scrollLeft+=event.deltaX||event.deltaY;syncNavigation();}},{passive:false});
$('timeline-position').oninput=()=>panTimeline(Number($('timeline-position').value));
$('timeline-back').onclick=()=>{const view=timelineView();panTimeline(view.start-view.visible/2);};
$('timeline-next').onclick=()=>{const view=timelineView();panTimeline(view.start+view.visible/2);};
$('timeline-cursor').onclick=()=>revealTime(video.currentTime||0,true);
$('follow-playback').onchange=()=>{if($('follow-playback').checked)revealTime(video.currentTime||0);};
$('cut-select').onchange=()=>chooseCut($('cut-select').value||null);
$('cut-time').onchange=()=>{if(!currentCut())return;const value=$('cut-time').value.trim()===''?NaN:round(Number($('cut-time').value));change(()=>{currentCut().time=value;currentCut().reviewed=true;});seek(currentCut().time);};
$('cut-reviewed').onchange=()=>change(()=>{if(currentCut())currentCut().reviewed=$('cut-reviewed').checked;});
$('cut-add').onclick=addCut;$('cut-delete').onclick=removeCut;
$('cut-before').onclick=()=>{if(currentCut())seek(currentCut().time-.12);};$('cut-after').onclick=()=>{if(currentCut())seek(currentCut().time+.12);};
$('undo').onclick=()=>{if(!undo.length)return;redo.push(snapshot());restore(undo.pop());persist();render();};
$('redo').onclick=()=>{if(!redo.length)return;undo.push(snapshot());restore(redo.pop());persist();render();};
$('reset').onclick=()=>change(()=>{intervals=clone(DATA.initial);cuts=clone(DATA.initialCuts||[]);selected=null;selectedCut=null;});
$('export').onclick=()=>{try{const edits=validate(documentData()),stamp=exportStamp(),filename='timeline-corrigee-'+DATA.analysis_id+'-'+stamp.filename+'.json';DoubalgeDownloads.download(new Blob([JSON.stringify({...documentData(),exportedAt:stamp.exportedAt,correctionSummary:stamp.correctionSummary},null,2)],{type:'application/json'}),filename);message('Téléchargement demandé : '+filename+' · '+summaryText()+'. Vérifie avec Ctrl + J.');}catch(e){message(e.message,true);}};
$('import').onclick=()=>$('import-file').click();$('import-file').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{const loaded=validate(JSON.parse(await file.text()));change(()=>{restore(loaded);selected=null;selectedCut=null;});message('Corrections importées. Les pistes automatiques sont inchangées.');}catch(e){message(e.message,true);}event.target.value='';};
for(const p of people){if(!p.reference)continue;$('voice-references').hidden=false;const b=document.createElement('button');b.textContent='▶ '+p.label;b.title=p.reference.text||'';b.onclick=()=>{const ref=referenceFor(p,intervals);if(!ref){message('Aucun passage attribué à '+p.label,true);return;}seek(ref.start);stopAt=ref.end;video.play().catch(e=>message(e.message,true));message(p.label+' · Extrait repère · '+fmt(ref.start));};$('voice-references').append(b);}
function validateMix(value){if(!value||!Array.isArray(value.removedCharacters)||value.removedCharacters.some(id=>!known.has(id))||typeof value.keepAmbience!=='boolean'||typeof value.keepUnknown!=='boolean')throw Error('Choix des voix ou de l’ambiance invalide.');return {removedCharacters:[...new Set(value.removedCharacters)],keepAmbience:value.keepAmbience,keepUnknown:value.keepUnknown};}
function renderMix(){for(const input of $('remove-voices').querySelectorAll('input'))input.checked=audioMix.removedCharacters.includes(input.dataset.character);$('keep-ambience').checked=audioMix.keepAmbience;$('keep-unknown').checked=audioMix.keepUnknown;}
if(DATA.duoAudio){$('duo-options').hidden=false;for(const p of people){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.dataset.character=p.id;label.style.setProperty('--voice',p.color);label.append(input,document.createTextNode('Retirer '+p.label));$('remove-voices').append(label);input.onchange=()=>change(()=>{audioMix.removedCharacters=[...$('remove-voices').querySelectorAll('input:checked')].map(i=>i.dataset.character);});}}
$('keep-ambience').onchange=()=>change(()=>{audioMix.keepAmbience=$('keep-ambience').checked;});
$('keep-unknown').onchange=()=>change(()=>{audioMix.keepUnknown=$('keep-unknown').checked;});
$('mix-keep-all').onclick=()=>change(()=>{audioMix={removedCharacters:[],keepAmbience:true,keepUnknown:true};});
$('mix-remove-all').onclick=()=>change(()=>{audioMix.removedCharacters=people.map(p=>p.id);audioMix.keepUnknown=false;});
$('reader-preview').onclick=()=>video.pause();
$('impro').onclick=()=>{try{const edits=validate(documentData()),stamp=exportStamp(),data={duration,characters:exportPeople(edits.intervals),intervals:edits.intervals,cuts:edits.cuts,media:DATA.duoAudio?DATA.improMedia:DATA.media,audioMix:clone(audioMix),exportedAt:stamp.exportedAt,correctionSummary:stamp.correctionSummary};if(DATA.duoAudio)data.duoAudio=DATA.duoAudio;data.title=DATA.title||'Scène';data.analysis_id=DATA.analysis_id;data.source_sha256=DATA.source_sha256;data.showTemplate=DATA.showTemplate;const filename='version-impro-'+DATA.analysis_id.slice(0,8)+'-'+stamp.filename+'.html';const blob=DoubalgeDownloads.htmlBlob(DATA.improTemplate,'__IMPRO_DATA__',data);DoubalgeDownloads.download(blob,filename);if(lastReaderURL)URL.revokeObjectURL(lastReaderURL);lastReaderURL=URL.createObjectURL(blob);lastExportState=JSON.stringify(snapshot());$('reader-preview').href=lastReaderURL;$('reader-preview').hidden=false;message('Téléchargement demandé : '+filename+' · '+summaryText()+'. Ouvre ce fichier avec Ctrl + J.');}catch(e){message(e.message+' Enregistre le JSON corrigé pour conserver ton travail.',true);}};
document.addEventListener('keydown',e=>{if(e.target.matches('input,select,textarea'))return;if(e.code==='Space'){e.preventDefault();play();}else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();$(e.shiftKey?'redo':'undo').click();}else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();$('redo').click();}else if(e.key==='Delete'){if(currentCut())removeCut();else remove();}else if(e.key.toLowerCase()==='s')split();});
video.src=DATA.media;video.addEventListener('error',()=>message('Lecture impossible dans cet aperçu. Téléchargez le HTML complet puis ouvrez-le dans Chrome, Firefox ou Edge.',true));
video.addEventListener('timeupdate',updateCursor);video.addEventListener('seeked',updateCursor);video.addEventListener('ended',()=>{stopAt=null;updateCursor();});
new ResizeObserver(()=>{if(!drag)renderTimeline();}).observe($('scroll'));
function animate(){updateCursor();requestAnimationFrame(animate);}sort();render();requestAnimationFrame(animate);

const frame=1/(Number(DATA.fps)>0?Number(DATA.fps):25);
function nextFrame(delta){video.pause();seek((video.currentTime||0)+delta*frame);}
function nudgeCut(delta){const c=currentCut();if(!c)return;video.pause();change(()=>{c.time=round(Math.min(duration-.01,Math.max(.01,c.time+delta*frame)));c.reviewed=true;});seek(c.time);}
$('frame-back').onclick=()=>nextFrame(-1);$('frame-next').onclick=()=>nextFrame(1);
$('cut-nudge-back').onclick=()=>nudgeCut(-1);$('cut-nudge-next').onclick=()=>nudgeCut(1);
$('cut-cursor').onclick=()=>{const c=currentCut();if(!c)return;video.pause();change(()=>{c.time=round(Math.min(duration-.01,Math.max(.01,video.currentTime||0)));c.reviewed=true;});};
$('compare-auto').onchange=renderTimeline;
for(const [button,dialog] of [['help-open','help-dialog'],['list-open','list-dialog'],['options-open','options-dialog'],['wave-options','wave-dialog']])$(button).onclick=()=>$(dialog).showModal();
for(const id of ['wave-size','wave-gain'])$(id).oninput=()=>{waveSize=Number($('wave-size').value);waveGain=Number($('wave-gain').value);$('wave-gain-value').textContent='×'+waveGain;renderTimeline();};
for(const b of document.querySelectorAll('[data-close]'))b.onclick=()=>b.closest('dialog').close();
$('no-duo-note').hidden=!!DATA.duoAudio;
video.addEventListener('play',()=>{$('play').textContent='Pause';});video.addEventListener('pause',()=>{$('play').textContent='Lire / Pause';});
document.addEventListener('keydown',e=>{if(e.target.matches('input,select,textarea')||document.querySelector('dialog[open]'))return;if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();if(e.altKey&&currentCut())nudgeCut(e.key==='ArrowLeft'?-1:1);else nextFrame(e.key==='ArrowLeft'?-1:1);}else if(e.key.toLowerCase()==='p'){e.preventDefault();addCut();}});

function referenceFor(person,list){const candidates=list.filter(i=>i.character===person.id).slice().sort((a,b)=>Number(b.reviewed)-Number(a.reviewed)||(b.end-b.start)-(a.end-a.start));const i=candidates[0];return i?{character:person.id,start:i.start,end:Math.min(i.end,i.start+5),text:'Extrait repère'}:null;}
function exportPeople(list){return people.map(p=>({...p,reference:referenceFor(p,list)}));}

$('spectacle').onclick=()=>{try{const edits=validate(documentData()),data={title:DATA.title||'Scène',analysis_id:DATA.analysis_id,source_sha256:DATA.source_sha256,duration,characters:exportPeople(edits.intervals),intervals:edits.intervals,cuts:edits.cuts,media:DATA.duoAudio?DATA.improMedia:DATA.media,audioMix:clone(audioMix)};if(DATA.duoAudio)data.duoAudio=DATA.duoAudio;const program={schema:'doublagebasic.show.v1',autoAdvance:false,scenes:[{title:data.title,data,performers:{}}]};DoubalgeDownloads.download(DoubalgeDownloads.htmlBlob(DATA.showTemplate,'__SHOW_DATA__',program),'spectacle.html');message('Téléchargement du spectacle demandé avec '+summaryText()+'. Vérifie avec Ctrl + J.');}catch(e){message(e.message,true);}};
