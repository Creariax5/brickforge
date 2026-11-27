"""Rastériseur avec tampon de profondeur (z-buffer), compilé avec numba.

Remplace l'algorithme du peintre (tri des triangles par profondeur moyenne), faux dès que des grands
triangles en recouvrent de petits : chaque pixel garde le triangle réellement le plus proche.
"""

from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def _raster(px, py, pz, W, H, depth, tri_id):
    n = px.shape[0]
    for t in range(n):
        x0, x1, x2 = px[t, 0], px[t, 1], px[t, 2]
        y0, y1, y2 = py[t, 0], py[t, 1], py[t, 2]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        xmin = max(int(np.floor(min(x0, x1, x2))), 0)
        xmax = min(int(np.ceil(max(x0, x1, x2))), W - 1)
        ymin = max(int(np.floor(min(y0, y1, y2))), 0)
        ymax = min(int(np.ceil(max(y0, y1, y2))), H - 1)
        if xmin > xmax or ymin > ymax:
            continue
        # profondeur interpolée en 1/z (correcte en perspective)
        iz0, iz1, iz2 = 1.0 / pz[t, 0], 1.0 / pz[t, 1], 1.0 / pz[t, 2]
        for y in range(ymin, ymax + 1):
            cy = y + 0.5
            for x in range(xmin, xmax + 1):
                cx = x + 0.5
                w0 = ((x1 - cx) * (y2 - cy) - (x2 - cx) * (y1 - cy)) / area
                w1 = ((x2 - cx) * (y0 - cy) - (x0 - cx) * (y2 - cy)) / area
                w2 = 1.0 - w0 - w1
                if w0 < -1e-6 or w1 < -1e-6 or w2 < -1e-6:
                    continue
                iz = w0 * iz0 + w1 * iz1 + w2 * iz2
                if iz > depth[y, x]:
                    depth[y, x] = iz
                    tri_id[y, x] = t


def raster(px, py, pz, W, H):
    """px, py, pz : (N, 3) coordonnées écran et profondeur. Renvoie l'indice du triangle visible par pixel (-1 = fond)."""
    depth = np.zeros((H, W), np.float64)
    tri_id = -np.ones((H, W), np.int64)
    _raster(np.ascontiguousarray(px, np.float64), np.ascontiguousarray(py, np.float64),
            np.ascontiguousarray(pz, np.float64), W, H, depth, tri_id)
    return tri_id
