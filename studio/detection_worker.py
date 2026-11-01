"""Processus isolé Community-1 : libère le GPU avant la préparation du lecteur."""
from __future__ import annotations

import argparse
from importlib.metadata import version
import os
from pathlib import Path
import sys

from detection_parole import MODEL, MODEL_REVISION, ROOT, charger_audio, extraire_tours, normaliser_tours
from export_html import ecrire_json


def fichiers_modele(token):
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    required = ['config.yaml', 'embedding/pytorch_model.bin', 'segmentation/pytorch_model.bin',
                'plda/plda.npz', 'plda/xvec_transform.npz']
    try:
        folder = snapshot_download(MODEL, revision=MODEL_REVISION, token=token, local_files_only=True)
        if all((Path(folder) / name).is_file() for name in required):
            return folder
    except LocalEntryNotFoundError:
        pass
    return snapshot_download(MODEL, revision=MODEL_REVISION, token=token,
                             allow_patterns=['config.yaml', 'embedding/*', 'segmentation/*', 'plda/*'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--sortie', type=Path, required=True)
    parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--personnages', type=int, default=0)
    parser.add_argument('--cpu', action='store_true')
    args = parser.parse_args()
    os.environ.pop('HF_HUB_OFFLINE', None)
    os.environ.setdefault('HF_HOME', str(ROOT / '.cache' / 'huggingface'))
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.cache' / 'matplotlib'))
    os.environ['PYANNOTE_METRICS_ENABLED'] = '0'
    import torch
    from pyannote.audio import Pipeline
    torch.set_num_threads(min(os.cpu_count() or 1, 4))
    token = os.environ.get('DOUBLAGE_HF_TOKEN')
    if not token:
        raise RuntimeError('Token Hugging Face absent du processus de détection.')
    print('[détection] Chargement de Community-1 (téléchargement unique si absent du cache).', flush=True)
    folder = fichiers_modele(token)
    pipeline = Pipeline.from_pretrained(folder)
    if pipeline is None:
        raise RuntimeError('Modèle Community-1 inaccessible.')
    device = torch.device('cuda' if not args.cpu and torch.cuda.is_available() else 'cpu')
    pipeline.to(device)
    print('[détection] ' + (torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'), flush=True)
    last = None

    def progress(step_name, step_artifact=None, file=None, total=None, completed=None):
        nonlocal last
        if step_name != last:
            print('[détection] ' + step_name + '…', flush=True)
            last = step_name

    result = pipeline(charger_audio(args.audio), hook=progress,
                      **({'num_speakers': args.personnages} if args.personnages else {}))
    events = normaliser_tours(extraire_tours(result), args.duration)
    ecrire_json(args.sortie, {'events': events, 'model': MODEL, 'revision': MODEL_REVISION,
                            'pyannote_audio': version('pyannote.audio'), 'num_speakers_requested': args.personnages,
                            'device': str(device), 'postprocessing': 'overlap-only-v1'})
    print(f'[détection] {len(events)} plages ; {len({e["speaker"] for e in events})} voix.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'[détection — erreur] {error}', file=sys.stderr)
        if isinstance(error, ImportError):
            print('Relancez Installer-studio.cmd à jour pour installer la détection améliorée.', file=sys.stderr)
        else:
            print('En cas d’accès refusé, vérifiez token_hf.txt et les conditions sur '
                  'https://huggingface.co/pyannote/speaker-diarization-community-1', file=sys.stderr)
        sys.exit(1)
