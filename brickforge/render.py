"""Aperçus rapides d'un modèle en voxels (sans Blender ni LDView) : vue isométrique et vue de dessus."""

from __future__ import annotations

import cv2
import numpy as np

from . import colors

PLATE_H = 8 / 20  # hauteur d'une plaque en pas de tenon


def iso(color: np.ndarray, s: int = 16, head_towards_viewer: bool = True) -> np.ndarray:
    W, L, H = color.shape
    filled = color >= 0
    if head_towards_viewer:  # j = 0 (tête) vers l'observateur
        color, filled = color[:, ::-1], filled[:, ::-1]
    pad = np.pad(filled, 1)

    def proj(u, v, h):
        return (u - v) * 0.866 * s, ((u + v) * 0.5 - h) * s

    xs, ys = [], []
    for u, v, h in ((0, 0, 0), (W, 0, 0), (0, L, 0), (W, L, 0), (0, 0, H * PLATE_H)):
        x, y = proj(u, v, h)
        xs.append(x)
        ys.append(y)
    ox, oy = -min(xs) + 20, -min(ys) + 20
    img = np.full((int(max(ys) + oy + 20), int(max(xs) + ox + 20), 3), 255, np.uint8)

    def poly(pts, col):
        arr = np.array([[proj(*p)[0] + ox, proj(*p)[1] + oy] for p in pts], np.int32)
        cv2.fillConvexPoly(img, arr, col, lineType=cv2.LINE_AA)
        cv2.polylines(img, [arr], True, (60, 60, 60), 1, lineType=cv2.LINE_AA)

    vox = np.argwhere(filled)
    order = np.lexsort((vox[:, 2], vox[:, 0] + vox[:, 1]))
    for i, j, k in vox[order]:
        top_vis = not pad[i + 1, j + 1, k + 2]
        u_vis = not pad[i + 2, j + 1, k + 1]
        v_vis = not pad[i + 1, j + 2, k + 1]
        if not (top_vis or u_vis or v_vis):
            continue
        base = np.array(colors.code_bgr(int(color[i, j, k])), float)
        h0, h1 = k * PLATE_H, (k + 1) * PLATE_H
        if u_vis:
            poly([(i + 1, j, h0), (i + 1, j + 1, h0), (i + 1, j + 1, h1), (i + 1, j, h1)], tuple((base * 0.8).tolist()))
        if v_vis:
            poly([(i, j + 1, h0), (i + 1, j + 1, h0), (i + 1, j + 1, h1), (i, j + 1, h1)], tuple((base * 0.62).tolist()))
        if top_vis:
            poly([(i, j, h1), (i + 1, j, h1), (i + 1, j + 1, h1), (i, j + 1, h1)], tuple(base.tolist()))
    return img


def top_map(color: np.ndarray, s: int = 24) -> np.ndarray:
    """Couleur visible depuis le dessus (tête en haut), une case par tenon."""
    W, L, H = color.shape
    img = np.full((L * s, W * s, 3), 255, np.uint8)
    for i in range(W):
        for j in range(L):
            ks = np.nonzero(color[i, j] >= 0)[0]
            if len(ks):
                c = colors.code_bgr(int(color[i, j, ks.max()]))
                cv2.rectangle(img, (i * s, j * s), ((i + 1) * s - 1, (j + 1) * s - 1), c, -1)
                cv2.circle(img, (i * s + s // 2, j * s + s // 2), int(s * 0.3), (90, 90, 90), 1, cv2.LINE_AA)
    return img
