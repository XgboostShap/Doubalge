"""Séparation locale dialogues/fond avec le modèle officiel TorchAudio HDemucs."""
from __future__ import annotations

import json
import os
from pathlib import Path

MODEL = 'torchaudio/HDEMUCS_HIGH_MUSDB_PLUS'
SAMPLE_RATE = 44100


def reconstruire_dialogue(waveform, model, device, log=print, segment_seconds=6):
    import torch
    segment = int(segment_seconds * SAMPLE_RATE)
    hop = segment // 2
    length = waveform.shape[-1]
    padded = torch.nn.functional.pad(waveform, (hop, hop))
    output = torch.zeros_like(padded)
    weights = torch.zeros(padded.shape[-1])
    window = torch.hann_window(segment, periodic=False)
    starts = list(range(0, padded.shape[-1] - hop, hop))
    vocal_index = model.sources.index('vocals')
    with torch.inference_mode():
        for index, start in enumerate(starts):
            count = min(segment, padded.shape[-1] - start)
            chunk = torch.nn.functional.pad(padded[:, start:start + count], (0, segment - count))
            prediction = model(chunk.unsqueeze(0).to(device))[0, vocal_index, :, :count].cpu()
            output[:, start:start + count] += prediction * window[:count]
            weights[start:start + count] += window[:count]
            log(f'[audio] Séparation voix/fond : {index + 1}/{len(starts)} blocs.', flush=True)
    return (output / weights.clamp_min(1e-8))[:, hop:hop + length]


def separer(video: Path, travail: Path, duration: float, source_hash: str, ffmpeg,
            cpu=False, log=print):
    from export_html import ecrire_json
    dialogue_file, background_file = travail / 'dialogue.m4a', travail / 'ambiance.m4a'
    manifest = travail / 'pistes-audio.json'
    signature = {'source_sha256': source_hash, 'model': MODEL, 'version': 1, 'duration': duration}
    if manifest.exists() and dialogue_file.exists() and background_file.exists():
        if json.loads(manifest.read_text(encoding='utf-8')) == signature:
            log('[audio] Pistes séparées existantes réutilisées.', flush=True)
            return dialogue_file, background_file

    import torch
    import torchaudio
    import soundfile as sf
    torch.set_num_threads(min(os.cpu_count() or 1, 4))
    device = torch.device('cuda' if not cpu and torch.cuda.is_available() else 'cpu')
    log(f'[audio] Préparation du modèle de séparation sur {device}. Téléchargement d’environ 320 Mo si absent du cache.', flush=True)
    bundle = torchaudio.pipelines.HDEMUCS_HIGH_MUSDB_PLUS
    model = bundle.get_model().to(device).eval()
    wav = travail / 'mix-stereo.wav'
    ffmpeg(['-i', str(video), '-vn', '-t', str(duration), '-ac', '2', '-ar', str(SAMPLE_RATE),
            '-c:a', 'pcm_f32le', str(wav)])
    samples, rate = sf.read(wav, dtype='float32', always_2d=True)
    if rate != SAMPLE_RATE or samples.shape[1] != 2:
        raise ValueError('La séparation nécessite le mélange stéréo à 44,1 kHz.')
    mixture = torch.from_numpy(samples.T.copy())
    dialogue = reconstruire_dialogue(mixture, model, device, log)
    background = mixture - dialogue
    # Même facteur sur les deux pistes : leur somme reste le mélange d’origine à un gain constant.
    scale = max(1.0, float(dialogue.abs().max()), float(background.abs().max()))
    for name, audio, destination in [('dialogue', dialogue, dialogue_file), ('ambiance', background, background_file)]:
        stem_wav = travail / (name + '.wav')
        sf.write(stem_wav, (audio / scale).T.numpy(), rate, subtype='FLOAT')
        temporary = destination.with_name(destination.stem + '.partial.m4a')
        ffmpeg(['-i', str(stem_wav), '-t', str(duration), '-ac', '1', '-ar', '24000',
                '-c:a', 'aac', '-b:a', '96k', str(temporary)])
        temporary.replace(destination)
    ecrire_json(manifest, signature)
    return dialogue_file, background_file
