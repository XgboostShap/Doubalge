"""Sauvegardes atomiques et versions des résultats intermédiaires."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        temp = f.name
    os.replace(temp, path)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def invalidate(project, first):
    """Archive les anciens résultats ; les PDF originaux restent inchangés."""
    old = [p for p in (project / 'etapes').glob('*') if p.name[:2].isdigit() and int(p.name[:2]) >= first]
    if old:
        folder = project / 'versions' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        for path in old:
            path.replace(folder / path.name)
        for path in (project/'exports').glob('*'):
            if path.is_file():
                path.replace(folder/('export-'+path.name))
        if first<=8:
            for path in (project/'memoire').glob('*.json'):
                path.replace(folder/('memoire-'+path.name))


def defaults():
    return {'endpoint':'http://127.0.0.1:11434', 'model':'mistral', 'audience':'Adultes curieux, sans connaissance préalable',
            'minutes':20, 'speakers':['Sophie','Emma'], 'num_ctx':16384, 'temperature':.3}
