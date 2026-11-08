# DoublageBasic v6 — module diarisation
# Fait partie du projet DoublageBasic (voir doublage_basic.py).
"""Étage 2 : diarisation pyannote — qui parle, quand (sans visage)."""
from __future__ import annotations

import os
import sys


def verifie_token():
    token = (os.environ.get("HF_TOKEN") or os.environ.get("PYANNOTE_TOKEN")
             or "").strip()
    PLACEHOLDERS = {"hf_colle_ton_token_ici", "hf_ton_vrai_token", "hf_colle",
                   "hf_ici", "hf_xxxxxxxxxxxx", "hf_...", "hf_ton_token"}
    if not token:
        sys.exit(
            "[erreur] pas de token HuggingFace.\n"
            "  1. Compte gratuit : https://huggingface.co\n"
            "  2. Accepter les conditions sur : speaker-diarization-3.1,\n"
            "     segmentation-3.0 ET speaker-diarization-community-1\n"
            "  3. Token 'Read' : https://huggingface.co/settings/tokens\n"
            "  4. Dans Colab, cellule au-dessus : os.environ['HF_TOKEN'] = 'hf_...'"
        )
    if token.lower() in PLACEHOLDERS or not token.startswith("hf_"):
        sys.exit("[erreur] le token HF ressemble à un placeholder non remplacé\n"
                 "(ou ne commence pas par 'hf_'). Colle ton VRAI token dans :\n"
                 "  os.environ['HF_TOKEN'] = 'hf_...'")
    return token


def extraire_tours(resultat):
    """Renvoie une liste de tuples (debut, fin, locuteur), compatible avec
    toutes les versions de pyannote :
    - anciennes (<= 3.x) : Annotation.itertracks -> (turn, track, label)
    - nouvelles (4.x) : DiarizeOutput.speaker_diarization -> (turn, speaker)"""
    if hasattr(resultat, "itertracks"):
        return [(t.start, t.end, label)
                for t, _, label in resultat.itertracks(yield_label=True)]
    for attr in ("speaker_diarization", "exclusive_speaker_diarization"):
        if hasattr(resultat, attr):
            return [(t.start, t.end, speaker)
                    for t, speaker in getattr(resultat, attr)]
    if hasattr(resultat, "annotation") and hasattr(resultat.annotation, "itertracks"):
        return [(t.start, t.end, label)
                for t, _, label in resultat.annotation.itertracks(yield_label=True)]
    sys.exit(f"[erreur] format de résultat pyannote non reconnu "
             f"(type {type(resultat).__name__}). Merci d'envoyer ce message "
             "pour adaptation du script.")


def diarise_pyannote(wav: str, token: str | None, n_perso: int | None, device=None):
    import torch
    import soundfile as sf
    from pyannote.audio import Pipeline
    from pyannote.audio.core.task import Problem, Resolution, Specifications
    torch.set_num_threads(min(os.cpu_count() or 1, 4))
    samples, rate = sf.read(wav, dtype='float32', always_2d=True)
    audio = {'waveform': torch.from_numpy(samples.T.copy()).mean(dim=0, keepdim=True), 'sample_rate': rate}
    print('[diarisation] chargement du modèle audio 3.1…', flush=True)
    with torch.serialization.safe_globals([torch.torch_version.TorchVersion, Problem, Resolution, Specifications]):
        pipe = Pipeline.from_pretrained('pyannote/speaker-diarization-3.1', use_auth_token=token)
        if pipe is None:
            raise RuntimeError('Modèle inaccessible : vérifier le jeton et les conditions Hugging Face')
        pipe.to(torch.device(device or 'cpu'))
        result = pipe(audio, **({'num_speakers': n_perso} if n_perso else {}))
    tours = sorted(extraire_tours(result))
    order = {}
    return [{'start': float(start), 'end': float(end), 'speaker': order.setdefault(label, len(order)),
             'label': str(label)} for start, end, label in tours if end > start]
