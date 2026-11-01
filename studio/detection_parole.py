"""Détection locale des locuteurs, sans fusionner les pauses ni perdre les chevauchements."""
from __future__ import annotations

import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MODEL = 'pyannote/speaker-diarization-community-1'
MODEL_REVISION = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'
RUNTIME_MARKER = 'community-1-v1'


def python_avance():
    override = os.environ.get('DOUBLAGE_DETECTION_PYTHON')
    if override:
        # Ne pas résoudre le lien de l’exécutable : cela sortirait du venv sous Linux.
        return Path(override).absolute()
    directory = ROOT / '.venv-detection'
    executable = directory / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    marker = directory / 'installation-ok.txt'
    try:
        if executable.is_file() and marker.read_text(encoding='utf-8').strip() == RUNTIME_MARKER:
            return executable
    except (OSError, UnicodeError):
        pass
    return None


def extraire_tours(result):
    annotation = getattr(result, 'speaker_diarization', result)
    if hasattr(annotation, 'itertracks'):
        return [(turn.start, turn.end, label) for turn, _, label in annotation.itertracks(yield_label=True)]
    raise TypeError('Format de résultat de détection non reconnu.')


def normaliser_tours(turns, duration):
    """Conserve les interruptions courtes et les voix simultanées.

    Seules les plages qui se chevauchent pour une même voix sont réunies.
    Les numéros de voix suivent leur première apparition chronologique.
    """
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Durée de détection invalide.')
    clean = []
    for start, end, label in turns:
        if not all(math.isfinite(t) for t in (start, end)) or end <= start:
            raise ValueError('Le modèle a produit des bornes de parole invalides.')
        start, end = round(max(0, start), 3), min(duration, round(end, 3))
        if end > start:
            clean.append((start, end, str(label)))
    clean.sort()
    labels, grouped = {}, {}
    for start, end, label in clean:
        speaker = labels.setdefault(label, len(labels))
        events = grouped.setdefault(speaker, [])
        if events and start <= events[-1]['end']:
            events[-1]['end'] = max(events[-1]['end'], end)
        else:
            events.append({'start': start, 'end': end, 'speaker': speaker})
    return sorted((e for events in grouped.values() for e in events), key=lambda e: (e['start'], e['end'], e['speaker']))


def charger_audio(wav):
    import soundfile as sf
    import torch
    samples, rate = sf.read(wav, dtype='float32', always_2d=True)
    if rate != 16000 or not len(samples):
        raise ValueError('La détection nécessite un fichier audio 16 kHz non vide.')
    # Charger en mémoire évite les dépendances DLL de décodage sur Windows.
    waveform = torch.from_numpy(samples.T.copy()).mean(dim=0, keepdim=True)
    return {'waveform': waveform, 'sample_rate': rate}


def classique(wav, token, speakers, cpu, duration):
    import torch
    from pyannote.audio import Pipeline
    from pyannote.audio.core.task import Problem, Resolution, Specifications
    torch.set_num_threads(min(os.cpu_count() or 1, 4))
    device = torch.device('cuda' if not cpu and torch.cuda.is_available() else 'cpu')
    with torch.serialization.safe_globals([torch.torch_version.TorchVersion, Problem, Resolution, Specifications]):
        pipeline = Pipeline.from_pretrained('pyannote/speaker-diarization-3.1', use_auth_token=token)
        if pipeline is None:
            raise RuntimeError('Modèle classique inaccessible. Vérifiez votre token et les conditions Hugging Face.')
        pipeline.to(device)
        output = pipeline(charger_audio(wav), **({'num_speakers': speakers} if speakers else {}))
    return {'events': normaliser_tours(extraire_tours(output), duration), 'model': 'pyannote/speaker-diarization-3.1',
            'device': str(device), 'postprocessing': 'overlap-only-v1'}


def detecter(wav, token, speakers, cpu, duration, travail, mode='auto'):
    if mode not in {'auto', 'community-1', 'classique'}:
        raise ValueError('Mode de détection inconnu.')
    if type(speakers) is not int or not 0 <= speakers <= 100:
        raise ValueError('Le nombre de voix doit être compris entre 0 et 100.')
    executable = python_avance()
    if mode == 'classique' or mode == 'auto' and executable is None:
        print('[détection] Modèle classique 3.1 ; pauses courtes conservées.', flush=True)
        if mode == 'auto':
            print('[détection] Pour activer Community-1, exécutez la nouvelle version de Installer-studio.cmd.', flush=True)
        return classique(wav, token, speakers, cpu, duration)
    if executable is None:
        raise RuntimeError('Installez la détection Community-1 avec Installer-studio.cmd, ou choisissez le modèle classique.')
    output = Path(travail) / 'detection-community.json'
    command = [str(executable), '-X', 'utf8', '-u', str(Path(__file__).with_name('detection_worker.py')),
               '--audio', str(wav), '--sortie', str(output), '--duration', str(duration), '--personnages', str(speakers)]
    if cpu:
        command.append('--cpu')
    environment = os.environ.copy()
    environment['DOUBLAGE_HF_TOKEN'] = token
    environment['PYANNOTE_METRICS_ENABLED'] = '0'
    print('[détection] Community-1 — analyse locale.', flush=True)
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment,
                          text=True, encoding='utf-8', errors='replace') as process:
        for line in process.stdout:
            print(line.rstrip(), flush=True)
        code = process.wait()
    if code:
        raise RuntimeError('Community-1 n’a pas terminé. Consultez le message ci-dessus ; aucune analyse classique ne remplace silencieusement son résultat.')
    import json
    return json.loads(output.read_text(encoding='utf-8'))
