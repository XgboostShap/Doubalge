"""Séparation expérimentale : fond continu, masques sur les dialogues seuls."""
from pathlib import Path
import os
import subprocess
import sys
from commun import FFMPEG


def prepare_stems(src, folder, device='cpu'):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'dialogue.wav').exists() and (folder / 'fond.wav').exists():
        return
    print('Séparation Demucs expérimentale ; des restes de voix peuvent subsister.', flush=True)
    args = [sys.executable, '-m', 'demucs', '-n', 'htdemucs', '--two-stems', 'vocals',
            '-d', device, '-o', str(folder / 'stems'), str(src)]
    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError:
        if device == 'cpu':
            raise
        print('Demucs GPU indisponible : repli CPU.', flush=True)
        args[args.index('-d') + 1] = 'cpu'
        subprocess.run(args, check=True)
    import shutil
    stem = folder / 'stems' / 'htdemucs' / Path(src).stem
    for name, target in [('vocals.wav', 'dialogue.wav'), ('no_vocals.wav', 'fond.wav')]:
        shutil.copyfile(stem / name, folder / (target + '.tmp'))
        os.replace(folder / (target + '.tmp'), folder / target)


def dialogue_mask(intervals, selected, mode, duration, rate):
    import numpy as np
    keep = np.zeros(int(duration * rate) + 1, dtype=bool)
    remove = np.zeros_like(keep)
    for row in intervals:
        # Une attribution inconnue est retirée par prudence dans les modes partiels.
        known = row['character'] is not None
        kept = known and ((row['character'] != selected) if mode == 'play_one' else (row['character'] == selected))
        a, b = max(0, int(row['start'] * rate)), min(len(keep), int(row['end'] * rate))
        (keep if kept else remove)[a:b] = True
    return keep & ~remove


def prepare_audio(folder, project, edit, mode, voice):
    if mode == 'silent':
        return None
    import numpy as np
    import soundfile as sf
    dialogue, rate = sf.read(folder / 'duo-cache/dialogue.wav', always_2d=True, dtype='float32')
    background, background_rate = sf.read(folder / 'duo-cache/fond.wav', always_2d=True, dtype='float32')
    if rate != background_rate or dialogue.shape != background.shape:
        raise ValueError('Pistes séparées incompatibles')
    mask = dialogue_mask(edit['intervals'], voice, mode, len(dialogue) / rate, rate)[:len(dialogue)]
    mixed = background + dialogue * mask[:, None]
    # Aucune coupure temporelle sur le fond.
    peak = float(np.max(np.abs(mixed))) if mixed.size else 1
    mixed /= max(1., peak)
    target = folder / 'duo-cache/impro.wav'
    sf.write(target, mixed, rate, subtype='PCM_16')
    return target
