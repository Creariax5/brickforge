"""Assemblage 3D initial à partir des pièces reconnues sur la vue de dessus.

Chaque pièce reconnue est posée avec sa vraie géométrie LDraw :
- position horizontale : centre du segment, exprimé dans la grille principale de la vue de dessus ;
- hauteur : le dessus de la pièce affleure le dessus du volume reconstruit (enveloppe visuelle) à cet endroit ;
- orientation : angle de la grille locale (sous-ensembles tournés), sens de descente pour les pentes,
  côté long le long de l'emprise mesurée pour les pièces rectangulaires.
Sous les pièces reconnues, le volume restant est rempli de plaques (« structure »), que l'utilisateur
peut ensuite remplacer.

Format (assemblage.json) : {"parts": [{"id", "part", "color", "m": [x y z a b c d e f g h i], "src", "status"}]}
où m est la transformation LDraw (LDU, Y vers le bas), comme une ligne de type 1.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

from . import identify as idf
from .bricks import build_pieces
from .ldlib import part_mesh
from .ldraw import ldraw_line
from .views import load_subject
from .voxels import reconstruct

STUD, PLATE = 20.0, 8.0


def _rot_y(phi: float) -> list[float]:
    c, s = math.cos(phi), math.sin(phi)
    c = 0.0 if abs(c) < 1e-9 else c
    s = 0.0 if abs(s) < 1e-9 else s
    return [c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c]


def _apply(rot: list[float], v) -> np.ndarray:
    return np.array(rot).reshape(3, 3) @ np.asarray(v, float)


def _fallback_part(pc: dict) -> str:
    w, d = sorted(pc["size"]) if pc.get("size") else (1, 1)
    for size in ((w, d), (w, d - 1), (1, d), (1, 2), (1, 1)):
        if size in idf.PLATES:
            return idf.PLATES[size]
    return "3024"


def build_assembly(subject_dir: Path, pieces: list[dict]) -> dict:
    views = load_subject(subject_dir)
    model = reconstruct(views)
    g = model.grid
    top_view = views["dessus"]
    sc = top_view.scale
    color = model.color.copy()
    W, L, H = color.shape
    filled = color >= 0
    any_ = filled.any(axis=2)
    tops = np.where(any_, H - np.argmax(filled[:, :, ::-1], axis=2), 0)

    c0, s0 = math.cos(g.th), math.sin(g.th)
    eu, ev = np.array([c0, s0]), np.array([-s0, c0])

    def to_lattice(xy_work):
        rel = np.asarray(xy_work, float) - g.origin
        return rel @ eu / g.p - g.i0, rel @ ev / g.p - g.j0   # coordonnées continues (case i centrée en i)

    parts, carve = [], np.zeros((W, L), int)  # carve : nombre de couches à retirer du haut de chaque colonne
    for n, pc in enumerate(pieces):
        part = pc.get("part")
        status = "à vérifier" if part else "inconnue"
        if not part:
            part = _fallback_part(pc)
        try:
            mesh = part_mesh(part)
        except FileNotFoundError:
            continue
        (lx, ly, lz), (hx, hy, hz) = mesh["bbox"]
        if pc.get("polygon"):   # centre de surface du contour (px de l'image d'origine)
            mo = cv2.moments(np.array(pc["polygon"], np.float32))
            cx_img, cy_img = (mo["m10"] / mo["m00"], mo["m01"] / mo["m00"]) if mo["m00"] else np.mean(pc["polygon"], 0)
        else:
            continue
        u, v = to_lattice(np.array([cx_img, cy_img]) * sc)
        i, j = int(round(u)), int(round(v))
        if not (0 <= i < W and 0 <= j < L):
            continue

        # Orientation
        d_th = math.radians(pc.get("angle_deg", 0.0)) - g.th
        d_th = (d_th + math.pi / 4) % (math.pi / 2) - math.pi / 4      # écart à la grille principale
        if pc.get("slope_dir"):
            dx_img, dy_img = pc["slope_dir"]
            dx, dz = dx_img * c0 + dy_img * s0, -dx_img * s0 + dy_img * c0   # image -> monde (X, Z)
            phi = math.atan2(-dx, -dz)                                       # géométrie canonique : descend vers -Z
            snap = round(phi / (math.pi / 2)) * (math.pi / 2)
            if abs(phi - snap - d_th) < math.radians(12) or abs(d_th) < math.radians(5):
                phi = snap + d_th
        else:
            fu, fv = pc.get("footprint", (1, 1))
            long_x = (hx - lx) >= (hz - lz)
            phi = d_th + (0.0 if (fu >= fv) == long_x else math.pi / 2)
        rot = _rot_y(phi)

        # Position : centre de la boîte englobante sur le centre du segment ; dessus sur le volume
        if abs(d_th) < math.radians(5):   # sur la grille principale : on aligne sur les demi-tenons
            u, v = round(u * 2) / 2, round(v * 2) / 2
        target = np.array([(u + 0.5) * STUD, 0.0, (v + 0.5) * STUD])
        local_c = np.array([(lx + hx) / 2, 0.0, (lz + hz) / 2])
        top_layers = int(tops[i, j])
        y_top = -top_layers * PLATE
        pos = target - _apply(rot, local_c)
        pos[1] = y_top - mesh["body_top"]
        parts.append({"id": f"p{n + 1}", "part": part, "color": int(pc.get("color") or 71),
                      "m": [round(float(x), 2) for x in pos] + [round(x, 6) for x in rot],
                      "src": "détection", "status": status, "det": n})

        # Colonnes couvertes : celles dont le centre tombe dans le contour du segment
        h_layers = max(1, int(round(mesh["height"] / PLATE)))
        if pc.get("polygon"):
            poly = np.array(pc["polygon"], np.float32) * sc
            for ci in range(max(0, i - 6), min(W, i + 7)):
                for cj in range(max(0, j - 6), min(L, j + 7)):
                    p_img = g.center(ci, cj)
                    if cv2.pointPolygonTest(poly, (float(p_img[0]), float(p_img[1])), False) >= 0:
                        carve[ci, cj] = max(carve[ci, cj], h_layers)

    # Structure : le volume sous les pièces reconnues, en plaques
    for ci in range(W):
        for cj in range(L):
            if carve[ci, cj]:
                t = tops[ci, cj]
                color[ci, cj, max(0, t - carve[ci, cj]):] = -1
    for p in build_pieces(color, slopes=False, tiles=False):
        x = (p.i + p.di / 2) * STUD
        z = (p.j + p.dj / 2) * STUD
        y = -(p.k + 1) * PLATE
        rot = [1, 0, 0, 0, 1, 0, 0, 0, 1] if p.di >= p.dj else [0, 0, 1, 0, 1, 0, -1, 0, 0]
        parts.append({"id": f"s{len(parts) + 1}", "part": p.part, "color": int(p.color),
                      "m": [x, y, z] + rot, "src": "structure", "status": "structure"})
    return {"size": [W, L, H], "parts": parts}


def to_ldr(assembly: dict, title: str) -> str:
    lines = [f"0 {title}", f"0 Name: {title}.ldr", "0 Author: Brick Forge Lab", ""]
    for p in assembly["parts"]:
        m = p["m"]
        lines.append(f"1 {p['color']} " + " ".join(f"{v:g}" for v in m) + f" {p['part']}.dat")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import sys
    subj, run = Path(sys.argv[1]), Path(sys.argv[2])
    a = build_assembly(subj, json.loads((run / "pieces.json").read_text()))
    from collections import Counter
    print(len(a["parts"]), Counter(p["src"] for p in a["parts"]), Counter(p["status"] for p in a["parts"]))
