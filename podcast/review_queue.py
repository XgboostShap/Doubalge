"""Dossier local de vérification, décisions humaines et corrections réutilisables."""
import copy
import time
from pathlib import Path

from storage import fingerprint, read, write
from issues import category


class Reviews:
    def __init__(self, project):
        self.project = Path(project)
        self.path = self.project/'verifications.json'

    def data(self):
        return read(self.path) if self.path.exists() else {'version':1, 'items':[], 'decisions':[]}

    def pending(self, step=None):
        data=self.data();changed=False
        path=self.project/'etapes/01.json'
        current=fingerprint(read(path)['data']) if path.exists() else None
        for item in data['items']:
            if item['status'] in ('pending','retry') and item.get('extraction_hash') and item['extraction_hash']!=current:
                item['status']='stale';changed=True
        if changed:write(self.path,data)
        return [i for i in data['items'] if i['status']=='pending' and (step is None or i['step']==step)]

    def record(self, step, key, idea, error):
        source = copy.deepcopy(idea)
        identity = fingerprint({'project':self.project.name,'step':step, 'key':key, 'source':source})[:24]
        data = self.data()
        item = next((i for i in data['items'] if i['id']==identity), None)
        if item is None:
            item = {'id':identity, 'step':step, 'key':key, 'idea_id':source.get('id',''),
                    'source':source, 'created':time.time(), 'attempts':0}
            data['items'].append(item)
        path=self.project/'etapes/01.json'
        if path.exists():item['extraction_hash']=fingerprint(read(path)['data'])
        # Une nouvelle source rend l’ancienne question caduque, sans effacer son historique.
        for old in data['items']:
            if old['id']!=identity and old['step']==step and old['key']==key and old['status']=='pending':
                old['status']='stale'
        item.update(status='pending', category=category(error), reason=str(error), updated=time.time(),
                    attempts=item['attempts']+1)
        draft = getattr(error, 'draft_text', None)
        if isinstance(draft,str): item['draft']=draft
        write(self.path,data)
        return item

    def completed(self, step, key):
        data = self.data(); changed=False
        for item in data['items']:
            if item['step']==step and item['key']==key and item['status'] in ('pending','retry'):
                item.update(status='validated', updated=time.time());changed=True
        if changed: write(self.path,data)

    def decide(self, identity, action, note='', correction=None):
        data=self.data()
        item=next((i for i in data['items'] if i['id']==identity),None)
        if item is None or item['status']!='pending': raise ValueError('Vérification absente ou déjà traitée.')
        if action not in ('correct','exclude','retry'): raise ValueError('Décision inconnue.')
        decision={'review_id':identity,'idea_id':item['idea_id'],'action':action,'note':note,
                  'time':time.time(),'correction':correction}
        data['decisions'].append(decision)
        for other in data['items']:
            if other['id']==identity or (action!='retry' and other['idea_id']==item['idea_id'] and other['status']=='pending'):
                other.update(status='retry' if action=='retry' else 'resolved',updated=decision['time'])
        write(self.path,data)
        return decision


def apply_corrections(project, data, corrections=None):
    """Appliquer après lecture des parties en cache, jamais à l’intérieur du cache."""
    path=Path(project)/'corrections.json'
    if corrections is None:
        if not path.exists(): return data
        corrections=read(path)
    source=read(Path(project)/'etapes/01.json')['data']
    signature=fingerprint(source)
    from editorial import source_hash, summary
    for doc in data['documents']:
        for part in doc['parts']:
            for identity,record in corrections.items():
                if record['extraction_hash']!=signature: continue
                candidates=part.get('ideas',[])+part.get('excluded_ideas',[])
                if not any(i['id']==identity for i in candidates): continue
                position=next((index for index,i in enumerate(part['ideas']) if i['id']==identity),len(part['ideas']))
                part['ideas']=[i for i in part['ideas'] if i['id']!=identity]
                part['excluded_ideas']=[i for i in part.get('excluded_ideas',[]) if i['id']!=identity]
                value=copy.deepcopy(record['idea'])
                if record['action']=='correct':
                    value['source_hash']=source_hash(value)
                    part['ideas'].insert(position,value)
                else: part['excluded_ideas'].append({**value,'reason':record['note'],'human_excluded':True})
                part['uncertain_ideas']=[i for i in part.get('uncertain_ideas',[]) if i['id']!=identity]
            part['summary']=summary(part['ideas'])[0] if part['ideas'] else 'Aucune idée explicative retenue dans cette partie.'
    return data
