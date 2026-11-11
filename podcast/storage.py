"""Sauvegardes atomiques et versions des résultats intermédiaires."""
import hashlib
from contextlib import ExitStack
import errno
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid


# Windows refuse le remplacement d'un fichier ouvert sans FILE_SHARE_DELETE.
# Les lecteurs de l'interface et le worker doivent donc partager les verrous.
# Le nombre de verrous est borné, même avec un cache contenant beaucoup de fichiers.
_LOCKS = [threading.RLock() for _ in range(64)]
_RETRY_DELAYS = (0, .025, .05, .1, .2, .4, .8, 1, 1.5, 2)


def _lock_index(path):
    return hash(os.path.normcase(os.path.abspath(os.fspath(path)))) % len(_LOCKS)


def _retry(operation):
    for attempt, delay in enumerate(_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            return operation()
        except OSError as error:
            windows_code = getattr(error, 'winerror', None)
            transient = (windows_code in (5, 32, 33) if windows_code is not None
                         else error.errno in (errno.EACCES, errno.EPERM, errno.EBUSY))
            if not transient or attempt == len(_RETRY_DELAYS)-1:
                raise


def read(path):
    path = Path(path)
    with _LOCKS[_lock_index(path)]:
        return json.loads(_retry(lambda: path.read_text(encoding='utf-8')))


def write(path, value):
    path = Path(path)
    with _LOCKS[_lock_index(path)]:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8',
                                             prefix='.'+path.name+'-', suffix='.tmp', delete=False) as f:
                temp = Path(f.name)
                json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            # Le fichier temporaire est fermé AVANT la première tentative.
            # Ne jamais supprimer l'ancien fichier pour contourner un verrou.
            _retry(lambda: os.replace(temp, path))
        finally:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass  # Ne pas masquer l'erreur de sauvegarde initiale.


def replace(source, destination):
    """Déplacement atomique, y compris si Windows bloque brièvement un lecteur."""
    with ExitStack() as stack:
        for index in sorted({_lock_index(source), _lock_index(destination)}):
            stack.enter_context(_LOCKS[index])
        return _retry(lambda: os.replace(source, destination))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def invalidate(project, first):
    """Archive les anciens résultats ; les PDF originaux restent inchangés."""
    old = [p for p in (project / 'etapes').glob('*') if p.name[:2].isdigit() and int(p.name[:2]) >= first]
    if old:
        folder = project / 'versions' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        for path in old:
            replace(path, folder / path.name)
        for path in (project/'exports').glob('*'):
            if path.is_file():
                replace(path, folder/('export-'+path.name))
        if first<=8:
            for path in (project/'memoire').glob('*.json'):
                replace(path, folder/('memoire-'+path.name))


def defaults():
    return {'endpoint':'http://127.0.0.1:11434', 'model':'mistral', 'audience':'Adultes curieux, sans connaissance préalable',
            'minutes':20, 'speakers':['Sophie','Emma'], 'num_ctx':16384, 'temperature':.3}
