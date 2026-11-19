"""Décisions humaines : valider la preuve, corriger le registre et préserver les unités."""
import json
import re
import time
import uuid

import editorial
import quality
import source_review
from review_queue import Reviews, apply_corrections
from storage import fingerprint, invalidate, read, write, write_text


def resolve(folder,body,preserve_summaries,render_part):
    reviews=Reviews(folder)
    item=next((i for i in reviews.pending() if i['id']==body.get('id')),None)
    if item is None:raise ValueError('Vérification absente ou déjà traitée.')
    action=body.get('action');note=body.get('note','')
    if not isinstance(note,str) or len(note)>4000:raise ValueError('Motif de décision invalide.')
    if action=='retry':
        if item['step']==2:
            if (folder/'etapes/02.json').exists():preserve_summaries(folder)
            part_key=re.match(r'(PDF\d+-P\d+)',item['idea_id'])
            archive=folder/'versions'/('verification-'+uuid.uuid4().hex[:12])
            from storage import replace
            for path in (folder/'etapes/parties').glob('02-*.json'):
                saved=read(path)
                if (part_key and path.stem=='02-'+part_key[0]) or item['idea_id'] in json.dumps(saved.get('data',{}),ensure_ascii=False):
                    archive.mkdir(parents=True,exist_ok=True)
                    for file in (path,path.with_suffix('.md')):
                        if file.exists():replace(file,archive/file.name)
        decision=reviews.decide(item['id'],action,note)
        return decision
    if action not in ('correct','exclude'):raise ValueError('Décision inconnue.')
    path=folder/'etapes/02.json'
    if not path.exists():raise ValueError('Terminez le rapport des sources avant de corriger une idée.')
    saved=read(path);data=saved['data'];source=read(folder/'etapes/01.json')['data']
    original=next((i for d in data['documents'] for p in d['parts']
        for i in p.get('ideas',[])+p.get('excluded_ideas',[]) if i['id']==item['idea_id']),None)
    if original is None:raise ValueError('Cette idée ne figure plus dans le registre. Réessayez le passage avec le modèle.')
    doc=next(d for d in data['documents'] if any(original['id']==i['id'] for p in d['parts'] for i in p.get('ideas',[])+p.get('excluded_ideas',[])))
    if any(p.get('incomplete_extraction') and any(i['id']==original['id'] for i in p.get('ideas',[])+p.get('excluded_ideas',[])) for p in doc['parts']):
        raise ValueError('Réessayez d’abord les fragments non extraits de cette partie ; leurs identifiants doivent être stabilisés avant correction.')
    value={**original,'document':doc['id']}
    if action=='correct':
        for field in ('statement','explanation'):
            text=body.get(field)
            if not isinstance(text,str) or not text.strip() or len(text)>5000:raise ValueError('Renseignez un énoncé et une explication pour cette idée.')
            value[field]=text.strip()
        proof=body.get('evidence')
        if not isinstance(proof,list) or not 1<=len(proof)<=4:raise ValueError('Sélectionnez une à quatre citations exactes avec leurs pages.')
        source_doc=next(d for d in source['documents'] if d['id']==doc['id'])
        pages=quality.catalog(source_doc)
        for row in proof:
            if not isinstance(row,dict) or type(row.get('page')) is not int or row['page'] not in pages or not isinstance(row.get('quote'),str):raise ValueError('Page ou citation source invalide.')
            if len(row['quote'].strip())<20:raise ValueError('Choisissez une citation explicative d’au moins 20 caractères.')
            quality.explanatory_quote(row['quote'])
            if quality.normalized(row['quote']) not in quality.normalized(pages[row['page']]['text']):raise ValueError('La citation doit figurer exactement sur la page indiquée du PDF.')
        evidence=' '.join(row['quote'] for row in proof);text=value['statement']+' '+value['explanation']
        quality.validate_acronyms(text,doc.get('glossary',{}))
        quality.validate_evidence_details(text,evidence);quality.validate_technical_wording(text,evidence)
        value.pop('human_excluded',None)
        value.update(evidence=proof,pages=sorted({r['page'] for r in proof}),status='corrected',
            review_reason='Correction et appui aux sources validés par l’utilisateur.',
            support_reason=note or 'Appui vérifié manuellement.',human_review={'time':time.time(),'note':note})
        if value.get('role') not in editorial.ROLES:value.update(editorial.role_fallback(value))
        value['source_hash']=editorial.source_hash(value)
    elif not note.strip():raise ValueError('Indiquez pourquoi cette idée est écartée ; elle restera dans le dossier.')
    correction={'extraction_hash':fingerprint(source),'action':action,'idea':value,'note':note,'time':time.time()}
    corrections=read(folder/'corrections.json') if (folder/'corrections.json').exists() else {}
    corrections[value['id']]=correction
    data=apply_corrections(folder,data,corrections);data['source_diagnostic']=source_review.diagnostic(data)
    markdown='# Résumer les trois parties\n\n'+'\n\n'.join(
        '## '+d['id']+' — partie '+str(p['number'])+'\n\n'+render_part(p) for d in data['documents'] for p in d['parts'])
    write(folder/'corrections.json',corrections)
    # Archiver les agrégats dépendants, garder les unités inchangées et toutes les voix.
    invalidate(folder,2,partials=False)
    write_text(folder/'etapes/02.md',markdown)
    write(folder/'etapes/02.json',{**saved,'created':time.time(),'data':data})
    decision=reviews.decide(item['id'],action,note,correction)
    meta=read(folder/'projet.json');meta['summary_warnings']=sum(len(p.get('uncertain_ideas',[])) for d in data['documents'] for p in d['parts']);write(folder/'projet.json',meta)
    return {'saved':True,'decision':decision,'resume_from':3}
