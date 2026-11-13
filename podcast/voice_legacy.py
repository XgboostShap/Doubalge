"""Réglages de l'ancienne IHM et dialogues fournis, sans exécuter leur code."""
import ast
import json
import re
from storage import fingerprint


def read_settings(source):
    if not isinstance(source,str) or len(source)>500000:raise ValueError('Fichier de réglages vide ou trop volumineux.')
    values={}
    if source.lstrip().startswith('{'):
        try:values=json.loads(source)
        except ValueError:raise ValueError('Le fichier de réglages JSON est invalide.') from None
        if not isinstance(values,dict):raise ValueError('Un objet de réglages JSON est requis.')
    else:
        try:tree=ast.parse(source)
        except (SyntaxError,RecursionError):raise ValueError('Le fichier Python de réglages est invalide.') from None
        names={'voice_studio_url','vs_anneso','vs_sophie','pause_ms','normalize_audio','target_dbfs'}
        for node in ast.walk(tree):
            if not isinstance(node,ast.Assign) or not isinstance(node.value,ast.Call):continue
            name=next((t.id for t in node.targets if isinstance(t,ast.Name) and t.id in names),None)
            if not name:continue
            call=node.value;kind=getattr(call.func,'attr','')
            value_node=next((k.value for k in call.keywords if k.arg=='value'),None)
            if value_node is None:
                position=3 if kind=='slider' else 1
                if len(call.args)>position:value_node=call.args[position]
            try:values[name]=ast.literal_eval(value_node)
            except (ValueError,TypeError,RecursionError):continue
    if not all(isinstance(values.get(k),str) and values[k].strip() for k in ('vs_anneso','vs_sophie')):
        raise ValueError('Les réglages doivent contenir vs_anneso et vs_sophie. Choisissez l’ancien podcast_interface.py ou son export JSON.')
    if values['vs_anneso'].strip()==values['vs_sophie'].strip():raise ValueError('Les deux profils doivent être distincts.')
    return {'endpoint':values.get('voice_studio_url','http://127.0.0.1:3900'),'model':'tts-1',
        'voices':{'AnneSo':values['vs_anneso'].strip(),'Sophie':values['vs_sophie'].strip()},
        'pause_ms':values.get('pause_ms',350),'normalize_audio':values.get('normalize_audio',True),
        'target_dbfs':values.get('target_dbfs',-20),'speed':1.0}


def parse_dialogue(text):
    if not isinstance(text,str) or not text.strip() or len(text)>300000:raise ValueError('Choisissez un dialogue TXT non vide, de 300 000 caractères maximum.')
    turns=[];names={}
    for number,line in enumerate(text.replace('\ufeff','').splitlines(),1):
        if not line.strip():continue
        match=re.match(r"^\s*([^\W\d_][\wÀ-ÿ .'’-]{0,39})\s*[:：]\s*(.*)$",line)
        if match:
            name=match[1].strip()
            if name.casefold()=='annso':name='AnneSo'
            key=name.casefold();names.setdefault(key,name)
            turns.append({'speaker':names[key],'text':match[2].strip(),'idea_ids':[],'kind':'provided'})
        elif turns:turns[-1]['text']+=' '+line.strip()
        else:raise ValueError('Ligne '+str(number)+' : commencer par le nom de l’intervenant suivi de deux-points.')
    if not 2<=len(names)<=3:raise ValueError('Le dialogue doit comporter deux ou trois intervenants nommés.')
    if any(not t['text'].strip() for t in turns):raise ValueError('Une réplique du dialogue est vide.')
    if not turns:raise ValueError('Aucune réplique à lire.')
    return {'source_kind':'provided_text','source_text':text,'input_hash':fingerprint(text),
        'speakers':list(names.values()),'chapters':[{'id':'LECTURE','title':'Dialogue fourni','opening_transition':'','turns':turns}],
        'note':'Texte fourni pour lecture audio ; il n’a pas été validé par les neuf étapes de contrôle des sources.'}
