"""Avancement lisible et poursuite explicite avec les seules idées retenues."""
import time


def eligible_reviews(source_data, items):
    parts=[p for d in source_data.get('documents',[]) for p in d['parts']]
    if any(p.get('incomplete_extraction') for p in parts):return []
    retained={i['id'] for p in parts for i in p['ideas']}
    excluded={i['id'] for p in parts for i in p.get('excluded_ideas',[])}
    return [i for i in items if i['step']==2 and i['idea_id'] in excluded-retained
            and not i['source'].get('unextracted')]


def reason_label(item):
    reason=item.get('reason','').lower()
    if 'développement non confirmé' in reason:return 'Sigle à vérifier'
    if 'bibliograph' in reason:return 'Référence bibliographique'
    if 'plan du document' in reason or 'liste de publications' in reason:return 'Contenu secondaire'
    if 'français' in reason or 'francais' in reason or 'bruit, pompage' in reason:return 'Formulation'
    return {'formula':'Formule','scope':'Portée du résultat','length':'Longueur',
        'format':'Format de réponse','generation':'Génération','terminology':'Terminologie',
        'source':'Appui source'}.get(item.get('category'),'Passage à examiner')


def overview(source_data, completed, task, pending, deferred, parts_count=0, retry_steps=()):
    retained=sum(len(p['ideas']) for d in source_data.get('documents',[]) for p in d['parts'])
    eligible=eligible_reviews(source_data,pending)
    running=task and task.get('state') in ('running','queued')
    next_step=min([next((n for n in range(1,10) if n not in completed),10)]+list(retry_steps))
    current=(task.get('step') or task.get('first') or min(next_step,9)) if running else min(
        (i['step'] for i in pending),default=min(next_step,9))
    if running:
        status='running'
        title=('Préparation audio en cours' if task.get('kind')=='audio' else
               'Relecture de la page en cours' if task.get('kind')=='pdf_reading' else
               f'Étape {current}/9 — calcul en cours') if task['state']=='running' else 'Traitement en attente de démarrage'
        detail=task.get('message','')
    elif pending:
        status='needs_review';title='Un choix est attendu — le calcul est arrêté'
        detail=(f'L’étape 2 est enregistrée. {len(pending)} passage(s) attendent une décision avant l’étape 3.'
                if 2 in completed and all(i['step']==2 for i in pending) else
                f'{len(pending)} passage(s) attendent une décision. Les autres parties réussies sont conservées.')
    elif task and task.get('state')=='error':
        status='error';title='Traitement arrêté sur une erreur';detail=task.get('error') or task.get('message','')
    elif source_data.get('documents') and not retained:
        status='needs_source';title='Aucune idée retenue à l’étape 2'
        detail='Réexaminez cette étape avant la synthèse. Le PDF et son extraction sont conservés.'
    elif next_step==10:
        status='done';title='Le script est terminé';detail='Le dialogue peut être relu, puis préparé avec vos voix.'
    else:
        status='ready';title=f'Prêt pour l’étape {next_step}';detail='Cliquez sur Continuer pour reprendre les parties manquantes.'
    started=(task or {}).get('started_at')
    end=time.time() if running else (task or {}).get('finished_at')
    elapsed=max(0,end-started) if isinstance(started,(int,float)) and isinstance(end,(int,float)) else None
    return {'state':status,'title':title,'detail':detail,'current_step':current,'completed_steps':len(completed),
        'retained':retained,'pending':len(pending),'deferred':len(deferred),'eligible_ids':[i['id'] for i in eligible],
        'can_continue_retained':bool(pending) and len(eligible)==len(pending) and retained>0 and not running,
        'saved_parts':parts_count,'elapsed_seconds':round(elapsed) if elapsed is not None else None,
        'last_saved_at':(task or {}).get('last_saved_at'),'source_progress':(task or {}).get('source_progress') if current==2 else None}
