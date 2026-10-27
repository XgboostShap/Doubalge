# DoublageBasic v6 — module validation
# Fait partie du projet DoublageBasic (voir doublage_basic.py).
"""Étage 5 : validation utilisateur — photos visages + extraits voix + cellule Colab."""
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

from commun import FFMPEG


def extraits_validation(src, events, levres, args, w, h):
    """Prépare l'étape de validation. Écrit :
       val_visage_XX.jpg = photo de CHAQUE visage reconnu (pour voir le
                           nombre de personnages détectés à l'image)
       val_voix_XX.jpg   = photo du visage attribué à la voix XX
       val_voix_XX.wav   = extrait audio de sa réplique la plus longue
    et génère cellule_validation.py à exécuter dans Colab :
       1. section VISAGES RECONNUS (tous, avec position écran + voix liée)
       2. section VOIX (photo + extrait audio par perso)
       3. question sur les fusions."""
    attrib = levres.get("attribution") if levres else None
    if attrib:  # clés JSON -> entiers (le JSON les transforme en chaînes)
        attrib = {int(k): v for k, v in attrib.items()}
    photos = {v["id"]: v for v in (levres or {}).get("visages", [])}
    attrib_inverse = {}
    if attrib:
        for sp, fv in attrib.items():
            if fv is not None:
                attrib_inverse[fv] = sp

    # tableau des visages pour la cellule (positions en % de l'écran)
    tab_visages = [{"id": v["id"],
                    "cx": round(v["cx"] / max(w, 1) * 100),
                    "cy": round(v["cy"] / max(h, 1) * 100),
                    "voix": attrib_inverse.get(v["id"])}
                   for v in photos.values() if v.get("photo")]

    # la cellule est écrite EN PREMIER : elle s'affiche même si un
    # extrait audio ou une photo manque ensuite (elle teste les fichiers)
    Path("cellule_validation.py").write_text(f"""# CELLULE DE VALIDATION — exécuter telle quelle dans Colab
from IPython.display import Image, Audio, display
import os
url = {args.video!r}
tl = {args.timeline!r}
persos = {sorted({e["speaker"] for e in events})}
visages = {tab_visages}
print(f"==== VISAGES RECONNUS : {{len(visages)}} ====")
for v in visages:
    qui = f"voix {{v['voix']}}" if v["voix"] is not None else "AUCUNE voix"
    print(f"visage {{v['id']}} — {{qui}} — vu vers "
          f"{{v['cx']}}% / {{v['cy']}}% de l'écran")
    display(Image(f"val_visage_{{v['id']}}.jpg"))
print(f"\\n==== VOIX DÉTECTÉES : {{len(persos)}} ====")
print("Une voix par perso : photo du visage + extrait audio.\\n")
for sp in persos:
    print(f"=== PERSO {{sp}} ===")
    if os.path.exists(f"val_voix_{{sp}}.jpg"):
        display(Image(f"val_voix_{{sp}}.jpg"))
    else:
        print("   (pas de photo de visage attribuée)")
    if os.path.exists(f"val_voix_{{sp}}.wav"):
        display(Audio(f"val_voix_{{sp}}.wav", autoplay=False))
    else:
        print("   (pas d'extrait audio disponible)")
print("Si deux numéros sont la MÊME personne, note-les.")
rep = input("Fusions à appliquer, ex '0,1' ou '0,1;2,3' — Entrée si rien : ").strip()
if rep:
    opts = " ".join(f"--fusion {{g.strip()}}" for g in rep.split(";") if g.strip())
    print(f"\\nCommande de rendu à lancer :\\n"
          f"!python doublage_basic.py \\"{{url}}\\" "
          f"--timeline {{tl}} {{opts}} -o tous.mp4\\n")
else:
    print("\\nBase validée sans fusion. Lance le rendu normal.\\n")
""")
    n_voix = len({e["speaker"] for e in events}) if events else 0
    print(f"[valider] cellule_validation.py écrit "
          f"({len(tab_visages)} visage(s) reconnu(s), {n_voix} voix)")

    for v in photos.values():
        if v.get("photo"):
            Path(f"val_visage_{v['id']}.jpg").write_bytes(
                base64.b64decode(v["photo"]))

    for sp in sorted({e["speaker"] for e in events}):
        nom = f"val_voix_{sp}"
        vis = attrib.get(sp) if attrib else None
        photo = photos.get(vis, {}).get("photo") if vis is not None else None
        if photo:
            Path(f"{nom}.jpg").write_bytes(base64.b64decode(photo))
        else:
            print(f"[valider] pas de photo pour la voix {sp} "
                  f"(visage non attribué)")
        repl = max((e for e in events if e["speaker"] == sp),
                   key=lambda e: e["end"] - e["start"])
        # on saute les 0,30 s de début (la frontière pyannote laisse souvent
        # traîner la fin du locuteur précédent) et on limite à 4 s
        t0 = repl["start"] + 0.30
        dur = min(repl["end"] - t0, 4.0)
        if dur <= 0.2:
            t0, dur = repl["start"], min(repl["end"] - repl["start"], 4.0)
        r = subprocess.run([FFMPEG, "-y", "-ss", f"{t0:.3f}",
                            "-t", f"{dur:.3f}", "-i", src,
                            "-vn", "-ac", "1", "-ar", "16000", f"{nom}.wav"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[valider] ⚠ extraction audio de la voix {sp} échouée "
                  f"(la validation continue sans)")
        else:
            print(f"[valider] {nom}.wav ({dur:.1f}s) "
                  f"{'+ photo' if photo else '(sans photo)'}")

    # (la cellule est déjà écrite plus haut, avant les extractions)


