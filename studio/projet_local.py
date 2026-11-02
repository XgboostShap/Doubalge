"""Projet de bureau : médias intégrés au document, corrections atomiques séparées."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import threading

from export_html import ecrire_json, valider_corrections

PROJECT_SCHEMA = 'doubalge.project.v1'


class Projet:
    def __init__(self, manifest):
        self.path = Path(manifest).resolve(strict=True)
        metadata = json.loads(self.path.read_text(encoding='utf-8-sig'))
        if metadata.get('schema') != PROJECT_SCHEMA:
            raise ValueError('Ce fichier n’est pas un projet Doubalge.')
        self.folder = self.path.parent
        self._document = json.loads((self.folder/'document.json').read_text(encoding='utf-8'))
        self._lock = threading.RLock()
        self._lease = None
        self._known = {p['id'] for p in self._document['characters']}
        # Une sauvegarde abîmée doit être signalée, jamais remplacée silencieusement.
        self.edits = self.validate(json.loads((self.folder/'corrections.json').read_text(encoding='utf-8')))

    @classmethod
    def create(cls, folder, document):
        folder = Path(folder).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        if any((folder/name).exists() for name in ['projet.doubalge','document.json','corrections.json']):
            raise ValueError('Ce dossier contient déjà un projet. Choisissez un nouveau dossier.')
        data = copy.deepcopy(document)
        data.pop('improTemplate',None)
        data.pop('showTemplate',None)
        edits = {k:data[k] for k in ['schema','analysis_id','source_sha256','duration','characters']}
        edits.update(intervals=data['initial'], cuts=data['initialCuts'], audioMix=data.get('audioMix'))
        edits = valider_corrections(edits,data['source_sha256'],data['duration'],data['analysis_id'],
                                   {p['id'] for p in data['characters']})
        ecrire_json(folder/'document.json', data)
        ecrire_json(folder/'corrections.json', edits)
        ecrire_json(folder/'projet.doubalge',{'schema':PROJECT_SCHEMA,'title':data.get('title','Scène')})
        return cls(folder/'projet.doubalge')

    def validate(self, edits):
        return valider_corrections(edits,self._document['source_sha256'],self._document['duration'],
                                  self._document['analysis_id'],self._known)

    def save(self, edits):
        clean = self.validate(edits)
        clean['savedAt'] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            shutil.copy2(self.folder/'corrections.json',self.folder/'corrections-precedentes.json')
            ecrire_json(self.folder/'corrections.json',clean)
            self.edits = clean
        return clean['savedAt']

    def document(self):
        with self._lock:
            data = copy.deepcopy(self._document)
            edits = copy.deepcopy(self.edits)
        data['initial'],data['initialCuts'],data['audioMix'] = edits['intervals'],edits['cuts'],edits['audioMix']
        names = {p['id']:p for p in edits.get('characters',[])}
        data['characters'] = [{**p,**names.get(p['id'],{})} for p in data['characters']]
        return data

    def acquire(self):
        if self._lease:
            return
        lease = (self.folder/'.ouvert.lock').open('a+b')
        try:
            lease.seek(0,2)
            if lease.tell() == 0:
                lease.write(b'0'); lease.flush()
            lease.seek(0)
            import os
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            lease.close()
            raise ValueError('Ce projet est déjà ouvert dans une autre fenêtre Doubalge.') from error
        self._lease = lease

    def release(self):
        if self._lease:
            self._lease.close()
            self._lease = None
