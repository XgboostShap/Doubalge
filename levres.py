# DoublageBasic v6.1 — module levres
# Fait partie du projet DoublageBasic (voir doublage_basic.py).
"""Étage 3 : passe visuelle — visages suivis, mouvement des lèvres.

v6.1 — accéléré : détection à ~480 px de large (≈5-6× plus rapide sans
perdre le suivi), images non échantillonnées sautées sans décodage
complet (grab), progression affichée toutes les 20 s de vidéo.
"""
from __future__ import annotations

import base64
import sys


def passe_levres(src: str, events, cuts, pas: int = 3, fusion_pos: float = 0.10):
    """Passe visuelle. Pour chaque image échantillonnée (1 sur `pas`) :
      - détection des visages (cascade Haar d'OpenCV, préinstallé dans Colab),
        sur une image RÉDUITE à ~480 px de large (rapide) ;
      - suivi par proximité : un visage détecté près d'un visage connu garde
        son numéro (les profils ratés coupent le fil, il reprendra un n° neuf) ;
      - RESET complet du suivi à chaque changement de plan (un visage n'est
        pas le même d'un plan à l'autre, même s'il est au même endroit) ;
      - pour chaque visage détecté sur 2 images consécutives, mesure du
        mouvement de la zone bouche (moitié basse du visage, bande centrale).

    IMPORTANT : on ne devine JAMAIS qui parle par la présence à l'image —
    on mesure juste le mouvement des lèvres. C'est la fusion qui décide.

    Retourne (visages, energies, presence, base) :
      visages  : [{"id", "vues", "cx", "cy", "photo"}] — photo = meilleure
                 photo du visage (JPEG base64), pour l'étape --valider
      energies : {"{i_event}|{id}": somme mouvement bouche pendant l'event}
      presence : {"{i_event}|{id}": nb échantillons pendant l'event}
      base     : {id: mouvement moyen bouche HORS parole (référence repos)}
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        sys.exit("[erreur] passe lèvres : lecture impossible de la vidéo")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    n_tot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duree_tot = (n_tot / fps) if n_tot else None
    # ------------------------------------------------ v8 : choix du détecteur
    # MediaPipe (blazeface) : bien plus robuste que Haar sur les scènes
    # sombres et les visages de trois-quarts, rapide sur CPU.
    # Repli automatique sur Haar si MediaPIpe n'est pas installé.
    # v8.1 : les DEUX modèles blazeface (0 = plans rapprochés, visages
    # < 2 m ; 1 = visages plus lointains) — un visage qui remplit le cadre
    # est raté par le modèle lointain, d'où la fusion des deux.
    detecteurs = []
    cascade = None
    try:
        import mediapipe as mp
        for m in (0, 1):
            detecteurs.append(mp.solutions.face_detection.FaceDetection(
                model_selection=m, min_detection_confidence=0.35))
        print("[lèvres] détecteur : MediaPipe blazeface "
              "(modèles proche + loin fusionnés)")
    except Exception:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if cascade.empty():
            sys.exit("[erreur] ni MediaPipe ni cascade Haar disponible "
                     "(pip install mediapipe, ou OpenCV incomplet)")
        print("[lèvres] détecteur : Haar (MediaPipe absent — moins robuste)")

    def iou(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1, y1 = max(ax, bx), max(ay, by)
        x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = aw * ah + bw * bh - inter
        return inter / union if union > 0 else 0.0

    tri = sorted(enumerate(events), key=lambda kv: kv[1]["start"])

    def event_actif(t):
        for i, e in tri:
            if e["start"] - 0.2 <= t <= e["end"] + 0.2:
                return i
            if e["start"] - 0.2 > t:
                break
        return -1

    energies, presence, base_e, base_n = {}, {}, {}, {}
    tous, tracks = [], []
    di = 0
    prochain_log = 0.0
    while True:
        if di % pas == 0:
            ok, frame = cap.read()
            if not ok:
                break
            t = di / fps
            if any(abs(t - c) < pas / fps for c in cuts):
                tracks = []                  # nouveau plan : on repart à zéro
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h_img, w_img = gray.shape
            k = min(1.0, 480.0 / w_img)      # détection sur image réduite
            if k < 1.0:
                det = cv2.equalizeHist(cv2.resize(
                    gray, None, fx=k, fy=k, interpolation=cv2.INTER_AREA))
            else:
                det = cv2.equalizeHist(gray)
            dh, dw = det.shape
            if detecteurs:
                rects = []
                for dmod in detecteurs:
                    res_mp = dmod.process(
                        cv2.cvtColor(det, cv2.COLOR_GRAY2RGB))
                    if not res_mp.detections:
                        continue
                    for d in res_mp.detections:
                        b = d.location_data.relative_bounding_box
                        r = (int(max(0, b.xmin) * dw),
                             int(max(0, b.ymin) * dh),
                             int(b.width * dw),
                             int(b.height * dh))
                        if all(iou(r, o) < 0.4 for o in rects):
                            rects.append(r)      # doublon des 2 modèles écarté
            else:
                min_f = max(24, int(dw * 0.05))
                rects = cascade.detectMultiScale(det, 1.15, 6,
                                                minSize=(min_f, min_f))
            for (dx, dy, dw_, dh_) in rects:
                # coordonnées pleine résolution (suivi + photo)
                x, y = int(dx / k), int(dy / k)
                w, h = max(1, int(dw_ / k)), max(1, int(dh_ / k))
                cx, cy = x + w / 2, y + h / 2
                v, dmin = None, max(w, h) * 0.7
                for tr in tracks:
                    bx, by, bw, bh = tr["box"]
                    d = max(abs(cx - (bx + bw / 2)), abs(cy - (by + bh / 2)))
                    if d < dmin:
                        v, dmin = tr, d
                bouche = cv2.resize(
                    det[dy + int(dh_ * 0.58): dy + int(dh_ * 0.92),
                        dx + int(dw_ * 0.20): dx + int(dw_ * 0.80)],
                    (48, 24)).astype(np.float32)
                if v is None:
                    v = {"id": len(tous), "box": (x, y, w, h), "vues": 0,
                         "scx": 0.0, "scy": 0.0, "prec": None, "vu_a": t,
                         "photo": None, "photo_a": 0}
                    tous.append(v)
                    tracks.append(v)
                v.update(box=(x, y, w, h), vu_a=t)
                if w * h > v["photo_a"]:      # meilleure photo = plus grand cadre
                    ok_jpg, buf = cv2.imencode(
                        ".jpg", frame[max(0, y): y + h, max(0, x): x + w],
                        [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ok_jpg:
                        v["photo"] = base64.b64encode(buf).decode("ascii")
                        v["photo_a"] = w * h
                if v["prec"] is not None:
                    mv = float(np.mean(np.abs(bouche - v["prec"]))) / 255.0
                    ie = event_actif(t)
                    if ie >= 0:
                        kk = f"{ie}|{v['id']}"
                        energies[kk] = energies.get(kk, 0.0) + mv
                        presence[kk] = presence.get(kk, 0) + 1
                    else:
                        base_e[v["id"]] = base_e.get(v["id"], 0.0) + mv
                        base_n[v["id"]] = base_n.get(v["id"], 0) + 1
                v["prec"] = bouche
                v["vues"] += 1
                v["scx"] += cx
                v["scy"] += cy
            tracks = [tr for tr in tracks if t - tr["vu_a"] <= 1.5]
            if t >= prochain_log:            # progression visible
                pct = f" ({t / duree_tot * 100:.0f}%)" if duree_tot else ""
                print(f"[lèvres] {t:.0f}s de vidéo traités{pct}")
                prochain_log = t + 20.0
        else:
            if not cap.grab():               # image ignorée : pas de décodage
                break
        di += 1
    cap.release()

    visages = []
    for v in tous:
        if v["vues"] >= 3:
            visages.append({"id": v["id"], "vues": v["vues"],
                            "cx": v["scx"] / v["vues"],
                            "cy": v["scy"] / v["vues"],
                            "photo": v["photo"],
                            "photo_a": v["photo_a"]})

    # ------------------------------------------------ v7 : consolidation par position
    # Le suivi est remis à zéro à chaque changement de plan : dans un dialogue
    # en champ/contrechamp, la même personne repart avec un numéro neuf à
    # chaque plan. On regroupe les fragments dont la position moyenne à
    # l'écran est proche (fusion_pos, en fraction de l'écran) : les énergies,
    # présences et références repos sont fusionnées avec eux.
    n_fusionnes = 0
    if fusion_pos and fusion_pos > 0 and len(visages) > 1:
        w_ref = w_img if w_img else 1280
        h_ref = h_img if h_img else 720
        groupes = []
        for v in visages:
            place = False
            for g in groupes:
                gcx, gcy = g["scx"] / g["vues"], g["scy"] / g["vues"]
                if (abs(v["cx"] - gcx) <= fusion_pos * w_ref
                        and abs(v["cy"] - gcy) <= fusion_pos * h_ref):
                    g["ids"].append(v["id"])
                    g["vues"] += v["vues"]
                    g["scx"] += v["cx"] * v["vues"]
                    g["scy"] += v["cy"] * v["vues"]
                    if v["photo"] and v["photo_a"] > g.get("photo_a", 0):
                        g["photo"], g["photo_a"] = v["photo"], v["photo_a"]
                    place = True
                    break
            if not place:
                groupes.append({"ids": [v["id"]], "vues": v["vues"],
                                "scx": v["cx"] * v["vues"],
                                "scy": v["cy"] * v["vues"],
                                "photo": v["photo"], "photo_a": v["photo_a"]})
        n_fusionnes = len(visages) - len(groupes)
        remap = {}
        for g in groupes:
            for i in g["ids"]:
                remap[i] = g["ids"][0]
        n_ener, n_pres = {}, {}
        for k, val in energies.items():
            ev, fid = k.split("|")
            kk = f"{ev}|{remap.get(int(fid), int(fid))}"
            n_ener[kk] = n_ener.get(kk, 0.0) + val
        for k, val in presence.items():
            ev, fid = k.split("|")
            kk = f"{ev}|{remap.get(int(fid), int(fid))}"
            n_pres[kk] = n_pres.get(kk, 0) + val
        energies, presence = n_ener, n_pres
        nb_e, nb_n = {}, {}
        for fid, val in base_e.items():
            r = remap.get(fid, fid)
            nb_e[r] = nb_e.get(r, 0.0) + val
            nb_n[r] = nb_n.get(r, 0) + base_n[fid]
        base = {i: nb_e[i] / nb_n[i] for i in nb_n if nb_n[i] >= 3}
        visages = [{"id": g["ids"][0], "vues": g["vues"],
                    "cx": g["scx"] / g["vues"], "cy": g["scy"] / g["vues"],
                    "photo": g["photo"], "photo_a": g["photo_a"]}
                   for g in groupes]
    if n_fusionnes:
        print(f"[lèvres] consolidation : {n_fusionnes} fragment(s) de visage "
              f"regroupés par position -> {len(visages)} personne(s)")
    else:
        base = {i: base_e[i] / base_n[i] for i in base_n
                if base_n[i] >= 3 and i in {f["id"] for f in visages}}
    return visages, energies, presence, base
