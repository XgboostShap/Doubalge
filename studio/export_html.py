"""Exports autonomes reprenant les interfaces HTML fournies par l'utilisateur."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / 'templates'
COLORS = ['#ff6500', '#7900d8', '#098f92', '#dd3366', '#4e9dec', '#c6a328']
SCHEMA = 'doublagebasic.timeline-edit.v1'


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
            'id': identifier, 'label': f'Voix {index + 1}', 'color': COLORS[index % len(COLORS)],
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
        'characters': characters, 'duoDefaultMode': 'play_one',
        'defaultCharacter': characters[0]['id'] if characters else 'background',
        'automatic': [{**i, 'confidence': 'proposition audio'} for i in intervals],
        'initial': copy.deepcopy(intervals), 'automaticCuts': copy.deepcopy(cuts),
        'initialCuts': copy.deepcopy(cuts), 'peaks': peaks,
        'media': donnees_media(editor_video, 'video/mp4'),
        'improMedia': donnees_media(muted_video, 'video/mp4'),
        'improTemplate': (TEMPLATES / 'impro.html').read_text(encoding='utf-8'),
    }
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
    editor = (TEMPLATES / 'editeur.html').read_text(encoding='utf-8')
    if editor.count('__EDITOR_DATA__') != 1:
        raise ValueError('Gabarit éditeur incomplet.')
    impro_template = document['improTemplate']
    if impro_template.count('__IMPRO_DATA__') != 1:
        raise ValueError('Gabarit impro incomplet.')
    player = {'duration': document['duration'], 'characters': document['characters'],
              'intervals': document['initial'], 'cuts': document['initialCuts'],
              'media': document['improMedia']}
    if 'duoAudio' in document:
        player.update(duoAudio=document['duoAudio'], keepCharacter=document['defaultCharacter'],
                      duoMode=document['duoDefaultMode'])
    editor_file, player_file = sortie / 'OSS-editeur.html', sortie / 'OSS.html'
    for path, text in [
        (editor_file, editor.replace('__EDITOR_DATA__', serialiser_html(document))),
        (player_file, impro_template.replace('__IMPRO_DATA__', serialiser_html(player))),
    ]:
        temporary = path.with_suffix('.html.tmp')
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(path)
    ecrire_json(sortie / 'corrections-initiales.json', {
        'schema': document['schema'], 'analysis_id': document['analysis_id'],
        'source_sha256': document['source_sha256'], 'duration': document['duration'],
        'intervals': document['initial'], 'cuts': document['initialCuts'],
    })
    return editor_file, player_file
