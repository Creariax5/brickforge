"""Forme cible : volume sculpté à partir des silhouettes des vues Gemini, sur la grille de construction.

Chaque case de la grille (1 tenon × 1 tenon × 1 plaque) est échantillonnée (2×2×2 points) ; un point
est dans la cible s'il se projette dans la silhouette de chaque vue (caméras calées par compare.py).
target[i, j, k] = part des points gardés (0..1).

Repère : LDraw (X, Z en LDU, Y vers le bas). Case (i, j, k) : x ∈ [x0 + 20i, +20], z ∈ [z0 + 20j, +20],
y ∈ [-8(k+1), -8k] (k = 0 au sol).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import compare as C

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Target:
    frac: np.ndarray        # (I, J, K)
    x0: float
    z0: float
    center: np.ndarray      # centre de scène utilisé par les caméras (repère Y vers le haut)
    cams: dict
    views: dict             # vue -> (photo BGR, masque bool)

    def cell_center_world(self, i, j, k):
        """Centre de case en repère Y vers le haut (celui des caméras)."""
        return np.stack([self.x0 + 20 * (np.asarray(i) + 0.5), 8 * (np.asarray(k) + 0.5),
                         self.z0 + 20 * (np.asarray(j) + 0.5)], -1)


def carve(subject: str, ref_assembly: Path | None = None, margin: int = 3, dilate_px: int = 3) -> Target:
    sdir = ROOT / "imgs" / subject
    cdir = ROOT / "out" / "compare" / subject
    cams = json.loads((cdir / "cameras.json").read_text())
    # Les caméras ont été calées dans le repère du modèle de référence (centre = centre de sa boîte)
    ref = json.loads((ref_assembly or sdir / "assemblage.json").read_text())
    scene = C.load_scene(ref)
    v = scene[0].reshape(-1, 3)
    center = (v.min(0) + v.max(0)) / 2
    lo, hi = v.min(0), v.max(0)                                   # repère Y vers le haut
    x0 = np.floor(lo[0] / 20) * 20 - margin * 20
    z0 = np.floor(lo[2] / 20) * 20 - margin * 20
    I = int(np.ceil((hi[0] - x0) / 20)) + margin
    J = int(np.ceil((hi[2] - z0) / 20)) + margin
    K = int(np.ceil(hi[1] / 8)) + margin
    views = {}
    for name in cams:
        m = cv2.imread(str(cdir / f"{name}_mask.png"), 0)
        ph = cv2.imread(str(cdir / f"{name}_photo.jpg"))
        if m is None or ph is None:
            continue
        mk = m > 0
        if dilate_px:
            mk = cv2.dilate(mk.astype(np.uint8), np.ones((2 * dilate_px + 1,) * 2, np.uint8)) > 0
        views[name] = (ph, mk)
    # points d'échantillonnage
    subh = np.array([1, 3, 5]) / 6          # 3 x 3 x 2 points par case
    subv = np.array([0.25, 0.75])
    ii, jj, kk = np.meshgrid(np.arange(I), np.arange(J), np.arange(K), indexing="ij")
    pts = []
    for a in subh:
        for b in subh:
            for c in subv:
                pts.append(np.stack([x0 + 20 * (ii + a), 8 * (kk + c), z0 + 20 * (jj + b)], -1))
    NS = len(pts)
    P = np.stack(pts, 3).reshape(-1, 3)
    inside = np.ones(len(P), bool)
    for name, (ph, mk) in views.items():
        H, W = mk.shape
        x, y, z = C.project(P, cams[name], (W, H), center)
        xi, yi = np.round(x).astype(int), np.round(y).astype(int)
        ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
        hit = np.zeros(len(P), bool)
        hit[ok] = mk[yi[ok], xi[ok]]
        inside &= hit
    frac = inside.reshape(I, J, K, NS).mean(3)
    frac[:, :, 0] = np.maximum(frac[:, :, 0], 0)                  # rien sous le sol
    return Target(frac, float(x0), float(z0), center, cams, views)


if __name__ == "__main__":
    import sys
    t = carve(sys.argv[1] if len(sys.argv) > 1 else "lego_tortue")
    print("grille", t.frac.shape, "cases pleines (>0.5) :", int((t.frac > 0.5).sum()), "partielles :",
          int(((t.frac > 0) & (t.frac <= 0.5)).sum()))
    for k in range(t.frac.shape[2]):
        print(k, int((t.frac[:, :, k] > 0.5).sum()), end=" | ")
