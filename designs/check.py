"""Vérifie qu'aucune pièce ne flotte dans un assemblage.

Deux pièces sont « connectées » si leurs boîtes englobantes (dans le repère monde) se touchent
verticalement (dessus de l'une = dessous de l'autre, avec recouvrement horizontal) — c'est le cas
d'un emboîtement tenon/tube — ou se touchent de côté avec recouvrement (pièces montées en SNOT).
On liste les composantes connexes : tout ce qui n'est pas dans la plus grande flotte.

Usage : python -m designs.check [sujet]     (défaut : lego_tortue)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from designs.kit import mesh

ROOT = Path(__file__).resolve().parent.parent
TOL = 0.6    # LDU
MIN_OVERLAP = 3.0  # LDU de recouvrement minimal sur les autres axes
SIDE_PARTS = {"22890", "14418", "6141"}
JOINTS = {"22890", "14418"}  # rotules et pièces fixées de côté


def world_boxes(parts):
    boxes = []
    for p in parts:
        m = mesh(p["part"])
        lo, hi = np.array(m["bbox"][0]), np.array(m["bbox"][1])
        lo[1] = max(lo[1], m["body_top"]) if m["body_top"] > lo[1] - 0.01 else lo[1]
        if p["part"] in JOINTS:          # rotule : seule la plaque 1x2 compte pour l'empilement
            lo, hi = np.array([-20.0, 0.0, -10.0]), np.array([20.0, 8.0, 10.0])
        R = np.array(p["m"][3:]).reshape(3, 3)
        c = np.array([[a, b, cc] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for cc in (lo[2], hi[2])]) @ R.T
        c += np.array(p["m"][:3])
        boxes.append((c.min(0), c.max(0)))
    return boxes


def touching(a, b, side_ok=False):
    """Contact vertical (empilement tenon/tube) ; contact latéral seulement si side_ok (SNOT)."""
    (alo, ahi), (blo, bhi) = a, b
    ov = np.minimum(ahi, bhi) - np.maximum(alo, blo)       # recouvrement par axe (négatif = écart)
    if (ov < -TOL).any():
        return False
    stacked = abs(ahi[1] - blo[1]) < TOL or abs(bhi[1] - alo[1]) < TOL
    if stacked and ov[0] > MIN_OVERLAP and ov[2] > MIN_OVERLAP:
        return True
    if side_ok:
        for ax in (0, 2):
            others = [o for o in range(3) if o != ax]
            if ov[ax] > -TOL and ov[ax] < 4.5 and (ov[others] > MIN_OVERLAP).all():   # tenon latéral enfoncé (4 LDU)
                return True
    return False


def check(subject="lego_tortue", verbose=True):
    doc = json.loads((ROOT / "imgs" / subject / "assemblage.json").read_text())
    return check_parts(doc["parts"], verbose)


def check_parts(parts, verbose=False):
    """Indices des pièces qui ne sont pas reliées au sol (liste vide si tout tient)."""
    if not parts:
        return []
    boxes = world_boxes(parts)
    n = len(parts)
    adj = [[] for _ in range(n)]
    snot = [abs(abs(np.array(p["m"][3:]).reshape(3, 3)[1, 1]) - 1) > 0.01 or p["part"] in SIDE_PARTS for p in parts]
    for i in range(n):
        for j in range(i + 1, n):
            if touching(boxes[i], boxes[j], side_ok=snot[i] or snot[j]):
                adj[i].append(j)
                adj[j].append(i)
    # rotules : bille (22890) et logement (14418) dont les centres coïncident
    def joint_center(p):
        R = np.array(p["m"][3:]).reshape(3, 3)
        return R @ np.array([30.0, 4.0, 0.0]) + np.array(p["m"][:3])
    balls = [i for i, p in enumerate(parts) if p["part"] == "22890"]
    sockets = [i for i, p in enumerate(parts) if p["part"] == "14418"]
    for i in balls:
        for j in sockets:
            if np.linalg.norm(joint_center(parts[i]) - joint_center(parts[j])) < 1.0:
                adj[i].append(j)
                adj[j].append(i)
    # sous-ensembles rigides (nageoires inclinées) : leurs pièces sont assemblées entre elles dans
    # leur propre repère ; on les relie entre elles (les boîtes inclinées ne « s'empilent » plus à plat)
    by_grp = {}
    for i, p in enumerate(parts):
        if p.get("grp"):
            by_grp.setdefault(p["grp"], []).append(i)
    for members in by_grp.values():
        for i in members[1:]:
            adj[members[0]].append(i)
            adj[i].append(members[0])
    comp = [-1] * n
    comps = []
    for s in range(n):
        if comp[s] >= 0:
            continue
        stack, cur = [s], []
        comp[s] = len(comps)
        while stack:
            i = stack.pop()
            cur.append(i)
            for j in adj[i]:
                if comp[j] < 0:
                    comp[j] = len(comps)
                    stack.append(j)
        comps.append(cur)
    ground = {i for i in range(n) if abs(boxes[i][1][1]) < TOL}
    comps.sort(key=lambda c: (not (set(c) & ground), -len(c)))
    floating = [i for c in comps if not (set(c) & ground) for i in c]   # tout groupe posé au sol tient
    if verbose:
        print(f"{n} pièces, {len(comps)} groupe(s) ; principal : {len(comps[0])} pièces ; flottantes : {len(floating)}")
        for c in comps[1:]:
            for i in c:
                p, (lo, hi) = parts[i], boxes[i]
                print(f"  {p['id']:6} {p['part']:7} coul {p['color']:3}  x {lo[0]/20:5.1f}..{hi[0]/20:5.1f}  "
                      f"z {lo[2]/20:5.1f}..{hi[2]/20:5.1f}  k {-hi[1]/8:5.1f}..{-lo[1]/8:5.1f}  (groupe de {len(c)})")
    return floating


if __name__ == "__main__":
    check(sys.argv[1] if len(sys.argv) > 1 else "lego_tortue")
