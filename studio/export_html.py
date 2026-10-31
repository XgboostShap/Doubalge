"""Exports autonomes reprenant les interfaces HTML fournies par l'utilisateur."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / 'templates'
COLORS = ['#ff6500', '#7900d8', '#098f92', '#dd3366', '#4e9dec', '#c6a328']
SCHEMA = 'doublagebasic.timeline-edit.v1'


def valider_mix(value, known):
    if value is None:
        return {'removedCharacters': [], 'keepAmbience': True, 'keepUnknown': True}
    if (not isinstance(value, dict) or not isinstance(value.get('removedCharacters'), list)
            or any(type(x) is not str or x not in known for x in value['removedCharacters'])
            or type(value.get('keepAmbience')) is not bool or type(value.get('keepUnknown')) is not bool):
        raise ValueError('Choix des voix ou de l’ambiance invalide.')
    return {'removedCharacters': list(dict.fromkeys(value['removedCharacters'])),
            'keepAmbience': value['keepAmbience'], 'keepUnknown': value['keepUnknown']}


def valider_corrections(data, source_hash, duration, analysis_id=None, known=None):
    if (not isinstance(data, dict) or data.get('schema') != SCHEMA
            or data.get('source_sha256') != source_hash):
        raise ValueError('Ces corrections ne correspondent pas à cette vidéo.')
    if (not isinstance(data.get('analysis_id'), str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', data['analysis_id'])
            or analysis_id is not None and data['analysis_id'] != analysis_id):
        raise ValueError('Ces corrections appartiennent à une autre analyse.')
    if (type(data.get('duration')) not in (int, float) or not math.isfinite(data['duration'])
            or abs(data['duration'] - duration) > .01):
        raise ValueError('La durée des corrections ne correspond pas à la vidéo.')
    clean = {'schema': SCHEMA, 'source_sha256': source_hash, 'analysis_id': data['analysis_id'],
             'duration': duration, 'intervals': [], 'cuts': []}
    for key in ['intervals', 'cuts']:
        if not isinstance(data.get(key), list) or len(data[key]) > 10000:
            raise ValueError('Liste de corrections invalide.')
        identifiers = set()
        for entry in data[key]:
            if (not isinstance(entry, dict) or not isinstance(entry.get('id'), str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', entry['id'])
                    or entry['id'] in identifiers or type(entry.get('reviewed')) is not bool):
                raise ValueError('Identifiant ou état de validation invalide.')
            identifiers.add(entry['id'])
            fields = ['start', 'end'] if key == 'intervals' else ['time']
            if any(type(entry.get(f)) not in (int, float) or not math.isfinite(entry[f]) for f in fields):
                raise ValueError('Instant de correction invalide.')
            if key == 'intervals':
                if 'character' not in entry:
                    raise ValueError('Voix manquante dans les corrections.')
                character = entry.get('character')
                if (not 0 <= entry['start'] < entry['end'] <= duration or character is not None
                        and (not isinstance(character, str) or not re.fullmatch(r'voice:[0-9]{1,3}', character)
                             or known is not None and character not in known)):
                    raise ValueError('Voix ou bornes de parole invalides.')
                clean[key].append({f: entry[f] for f in ['id', 'start', 'end', 'character', 'reviewed']})
            else:
                if not 0 < entry['time'] < duration:
                    raise ValueError('Plan hors de la vidéo.')
                clean[key].append({f: entry[f] for f in ['id', 'time', 'reviewed']})
    clean['intervals'].sort(key=lambda i: (i['start'], i['end'], i['id']))
    clean['cuts'].sort(key=lambda c: (c['time'], c['id']))
    if any(abs(a['time'] - b['time']) < .005 for a, b in zip(clean['cuts'], clean['cuts'][1:])):
        raise ValueError('Deux plans occupent le même instant.')
    inferred = {i['character'] for i in clean['intervals'] if i['character'] is not None}
    if isinstance(data.get('characters'), list):
        characters = data['characters']
        if len(characters) > 100 or any(not isinstance(p, dict) or not isinstance(p.get('id'), str)
                or not re.fullmatch(r'voice:[0-9]{1,3}', p['id']) for p in characters):
            raise ValueError('Liste des voix invalide.')
        if len({p['id'] for p in characters}) != len(characters):
            raise ValueError('Une voix apparaît plusieurs fois dans les corrections.')
        character_ids = {p['id'] for p in characters}
        if not inferred <= character_ids or known is not None and not character_ids <= known:
            raise ValueError('Les voix déclarées ne correspondent pas aux passages corrigés.')
        clean['characters'] = [{'id': p['id'], 'label': str(p.get('label', p['id']))[:80],
                                'color': p.get('color') if isinstance(p.get('color'), str)
                                and re.fullmatch(r'#[0-9a-fA-F]{6}', p['color']) else COLORS[n % len(COLORS)]}
                               for n, p in enumerate(characters)]
        inferred.update(p['id'] for p in characters)
    clean['audioMix'] = valider_mix(data.get('audioMix'), known if known is not None else inferred)
    return clean


def empreinte(path: Path) -> str:
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def ecrire_json(path: Path, data) -> None:
    text = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)
    temporaire = path.with_suffix(path.suffix + '.tmp')
    temporaire.write_text(text, encoding='utf-8')
    temporaire.replace(path)


def donnees_media(path: Path, mime: str) -> str:
    return 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


def construire_document(analysis: dict, peaks: list[float], editor_video: Path,
                        muted_video: Path, pistes: tuple[Path, Path] | None = None) -> dict:
    duration = float(analysis['duration'])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Durée de vidéo invalide.')
    speakers = sorted({event['speaker'] for event in analysis['events']})
    if any(type(speaker) is not int or speaker < 0 for speaker in speakers):
        raise ValueError('Identifiant de voix invalide.')
    characters = []
    for index, speaker in enumerate(speakers):
        identifier = f'voice:{speaker}'
        events = [e for e in analysis['events'] if e['speaker'] == speaker]
        reference = max(events, key=lambda e: e['end'] - e['start'])
        characters.append({
            'id': identifier, 'label': f'Voix {speaker + 1}', 'color': COLORS[index % len(COLORS)],
            'photo': analysis.get('photos', {}).get(str(speaker)),
            'reference': {'character': identifier, 'start': reference['start'],
                          'end': min(reference['end'], reference['start'] + 5),
                          'text': 'Extrait repère de cette voix'},
        })
    intervals = []
    for index, event in enumerate(analysis['events']):
        start, end = float(event['start']), float(event['end'])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration):
            raise ValueError(f'Bornes invalides pour le passage {index + 1}.')
        intervals.append({'id': f'e{index:06d}', 'start': start, 'end': end,
                          'character': f"voice:{event['speaker']}", 'reviewed': False})
    cut_times = sorted(set(float(t) for t in analysis['cuts']))
    if any(not math.isfinite(t) or t <= 0 or t >= duration for t in cut_times):
        raise ValueError('Un changement de plan est hors de la vidéo.')
    cuts = [{'id': f'cut-{index:04d}', 'time': t, 'reviewed': False}
            for index, t in enumerate(cut_times)]
    document = {
        'schema': SCHEMA, 'analysis_id': analysis['analysis_id'],
        'source_sha256': analysis['source_sha256'], 'duration': duration, 'fps': analysis.get('fps', 25),
        'characters': characters, 'title': Path(analysis.get('source', 'Scène')).stem,
        'audioMix': valider_mix(None, set()), 'duoDefaultMode': 'play_one',
        'defaultCharacter': characters[0]['id'] if characters else 'background',
        'automatic': [{**i, 'confidence': 'proposition audio'} for i in intervals],
        'initial': copy.deepcopy(intervals), 'automaticCuts': copy.deepcopy(cuts),
        'initialCuts': copy.deepcopy(cuts), 'peaks': peaks,
        'media': donnees_media(editor_video, 'video/mp4'),
        'improMedia': donnees_media(muted_video, 'video/mp4'),
        'improTemplate': (TEMPLATES / 'impro.html').read_text(encoding='utf-8'),
        'showTemplate': (TEMPLATES / 'spectacle.html').read_text(encoding='utf-8'),
    }
    if analysis.get('corrections'):
        corrections = valider_corrections(analysis['corrections'], analysis['source_sha256'], duration,
                                           analysis['analysis_id'])
        if corrections.get('characters'):
            by_id = {p['id']: p for p in document['characters']}
            document['characters'] = [{**by_id.get(p['id'], {'photo': None}), **p}
                                      for p in corrections['characters']]
        document['initial'] = corrections['intervals']
        document['initialCuts'] = corrections['cuts']
        document['audioMix'] = corrections['audioMix']
        for person in document['characters']:
            candidates = [i for i in corrections['intervals'] if i['character'] == person['id']]
            if candidates:
                reference = max(candidates, key=lambda i: (i['reviewed'], i['end'] - i['start']))
                person['reference'] = {'character': person['id'], 'start': reference['start'],
                                       'end': min(reference['end'], reference['start'] + 5),
                                       'text': 'Extrait repère corrigé'}
            else:
                person.pop('reference', None)
        if analysis.get('corrected_only'):
            document['automatic'] = []
            document['automaticCuts'] = []
    if pistes:
        dialogue, background = pistes
        document['duoAudio'] = {
            'model': 'torchaudio/HDEMUCS_HIGH_MUSDB_PLUS', 'experimental': True,
            'source_sha256': analysis['source_sha256'],
            'render_source_sha256': empreinte(editor_video),
            'analysis_id': analysis['analysis_id'], 'duration': duration,
            'fade': .01, 'dialogue': donnees_media(dialogue, 'audio/mp4'),
            'background': donnees_media(background, 'audio/mp4'),
            'codec': 'aac_m4a', 'sample_rate': 24000,
        }
    return document


def serialiser_html(data: dict) -> str:
    # Un nom de personnage ou une métadonnée ne doit pas fermer le script JSON.
    return json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')


def exporter(document: dict, sortie: Path) -> tuple[Path, Path]:
    sortie.mkdir(parents=True, exist_ok=True)
    document = copy.deepcopy(document)
    document['improTemplate'] = (TEMPLATES / 'impro.html').read_text(encoding='utf-8')
    document['showTemplate'] = (TEMPLATES / 'spectacle.html').read_text(encoding='utf-8')
    editor = (TEMPLATES / 'editeur.html').read_text(encoding='utf-8')
    if editor.count('__EDITOR_DATA__') != 1:
        raise ValueError('Gabarit éditeur incomplet.')
    impro_template = document['improTemplate']
    if impro_template.count('__IMPRO_DATA__') != 1:
        raise ValueError('Gabarit impro incomplet.')
    player = {'duration': document['duration'], 'characters': document['characters'],
              'intervals': document['initial'], 'cuts': document['initialCuts'],
              'media': document['improMedia'] if 'duoAudio' in document else document['media'],
              'title': document.get('title', 'Scène'), 'analysis_id': document['analysis_id'],
              'source_sha256': document['source_sha256'], 'showTemplate': document['showTemplate']}
    if 'audioMix' in document:
        player['audioMix'] = document['audioMix']
    if 'duoAudio' in document:
        player.update(duoAudio=document['duoAudio'], keepCharacter=document['defaultCharacter'],
                      duoMode=document['duoDefaultMode'])
    editor_file, player_file = sortie / 'OSS-editeur.html', sortie / 'OSS.html'
    show_data = {'schema': 'doublagebasic.show.v1', 'autoAdvance': False,
                 'scenes': [{'title': player['title'], 'data': {k: v for k, v in player.items() if k != 'showTemplate'},
                             'performers': {}}]}
    for path, text in [
        (editor_file, editor.replace('__EDITOR_DATA__', serialiser_html(document))),
        (player_file, impro_template.replace('__IMPRO_DATA__', serialiser_html(player))),
        (sortie / 'Spectacle.html', document['showTemplate'].replace('__SHOW_DATA__', serialiser_html(show_data))),
    ]:
        temporary = path.with_suffix('.html.tmp')
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(path)
    ecrire_json(sortie / 'corrections-initiales.json', {
        'schema': document['schema'], 'analysis_id': document['analysis_id'],
        'source_sha256': document['source_sha256'], 'duration': document['duration'],
        'intervals': document['initial'], 'cuts': document['initialCuts'],
        'audioMix': document.get('audioMix'), 'characters': document['characters'],
    })
    return editor_file, player_file
