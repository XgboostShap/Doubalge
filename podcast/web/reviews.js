/* Navigation et décisions sur une liste longue, sans reconstruire tous les formulaires. */
const reviewUi={project:null,open:false,mode:'pending',category:'',search:'',page:0,selected:null,key:'',drafts:new Map()};
const REVIEW_PAGE_SIZE=8;

function renderSourceSummary(parts){
 const holder=document.createDocumentFragment();holder.append(node('p','L’étape 2 est enregistrée. Ouvrez la synthèse d’une partie pour la lire ; les citations et le registre complet restent dans les fichiers à télécharger.'));
 for(const part of parts){const section=node('details');section.className='source-summary';section.append(node('summary',`${part.document} — partie ${part.number} · ${part.retained} idées retenues · ${part.unconfirmed} passages non confirmés`),markdown(part.summary));holder.append(section);}
 return holder;
}

function elapsedLabel(seconds){
 if(seconds===null||seconds===undefined)return '';
 const minutes=Math.floor(seconds/60),hours=Math.floor(minutes/60);
 return hours?`${hours} h ${minutes%60} min`:`${minutes} min ${Math.floor(seconds%60)} s`;
}

function renderFlow(p){
 $('project-progress').hidden=!p.pdfs.length;
 const f=p.flow;if(!f)return;
 $('project-progress').dataset.state=f.state;
 $('progress-title').textContent=f.title;
 $('progress-detail').textContent=f.state==='error'&&f.detail.length>350?f.detail.slice(0,350)+'… Voir le détail de l’erreur ci-dessous.':f.detail;
 $('progress-clock').textContent=f.elapsed_seconds!==null?'Durée de cette exécution : '+elapsedLabel(f.elapsed_seconds):'';
 $('stage-progress').value=f.completed_steps;
 $('progress-stage-count').textContent=`${f.completed_steps}/9 étapes enregistrées`;
 const counts=$('progress-counts');counts.replaceChildren();
 for(const [value,label,kind] of [[f.retained,'idées retenues','retained'],[f.pending,'à examiner','pending'],[f.deferred,'mis de côté','deferred']]){
  const item=node('span');item.className='count '+kind;item.append(node('strong',String(value)),document.createTextNode(' '+label));counts.append(item);
 }
 const source=f.source_progress;
 $('progress-source').hidden=!source&&!f.step_saved_parts;
 if(source)$('progress-source').textContent=`${source.document} · partie ${source.part}/3 · page ${source.page}${source.page_count?' sur '+source.page_count:''}`;
 else $('progress-source').textContent=`${f.step_saved_parts} points de reprise enregistrés pour cette étape`;
 $('show-reviews').hidden=!(f.pending+f.deferred);
 $('show-reviews').textContent=f.pending?`Examiner les ${f.pending} passages`:`Voir les ${f.deferred} passages mis de côté`;
 $('retained-choice').hidden=!f.can_continue_retained;
 $('continue-retained').textContent=`Continuer avec les ${f.retained} idées retenues`;
 $('continue-retained').disabled=busy(p);
 $('retained-choice-help').textContent=`Les ${f.pending} passages non confirmés seront laissés de côté et conservés dans le dossier. Ils ne seront pas utilisés dans cet épisode. La suite démarrera avec les idées déjà retenues.`;
 $('follow-progress').checked=followProgress;
 $('cancel-progress').hidden=!busy(p);
}

