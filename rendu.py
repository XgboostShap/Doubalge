# DoublageBasic v6 — module rendu
# Fait partie du projet DoublageBasic (voir doublage_basic.py).
"""Étage 6 : détection des plans + rendu ffmpeg (pastilles, pastille plan, filtre --voix)."""
from __future__ import annotations

import re
import subprocess
import sys

from commun import COULEURS, FFMPEG, PALE, PLAN_RGB


def _plans_au_seuil(src: str, seuil: float):
    cmd = [FFMPEG, "-i", src,
           "-vf", f"select='gt(scene,{seuil})',showinfo",
           "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    times = [float(m) for m in
             re.findall(r"pts_time:([0-9]+\.?[0-9]*)", r.stderr)]
    return [round(t, 2) for t in times if t > 0.5]


def detecte_plans(src: str, seuil: float = 0.25):
    print(f"[plans] détection des changements de plan (seuil {seuil})...")
    cuts = _plans_au_seuil(src, seuil)
    if cuts:
        print(f"[plans] {len(cuts)} changement(s) de plan")
        return cuts
    for s in (0.15, 0.10):
        if s >= seuil:
            continue
        print(f"[plans] aucun cut au seuil {seuil}, réessai à {s}...")
        cuts = _plans_au_seuil(src, s)
        if cuts:
            print(f"[plans] {len(cuts)} changement(s) de plan (seuil {s})")
            return cuts
    print("[plans] aucun changement de plan détecté : "
          "la vidéo semble tenue en plan fixe. "
          "La pastille blanche n'apparaîtra pas.")
    return []


def _hex(rgb, k):
    return "0x" + "".join(f"{int(c * k):02X}" for c in rgb)


def filtre_pastilles(events, w, h, n_perso, avance: float = 0.0,
                     taille=36, marge=20):
    """À DROITE : pile complète de pastilles personnages (toutes affichées).
    Allumage AVANCE secondes avant la réplique, extinction à sa fin."""
    parts = []
    for spk in range(n_perso):
        x, y = w - marge - taille, h - marge - (spk + 1) * taille - spk * 8
        rgb = COULEURS[spk % len(COULEURS)]
        parts.append(f"drawbox=x={x}:y={y}:w={taille}:h={taille}:"
                     f"color={_hex(rgb, PALE)}:t=fill")
        for ev in events:
            if ev["speaker"] != spk:
                continue
            t_on = max(0.0, ev["start"] - avance)
            t_off = ev["end"]
            parts.append(f"drawbox=x={x}:y={y}:w={taille}:h={taille}:"
                         f"color={_hex(rgb, 1.0)}:t=fill:"
                         f"enable='between(t,{t_on:.2f},{t_off:.2f})'")
    return parts


def filtre_pastille_plan(cuts, w, h, avance: float = 0.0,
                         taille=36, marge=20):
    if not cuts:
        return []
    x, y = marge, h - marge - taille   # bas-gauche, symétrique de la pile
    parts = [f"drawbox=x={x}:y={y}:w={taille}:h={taille}:"
             f"color={_hex(PLAN_RGB, PALE)}:t=fill"]
    for t_cut in cuts:
        t_on = max(0.0, t_cut - avance)
        parts.append(f"drawbox=x={x}:y={y}:w={taille}:h={taille}:"
                     f"color={_hex(PLAN_RGB, 1.0)}:t=fill:"
                     f"enable='between(t,{t_on:.2f},{t_cut:.2f})'")
    return parts


def filtre_audio_voix(events, n_perso, voix: int):
    """Filtre AUDIO : coupe le son pendant les répliques de tous les
    personnages SAUF `voix` (volume=0). Les silences entre répliques
    (musique, ambiance) restent intacts."""
    if voix < 0 or voix >= n_perso:
        sys.exit(f"[erreur] --voix {voix} : ce personnage n'existe pas "
                 f"(personnages valides : 0 à {n_perso - 1})")
    parts = []
    for ev in events:
        if ev["speaker"] == voix:
            continue
        parts.append(f"volume=0:enable='between(t,{ev['start']:.2f},{ev['end']:.2f})'")
    return parts


def rendu(src, out, vf, duree, af=None):
    """Rendu une passe. Sans filtre audio : son copié tel quel.
    Avec --voix : audio réencodé en AAC (obligatoire, le son est modifié)."""
    cmd = [FFMPEG, "-y", "-i", src, "-vf", vf]
    if af:
        cmd += ["-af", ",".join(af),
                "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "copy"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-t", f"{duree:.3f}", "-pix_fmt", "yuv420p", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"[erreur] rendu ffmpeg:\n{r.stderr[-1200:]}")


