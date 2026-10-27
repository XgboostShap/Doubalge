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


def diarise_pyannote(wav: str, token: str, n_perso: int | None):
    print("[diarisation] chargement de pyannote (1-2 min la première fois)...")
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        sys.exit("[erreur] pyannote.audio requis : pip install pyannote.audio")
    try:
        pipe = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", token=token)
    except TypeError:  # anciennes versions
        pipe = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=token)
    except Exception as ex:
        sys.exit(f"[erreur] pyannote indisponible : {str(ex)[:300]}\n"
                  "Vérifie : token valide + conditions acceptées sur les 3 repos "
                  "(speaker-diarization-3.1, segmentation-3.0, "
                  "speaker-diarization-community-1).")
    print("[diarisation] analyse en cours (1-3 min sur CPU)...")
    try:
        if n_perso and n_perso > 0:
            resultat = pipe(wav, num_speakers=n_perso)
        else:
            resultat = pipe(wav)
    except TypeError:
        resultat = pipe(wav)
    tours = extraire_tours(resultat)
    evenements = []
    ordre = {}
    for debut, fin, label in tours:
        if label not in ordre:
            ordre[label] = len(ordre)   # couleur stable par ordre d'apparition
        evenements.append({"start": round(debut, 2), "end": round(fin, 2),
                           "speaker": ordre[label]})
    fus = []
    for ev in evenements:
        if fus and fus[-1]["speaker"] == ev["speaker"] and \
                ev["start"] - fus[-1]["end"] < 0.30:
            fus[-1]["end"] = ev["end"]
        else:
            fus.append(ev)
    return fus