function renderReviews(p){
 if(reviewUi.project!==p.id){reviewUi.project=p.id;reviewUi.open=false;reviewUi.selected=null;reviewUi.page=0;reviewUi.key='';reviewUi.search='';reviewUi.category='';reviewUi.mode='pending';}
 $('review-panel').hidden=!reviewUi.open;
 if(!reviewUi.open)return;
 const all=reviewUi.mode==='deferred'?(p.deferred_reviews||[]):(p.reviews||[]);
 const search=reviewUi.search.trim().toLocaleLowerCase('fr');
 const items=all.filter(i=>(!reviewUi.category||i.label===reviewUi.category)&&(!search||
  [i.idea_id,i.source.statement,i.source.document,(i.source.pages||[]).join(' '),i.reason].join(' ').toLocaleLowerCase('fr').includes(search)));
 const labels=[...new Set(all.map(i=>i.label||'Passage à examiner'))].sort();
 const key=JSON.stringify([p.id,all.map(i=>[i.id,i.attempts]),busy(p),p.pdf_readings,reviewUi.mode,reviewUi.category,reviewUi.search,reviewUi.page,reviewUi.selected]);
 if(key===reviewUi.key)return;reviewUi.key=key;
 $('review-status').value=reviewUi.mode;$('review-search').value=reviewUi.search;
 const category=$('review-category');category.replaceChildren(node('option','Tous les motifs'));category.firstChild.value='';
 for(const text of labels){const option=node('option',text);option.value=text;category.append(option);}category.value=reviewUi.category;
 reviewUi.page=Math.max(0,Math.min(reviewUi.page,Math.ceil(items.length/REVIEW_PAGE_SIZE)-1));
 const start=reviewUi.page*REVIEW_PAGE_SIZE,visible=items.slice(start,start+REVIEW_PAGE_SIZE);
 if(!visible.some(i=>i.id===reviewUi.selected))reviewUi.selected=visible[0]?.id||null;
 $('review-range').textContent=items.length?`${start+1}–${start+visible.length} sur ${items.length} passage(s)`:'Aucun passage dans cette sélection.';
 $('review-prev').disabled=reviewUi.page===0;$('review-next').disabled=start+REVIEW_PAGE_SIZE>=items.length;
 const list=$('review-list');list.replaceChildren();
 for(const item of visible){
  const button=node('button');button.type='button';button.dataset.reviewId=item.id;button.className='review-choice'+(item.id===reviewUi.selected?' selected':'');
  button.setAttribute('aria-pressed',String(item.id===reviewUi.selected));
  button.append(node('strong',item.source.statement||'Extrait à réexaminer'),
   node('small',`${item.label||'Passage à examiner'} · ${item.source.document||''} · page ${(item.source.pages||[]).join(', ')||'à préciser'}`));
  button.onclick=()=>{reviewUi.selected=item.id;reviewUi.key='';renderReviews(current());};list.append(button);
 }
 const holder=$('review-items');holder.replaceChildren();
 const selectedItem=items.find(i=>i.id===reviewUi.selected);
 if(selectedItem)renderReviewEditor(p,selectedItem,holder);
 reviewUi.key=JSON.stringify([p.id,all.map(i=>[i.id,i.attempts]),busy(p),p.pdf_readings,reviewUi.mode,reviewUi.category,reviewUi.search,reviewUi.page,reviewUi.selected]);
}

