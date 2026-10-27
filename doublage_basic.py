#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DoublageBasic v6 — version modulaire.

Étages (1 fichier = 1 étage, testable isolément) :
  commun.py        constantes, ffmpeg, temps, bip
  telecharge.py    source YouTube/fichier, --debut/--fin, audio 16 kHz
  diarisation.py   pyannote : qui parle, quand
  levres.py        visages suivis, mouvement des lèvres
  fusion.py        attribution voix<->visage, fusions --fusion
  validation.py    --valider : photos + extraits voix + cellule Colab
  rendu.py         détection des plans + rendu ffmpeg (pastilles, --voix)
  doublage_basic.py  CLI + orchestration (ce fichier)

Tous les fichiers doivent être dans le MÊME dossier.
Usage et options : python doublage_basic.py --help
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from commun import (AVANCE_PAROLE_DEFAUT, AVANCE_PLAN_DEFAUT, bip_fin,
                    duree_et_taille, est_url, parse_temps)
from diarisation import diarise_pyannote, verifie_token
from fusion import fusion_levres, fusionne_voix
from levres import passe_levres
from rendu import (detecte_plans, filtre_audio_voix, filtre_pastille_plan,
                   filtre_pastilles, rendu)
from telecharge import coupe_extrait, extrait_audio, telecharge
from validation import extraits_validation


