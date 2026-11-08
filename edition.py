"""Corrections explicites : la diarisation brute reste immuable."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
from pathlib import Path

SCHEMA = 'doublagebasic.timeline-edit.v1'

def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)

def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + ' doit être un nombre fini')
    return float(value)

def validate(edit, project, previous=None):
    if not isinstance(edit, dict) or edit.get('schema') != SCHEMA:
        raise ValueError('Schéma de corrections inconnu')
    if edit.get('source_sha256') != project['source_sha256']:
        raise ValueError('Ce JSON appartient à une autre vidéo (SHA256 différent)')
    if edit.get('analysis_id') != project['analysis_id']:
        raise ValueError("Identifiant d'analyse différent")
    duration = number(edit.get('duration'), 'Durée')
    if abs(duration - project['duration']) > .1:
        raise ValueError('Durée différente')
    intervals = edit.get('intervals')
    if not isinstance(intervals, list) or len(intervals) > 100000:
        raise ValueError('Liste des intervalles invalide')
    result = {k: edit[k] for k in ('schema', 'analysis_id', 'source_sha256', 'duration')}
    seen = set()
    result['intervals'] = []
    for row in intervals:
        if not isinstance(row, dict):
            raise ValueError('Intervalle invalide')
        ident = row.get('id')
        if not isinstance(ident, str) or not ident or len(ident) > 128 or ident in seen:
            raise ValueError("Identifiant d'intervalle invalide ou dupliqué")
        seen.add(ident)
        start, end = number(row.get('start'), 'Début'), number(row.get('end'), 'Fin')
        if not 0 <= start < end <= duration + .001:
            raise ValueError('Intervalle hors de la vidéo')
        voice = row.get('character')
        if voice is not None and voice not in project['voices']:
            raise ValueError('Voix inconnue : ' + str(voice))
        reviewed = row.get('reviewed', False)
        if not isinstance(reviewed, bool):
            raise ValueError('Validation invalide')
        result['intervals'].append(dict(id=ident, start=start, end=end, character=voice, reviewed=reviewed))
    cuts = edit.get('cuts', (previous or {}).get('cuts', []))
    if not isinstance(cuts, list) or len(cuts) > 100000:
        raise ValueError('Liste de plans invalide')
    result['cuts'] = []
    seen = set()
    for row in cuts:
        if not isinstance(row, dict):
            raise ValueError('Plan invalide')
        ident, t = row.get('id'), number(row.get('time'), 'Plan')
        if not isinstance(ident, str) or not ident or len(ident) > 128 or ident in seen or not 0 <= t <= duration:
            raise ValueError('Plan hors limites ou dupliqué')
        seen.add(ident)
        reviewed = row.get('reviewed', False)
        if not isinstance(reviewed, bool):
            raise ValueError('Validation de plan invalide')
        result['cuts'].append(dict(id=ident, time=t, reviewed=reviewed))
    return copy.deepcopy(result)

def initial_edit(project, analysis):
    return dict(schema=SCHEMA, analysis_id=project['analysis_id'], source_sha256=project['source_sha256'],
                duration=project['duration'], intervals=copy.deepcopy(analysis['intervals']), cuts=copy.deepcopy(analysis['cuts']))
