# DoublageBasic v6 — module fusion
# Fait partie du projet DoublageBasic (voir doublage_basic.py).
"""Étage 4 : recoupement audio↔lèvres, attribution voix/visage, fusions utilisateur."""
from __future__ import annotations

import sys


def fusion_levres(events, visages, energies, presence, base, seuil: float = 1.35):
    """Recoupement audio ↔ lèvres. Pour chaque réplique, le visage « gagnant »
    est celui dont le mouvement de bouche dépasse le plus nettement son
    mouvement au repos. Puis chaque VOIX (cluster pyannote) est attribuée au
    visage qui remporte le plus ses répliques.

    Retourne (attribution, gagnants, alertes) :
      attribution : {speaker: id_visage ou None}
      gagnants    : {i_event: id_visage ou None}
      alertes     : [str]  — signale tout ce qui cloche, sans jamais inventer
    """
    alertes = []
    gagnants = {}
    for i in range(len(events)):
        scores = {}
        for f in visages:
            k = f"{i}|{f['id']}"
            if presence.get(k):
                moy = energies[k] / presence[k]
                rep = base.get(f["id"])
                scores[f["id"]] = moy / rep if rep else moy * 2
                # pas de référence repos -> on exige un mouvement net (x2)
        if not scores:
            gagnants[i] = None
            continue
        top = max(scores.values())
        if top < seuil:
            gagnants[i] = None
        else:
            gagnants[i] = max(scores, key=scores.get)

    votes = {}
    for i, e in enumerate(events):
        g = gagnants.get(i)
        if g is not None:
            votes.setdefault(e["speaker"], {})
            votes[e["speaker"]][g] = votes[e["speaker"]].get(g, 0) + 1

    attribution = {}
    for sp in sorted({e["speaker"] for e in events}):
        if sp in votes:
            attribution[sp] = max(votes[sp], key=votes[sp].get)
        else:
            attribution[sp] = None

    # alertes
    for sp, vf in sorted(attribution.items()):
        if vf is None:
            n = sum(1 for e in events if e["speaker"] == sp)
            alertes.append(f"voix {sp} : jamais attribuée à un visage "
                           f"({n} réplique(s)) — hors champ, dos tourné ou "
                           f"voix off ?")
    seen = {}
    for sp, vf in attribution.items():
        if vf is not None:
            if vf in seen.values():
                autre = [s for s, v in attribution.items() if v == vf][0]
                alertes.append(f"voix {sp} et voix {autre} : même visage "
                               f"n°{vf} — 2 personnes ou 1 seule voix mal "
                               f"découpée par pyannote ?")
            seen[sp] = vf
    sans = sum(1 for g in gagnants.values() if g is None)
    if sans:
        alertes.append(f"{sans} réplique(s) sans lèvres détectées "
                       f"(visage de profil, cadrage large, ou voix off)")
    return attribution, gagnants, alertes


def fusionne_voix(events, groupes):
    """Fusionne des voix : chaque --fusion 'a,b,c' = ces voix sont UNE seule
    personne. Les events sont ré-étiquetés puis les voix renumérotées 0..N-1.
    Modifie `events` en place ; retourne le mapping affiché."""
    existants = {e["speaker"] for e in events}
    parent = {i: i for i in existants}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for g in groupes:
        ids = sorted({i for i in g if i in existants})
        if len(ids) < 2:
            print(f"[fusion] groupe {g} ignoré (1 seule voix connue)")
            continue
        for i in ids[1:]:
            parent[find(i)] = find(ids[0])

    racines = sorted({find(i) for i in existants})
    renum = {r: n for n, r in enumerate(racines)}
    mapping = {}
    for i in sorted(existants):
        mapping[i] = renum[find(i)]
    for e in events:
        e["speaker"] = mapping[e["speaker"]]
    return mapping


