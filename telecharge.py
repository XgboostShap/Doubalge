# DoublageBasic v6 — module telecharge
# Fait partie du projet DoublageBasic (voir doublage_basic.py).
"""Étage 1 : source — YouTube/yt-dlp, découpe --debut/--fin, extraction audio."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from commun import FFMPEG


def telecharge(url: str, workdir: str, debut=None, fin=None) -> str:
    print("[source] téléchargement YouTube...")
    dst = os.path.join(workdir, "source.mp4")
    max_h = 720
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist",
           "--ffmpeg-location", FFMPEG,
           "-f", f"bv*[height<={max_h}][ext=mp4]+ba[ext=m4a]/"
                 f"b[height<={max_h}][ext=mp4]/"
                 f"bv*[height<={max_h}]+ba/b[height<={max_h}]/b"]
    if debut is not None:
        fin_s = "" if fin is None else f"-{fin:.3f}"
        cmd += ["--download-sections", f"*{debut:.3f}{fin_s}"]
    cmd += ["-o", dst, url]
    r = subprocess.run(cmd, text=True)
    if r.returncode != 0 or not Path(dst).exists():
        sys.exit("[erreur] échec du téléchargement YouTube")
    print(f"[source] ok: {dst}")
    return dst


def coupe_extrait(src: str, workdir: str, debut: float, fin: float) -> str:
    """Découpe [debut, fin] d'un fichier local (réencodage pour couper
    au bon endroit, pas au keyframe près). Rend le chemin de l'extrait."""
    dst = os.path.join(workdir, "extrait.mp4")
    print(f"[extrait] découpe {debut:.1f}s -> {fin:.1f}s...")
    cmd = [FFMPEG, "-y", "-ss", f"{debut:.3f}", "-i", src,
           "-t", f"{fin - debut:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-c:a", "aac", "-b:a", "192k", dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"[erreur] découpe ffmpeg:\n{r.stderr[-1200:]}")
    print(f"[extrait] ok: {dst}")
    return dst


def extrait_audio(video: str, wav: str):
    subprocess.run([FFMPEG, "-y", "-i", video, "-vn", "-ac", "1",
                    "-ar", "16000", "-c:a", "pcm_s16le", wav],
                   check=True, capture_output=True)


