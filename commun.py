# DoublageBasic v6 — module commun
# Fait partie du projet DoublageBasic (voir doublage_basic.py).
"""Constantes et utilitaires partagés (ffmpeg, couleurs, temps)."""
from __future__ import annotations

import re
import subprocess
import sys

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG = "ffmpeg"


COULEURS = [(0xE7, 0x4C, 0x3C), (0x2E, 0xCC, 0x71), (0x34, 0x98, 0xDB),
            (0x9B, 0x59, 0xB6), (0xF1, 0xC4, 0x0F), (0xE6, 0x7E, 0x22)]
PALE = 0.35                 # intensité du repère permanent
AVANCE_PAROLE_DEFAUT = 1.5  # s d'anticipation des pastilles personnages
AVANCE_PLAN_DEFAUT = 0.5    # s d'anticipation de la pastille changement de plan
PLAN_RGB = (0xFF, 0xFF, 0xFF)  # blanc pour la pastille "changement de plan"

def est_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def parse_temps(s: str) -> float:
    """Accepte '90', '90.5', '1:30', '1:30.5', '1:02:03'."""
    s = s.strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) > 3:
            sys.exit(f"[erreur] temps invalide : {s!r}")
        try:
            return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))
        except ValueError:
            sys.exit(f"[erreur] temps invalide : {s!r}")
    try:
        return float(s)
    except ValueError:
        sys.exit(f"[erreur] temps invalide : {s!r}")


def duree_et_taille(path: str):
    r = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        sys.exit("[erreur] durée illisible")
    h, mi, s = m.groups()
    duree = int(h) * 3600 + int(mi) * 60 + float(s)
    m2 = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r.stderr)
    w, hpx = (int(m2.group(1)), int(m2.group(2))) if m2 else (640, 480)
    return duree, w, hpx


def bip_fin():
    """Bip sonore de fin d'exécution (Colab : son dans le navigateur)."""
    try:
        import numpy as np
        from IPython.display import Audio, display
        sr = 44100
        t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
        display(Audio(np.sin(2 * np.pi * 880 * t) * 0.4, rate=sr, autoplay=True))
    except Exception:
        pass  # hors notebook : pas de bip, pas d'erreur