def main():
    ap = argparse.ArgumentParser(
        description="DoublageBasic v5 : pyannote + lèvres + validation + --voix")
    ap.add_argument("video", help="Vidéo locale ou URL YouTube")
    ap.add_argument("-o", "--out", help="Sortie (défaut: <nom>_basic.mp4)")
    ap.add_argument("--personnages", type=int, default=0,
                    help="0 = détection auto du nombre de personnages")
    ap.add_argument("--avance", type=float, default=AVANCE_PAROLE_DEFAUT,
                    help=f"Anticipation des pastilles personnages, en s "
                         f"(défaut: {AVANCE_PAROLE_DEFAUT}s)")
    ap.add_argument("--avance-plan", type=float, default=AVANCE_PLAN_DEFAUT,
                    help=f"Anticipation de la pastille changement de plan, en s "
                         f"(défaut: {AVANCE_PLAN_DEFAUT}s, indépendante de --avance)")
    ap.add_argument("--seuil-plan", type=float, default=0.25,
                    help="Sensibilité détection de plan (défaut 0.25)")
    ap.add_argument("--voix", type=int, default=None,
                    help="Son audible UNIQUEMENT pour le perso N (les autres "
                         "répliques à volume 0, musique intacte)")
    ap.add_argument("--debut", type=parse_temps, default=None,
                    help="Début de l'extrait en secondes ou mm:ss (défaut: 0)")
    ap.add_argument("--fin", type=parse_temps, default=None,
                    help="Fin de l'extrait en secondes ou mm:ss (défaut: fin "
                         "de la vidéo)")
    ap.add_argument("--rapport", action="store_true", help="Écrire rapport_basic.txt")
    ap.add_argument("--sans-levres", action="store_true",
                    help="Sauter la passe lèvres (fusion audio/visages)")
    ap.add_argument("--pas-levres", type=int, default=3,
                    help="Échantillonnage passe lèvres : 1 image sur N "
                         "(défaut 3 ; augmenter si trop lent)")
    ap.add_argument("--seuil-levres", type=float, default=1.35,
                    help="Mouvement de bouche minimum (x le repos) pour "
                         "déclarer qu'un visage parle (défaut 1.35)")
    ap.add_argument("--fusion-visages", type=float, default=0.10,
                    help="Regrouper les fragments de visage (un par plan) "
                         "dont la position moyenne est proche, en fraction "
                         "de l'écran (défaut 0.10 ; 0 = désactivé)")
    ap.add_argument("--valider", action="store_true",
                    help="Étape de validation : photo de chaque visage + "
                         "audio de chaque voix + cellule_validation.py à "
                         "exécuter dans Colab")
    ap.add_argument("--fusion", action="append", default=[],
                    metavar="A,B,C",
                    help="Déclarer que ces voix sont la MÊME personne "
                         "(répétable : --fusion 0,1 --fusion 2,3)")
    ap.add_argument("--timeline", help="Sauver/charger les événements en JSON")
    args = ap.parse_args()

    if not args.video.strip():
        sys.exit("[erreur] aucune vidéo fournie")

    if args.debut is not None and args.fin is not None and args.fin <= args.debut:
        sys.exit("[erreur] --fin doit être après --debut")
    if (args.debut is not None or args.fin is not None) \
            and args.timeline and Path(args.timeline).exists():
        sys.exit("[erreur] --timeline existe déjà mais --debut/--fin change "
                 "les timings. Supprime le .json (ou renomme-le) pour "
                 "réanalyser l'extrait.")

    tmp = tempfile.TemporaryDirectory() if (est_url(args.video)
                                           or args.debut is not None
                                           or args.fin is not None) else None
    if tmp and est_url(args.video):
        src = telecharge(args.video, tmp.name, debut=args.debut, fin=args.fin)
        coupe = False
    else:
        src = args.video
        coupe = args.debut is not None or args.fin is not None
    if coupe:
        d, f = args.debut or 0.0, args.fin
        if f is None:
            dur_tot, _, _ = duree_et_taille(src)
            f = dur_tot
            print(f"[extrait] --fin omis : fin de la vidéo ({f:.1f}s)")
        src = coupe_extrait(src, tmp.name, d, f)
    base = Path(src).stem
    out = args.out or f"{base}_basic.mp4"

    duree, w, h = duree_et_taille(src)
    print(f"[source] {w}x{h}, {duree:.1f}s")

    cuts = []
    if args.timeline and Path(args.timeline).exists():
        data = json.loads(Path(args.timeline).read_text())
        tl_src = data.get("source")
        if tl_src is not None and tl_src != args.video:
            sys.exit(
                f"[erreur] {args.timeline} a été créée pour une AUTRE vidéo :\n"
                f"  timeline : {tl_src}\n"
                f"  demandé   : {args.video}\n"
                f"Les timings ne correspondraient pas. Supprime le .json\n"
                f"(ou utilise un autre nom --timeline) pour réanalyser :\n"
                f"  !rm {args.timeline}")
        if tl_src is None:
            print("[timeline] attention : .json sans champ 'source' (ancien "
                  "format) — chargé sans vérification de la vidéo")
        events = data["events"]
        cuts = data.get("cuts", [])
        print(f"[timeline] chargée : {len(events)} événements, {len(cuts)} plans")
    else:
        wav = os.path.join(tmp.name if tmp else tempfile.mkdtemp(), "audio.wav")
        extrait_audio(src, wav)
        print("[audio] extrait 16 kHz mono")

        token = verifie_token()
        events = diarise_pyannote(wav, token, args.personnages)

        tot = sum(e["end"] - e["start"] for e in events)
        rep = {p: sum(1 for e in events if e["speaker"] == p)
               for p in sorted({e["speaker"] for e in events})}
        print(f"[diarisation] {len(events)} réplique(s), {tot:.1f}s de parole, "
              f"{len(rep)} personnage(s) : {rep}")

        cuts = detecte_plans(src, args.seuil_plan)

        levres = None
        if not args.sans_levres and events:
            print(f"[lèvres] passe visuelle (1 image sur {args.pas_levres})...")
            visages, energies, presence, basem = passe_levres(
                src, events, cuts, pas=args.pas_levres,
                fusion_pos=args.fusion_visages)
            attribution, gagnants, alertes = fusion_levres(
                events, visages, energies, presence, basem,
                seuil=args.seuil_levres)
            levres = {"visages": visages, "energies": energies,
                      "presence": presence, "base": basem,
                      "attribution": attribution, "gagnants": gagnants,
                      "alertes": alertes}
            n_attr = sum(1 for v in attribution.values() if v is not None)
            print(f"[lèvres] {len(visages)} visage(s) suivi(s) ; "
                  f"{n_attr} voix sur {len(attribution)} attribuées à un visage")
            for a in alertes:
                print(f"[lèvres] ⚠ {a}")

        if args.rapport:
            lignes = [f"RAPPORT DoublageBasic v4 - {len(events)} répliques, "
                      f"{len(cuts)} changements de plan", "=" * 50]
            for i, ev in enumerate(events):
                lignes.append(f"{i+1:3d}. [{ev['start']:7.2f}s -> {ev['end']:7.2f}s] "
                              f"perso {ev['speaker']}")
            lignes.append("-" * 50)
            for i, t in enumerate(cuts):
                lignes.append(f"plan {i+1:3d} à {t:7.2f}s")
            lignes += ["=" * 50, f"Personnages (audio): {len(rep)}",
                       f"Répliques par perso: {rep}"]
            if levres:
                lignes += ["", "FUSION AUDIO + LÈVRES", "-" * 50]
                vus = {v["id"]: v for v in levres["visages"]}
                for sp, vf_ in sorted(levres["attribution"].items(),
                                      key=lambda kv: kv[0]):
                    n = rep.get(sp, 0)
                    if vf_ is None:
                        lignes.append(f"voix {sp} : PAS de visage "
                                      f"({n} répliques) — à vérifier")
                    else:
                        v = vus.get(vf_, {})
                        cx, cy = v.get("cx", 0), v.get("cy", 0)
                        lignes.append(
                            f"voix {sp} = visage n°{vf_} "
                            f"({n} répliques, vu vers "
                            f"{cx / w * 100:.0f}% largeur / "
                            f"{cy / h * 100:.0f}% hauteur de l'écran)")
                if levres["alertes"]:
                    lignes += ["", "ALERTES", "-" * 50]
                    lignes += [f"⚠ {a}" for a in levres["alertes"]]
            Path("rapport_basic.txt").write_text("\n".join(lignes) + "\n")
            print("[rapport] rapport_basic.txt")

        if args.timeline:
            Path(args.timeline).write_text(json.dumps(
                {"events": events, "cuts": cuts, "duration": duree,
                 "source": args.video, "levres": levres}, indent=2))
            print(f"[timeline] écrite : {args.timeline}")

    n_perso = len({e["speaker"] for e in events}) if events else 1

    if args.fusion:
        groupes = [[int(x) for x in g.split(",") if x.strip() != ""]
                   for g in args.fusion]
        mapping = fusionne_voix(events, groupes)
        n_perso = len({e["speaker"] for e in events}) if events else 1
        print(f"[fusion] mapping voix -> perso : {mapping} "
              f"({n_perso} perso après fusion)")

    if args.valider:
        levres = None
        if args.timeline and Path(args.timeline).exists():
            levres = json.loads(
                Path(args.timeline).read_text()).get("levres")
            if levres and "attribution" in levres:
                # le JSON transforme les clés entières en chaînes ("1") :
                # on les rend aux entiers pour retrouver les visages
                levres["attribution"] = {
                    int(k): v for k, v in levres["attribution"].items()}
            if levres and "base" in levres:
                levres["base"] = {
                    int(k): v for k, v in levres["base"].items()}
        if not levres:
            print("[valider] la timeline ne contient pas la passe lèvres — "
                  "relance l'analyse sans --sans-levres")
        extraits_validation(src, events, levres, args, w, h)
        print("[valider] exécute maintenant la cellule : %run cellule_validation.py")
        print("[valider] (ou copie-colle son contenu dans une cellule)")
        print("[valider] puis relance le rendu (normal, ou avec --fusion ...)")
        if args.out is None:
            bip_fin()
            return          # --valider seul : pas de rendu complet

    vf_parts = filtre_pastilles(events, w, h, n_perso, avance=args.avance)
    vf_parts += filtre_pastille_plan(cuts, w, h, avance=args.avance_plan)
    vf = ",".join(vf_parts)

    af = None
    if args.voix is not None:
        af = filtre_audio_voix(events, n_perso, args.voix)
        nb = sum(1 for e in events if e["speaker"] == args.voix)
        muets = sum(1 for e in events if e["speaker"] != args.voix)
        print(f"[voix] son gardé pour le perso {args.voix} "
              f"({nb} réplique(s) audibles), {muets} réplique(s) muette(s) ; "
              f"musique/ambiance intactes")

    print(f"[rendu] {n_perso} perso (avance {args.avance}s) + "
          f"{len(cuts)} plan(s) (avance {args.avance_plan}s), "
          f"{'son réencodé (perso ' + str(args.voix) + ' audible seul)' if af else 'son copié tel quel'}")
    rendu(src, out, vf, duree, af=af)
    if tmp:
        tmp.cleanup()
    print(f"[ok] {out}")
    bip_fin()


if __name__ == "__main__":
    main()