function renderReviewEditor(p,item,holder){
 const source=item.source||{},page=source.pages?.[0]||null,card=node('div');card.className='review-item';holder.append(card);
 card.append(node('h3',source.statement||'Extrait à réexaminer'),node('small',`Étape ${item.step} · ${item.idea_id}`));
 const reason=node('details');reason.append(node('summary',item.label||'Pourquoi vérifier ce passage ?'),node('p',item.reason));card.append(reason);
 if(item.draft){const rejected=node('details');rejected.append(node('summary','Voir le brouillon refusé'),node('pre',item.draft));card.append(rejected);}
 if(page&&/^PDF[1-9]\d*$/.test(source.document||'')){
  const link=node('a',`Ouvrir le PDF source, page ${page}`);link.href=`/sources/${p.id}/${source.document}.pdf#page=${page}`;link.target='_blank';link.rel='noopener';card.append(link);
  const name=`${source.document}-p${page}.md`;
  if(p.pdf_readings?.includes(name)){const reading=node('a','Lire la relecture structurée de cette page');reading.href=`/files/${p.id}/lecture-${name}`;card.append(reading);}
  if(p.pdf_reread_available&&item.status!=='deferred'){
   const reread=node('button','Relire cette page localement');reread.disabled=busy(p);
   reread.onclick=async()=>{try{await api(`/api/projects/${p.id}/reread`,{id:item.id});await refresh();}catch(e){notice(e.message,true);}};card.append(reread);
  }
 }
 if(item.status==='deferred'){
  card.append(node('p','Ce passage est conservé pour plus tard et n’est pas utilisé dans le podcast.'),node('p',source.explanation||''));
  const button=node('button','Reprendre cette vérification');button.disabled=busy(p);
  button.onclick=async()=>{try{await api(`/api/projects/${p.id}/reopen-review`,{id:item.id});reviewUi.mode='pending';reviewUi.page=0;reviewUi.selected=item.id;reviewUi.key='';await refresh();}catch(e){notice(e.message,true);}};card.append(button);return;
 }
 let draft=reviewUi.drafts.get(item.id);
 if(!draft){const evidence=source.evidence?.length?source.evidence:source.checked_evidence||[];draft={statement:source.statement||'',explanation:source.explanation||'',note:'',evidence:evidence.map(e=>typeof e==='string'?{page,quote:e}:{page:e.page||page,quote:e.quote||''})};if(!draft.evidence.length)draft.evidence=[{page,quote:''}];reviewUi.drafts.set(item.id,draft);}
 const editable=p.completed.includes(2)&&/^PDF\d+-P\d+-I\d+$/.test(item.idea_id)&&!(p.incomplete_source_parts||[]).some(prefix=>item.idea_id.startsWith(prefix+'-'));
 function field(title,value,update){const label=node('label',title),input=node('textarea');input.value=value;input.rows=3;input.disabled=busy(p);input.oninput=()=>update(input.value);label.append(input);card.append(label);return input;}
 if(editable){
  field('Idée à conserver',draft.statement,value=>draft.statement=value);
  field('Explication et réserves',draft.explanation,value=>draft.explanation=value);
  const proofs=node('div');card.append(proofs);
  function proofFields(row){const label=node('label','Citation exacte du PDF'),number=node('input'),quote=node('textarea');number.type='number';number.min=1;number.value=row.page||'';number.placeholder='Page';number.setAttribute('aria-label','Page de la citation');number.oninput=()=>row.page=Number(number.value);quote.value=row.quote;quote.rows=4;quote.oninput=()=>row.quote=quote.value;number.disabled=quote.disabled=busy(p);label.append(number,quote);proofs.append(label);}
  draft.evidence.forEach(proofFields);
  const more=node('button','Ajouter une citation');more.type='button';more.disabled=busy(p)||draft.evidence.length>=4;more.onclick=()=>{const row={page,quote:''};draft.evidence.push(row);proofFields(row);more.disabled=draft.evidence.length>=4;};card.append(more);
  field('Motif de la décision (obligatoire pour écarter)',draft.note,value=>draft.note=value);
 }
 const actions=node('div');actions.className='row';card.append(actions);
 async function decide(action){try{notice('');await api(`/api/projects/${p.id}/review`,{id:item.id,action,...draft});reviewUi.drafts.delete(item.id);await refresh();notice(action==='retry'?'Nouvelle tentative préparée. Continuez après les choix sur les autres passages.':'Décision enregistrée.');}catch(e){notice(e.message,true);}}
 if(editable){for(const [action,label] of [['correct','Valider la correction de la source'],['exclude','Écarter cette idée avec un motif']]){const button=node('button',label);button.disabled=busy(p);button.onclick=()=>decide(action);actions.append(button);}}
 if(p.flow?.eligible_ids.includes(item.id)){
  const later=node('button','Mettre de côté pour plus tard');later.disabled=busy(p);later.onclick=async()=>{try{await api(`/api/projects/${p.id}/defer-reviews`,{ids:[item.id]});await refresh();}catch(e){notice(e.message,true);}};actions.append(later);
 }
 const retry=node('button','Réessayer avec le modèle');retry.disabled=busy(p);retry.onclick=()=>decide('retry');actions.append(retry);
}

function initReviewUI(){
 $('cancel-progress').onclick=()=>$('cancel').click();
 $('show-reviews').onclick=()=>{const p=current();reviewUi.open=!reviewUi.open;if(!p.reviews?.length&&p.deferred_reviews?.length){reviewUi.mode='deferred';reviewUi.page=0;reviewUi.key='';}renderReviews(p);if(reviewUi.open)$('review-panel').scrollIntoView({behavior:'smooth',block:'start'});};
 $('close-reviews').onclick=()=>{reviewUi.open=false;renderReviews(current());};
 $('review-status').onchange=()=>{reviewUi.mode=$('review-status').value;reviewUi.page=0;reviewUi.category='';reviewUi.selected=null;reviewUi.key='';renderReviews(current());};
 $('review-category').onchange=()=>{reviewUi.category=$('review-category').value;reviewUi.page=0;reviewUi.selected=null;reviewUi.key='';renderReviews(current());};
 $('review-search').oninput=()=>{reviewUi.search=$('review-search').value;reviewUi.page=0;reviewUi.selected=null;reviewUi.key='';renderReviews(current());};
 $('review-prev').onclick=()=>{reviewUi.page--;reviewUi.selected=null;reviewUi.key='';renderReviews(current());};
 $('review-next').onclick=()=>{reviewUi.page++;reviewUi.selected=null;reviewUi.key='';renderReviews(current());};
 $('follow-progress').onchange=()=>{followProgress=$('follow-progress').checked;render();};
 $('continue-retained').onclick=async()=>{const p=current();try{notice('');await api(`/api/projects/${p.id}/defer-reviews`,{ids:p.flow.eligible_ids,continue:true});reviewUi.open=false;followProgress=true;await refresh();notice('La suite utilise les idées retenues. Les autres passages restent disponibles dans « Mis de côté ».');}catch(e){notice(e.message,true);}};
}
