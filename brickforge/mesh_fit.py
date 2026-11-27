"""Recale un maillage généré (Hunyuan3D, TRELLIS.2…) sur la vraie forme d'une BrickHeadz officielle et mesure le volume commun.

Recherche : quart de tour × miroir gauche/droite, puis rotation fine, échelle par axe et décalage (recherche par motifs),
en maximisant le volume commun (cases « pleines à plus de la moitié », comme pour les constructions).
Sorties dans le dossier du maillage : fit.json (paramètres, volume, silhouettes), fit.glb (maillage recalé, repère LDU),
fit_dist.bin (écart signé de chaque sommet à la surface des briques, en LDU) — pour la vue 3D superposée.

    python -m brickforge.mesh_fit data/trellis/donald_512/donald_512.glb 40377-1:0
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
from scipy import ndimage

from brickforge import fill as F
from brickforge import fill_learn as L
from brickforge.from_mesh import load, to_frame


def _up(mesh, up):
    """Maillage remis « Y vers le haut » (glTF) ; certains outils (TRELLIS.2) exportent Z vers le haut."""
    if up == "y":
        return mesh
    m = mesh.copy()
    v = np.asarray(m.vertices, float)
    m.vertices = np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1)
    return m


def _pts(mesh, yaw, flip, n=600_000, plates=30.0):
    v = to_frame(mesh, yaw, plates)
    if flip:
        v[:, 2] = -v[:, 2]
    p, _ = trimesh.sample.sample_surface(trimesh.Trimesh(v, mesh.faces, process=False), n, seed=0)
    return v, p


def _xf(p, x):
    th, sx, sy, sz, tx, ty, tz = x
    q = p * [sx, sy, sz]
    c, s = np.cos(th), np.sin(th)
    return np.stack([q[:, 0] * c + q[:, 2] * s, q[:, 1], -q[:, 0] * s + q[:, 2] * c], 1) + [tx, ty, tz]


def fit(mesh, T, log=print):
    best = None
    for up in ("y", "z"):
        mu = _up(mesh, up)
        for flip in (False, True):
            for yaw in range(4):
                _, p = _pts(mu, yaw, flip, n=200_000)
                v = L.iou(T, L.fine_vox(p))
                if best is None or v > best[0]:
                    best = (v, yaw, flip, up)
    v0, yaw, flip, up = best
    log(f"orientation : haut {up}, quart {yaw}, miroir {flip} → volume {v0:.3f}")
    mesh = _up(mesh, up)
    verts, P = _pts(mesh, yaw, flip)
    sc = lambda x: L.iou(T, L.fine_vox(_xf(P, x)))
    ident = (sc(np.array([0.0, 1, 1, 1, 0, 0, 0])), np.array([0.0, 1, 1, 1, 0, 0, 0]))
    starts = [ident]
    for sz in (1.0, 1.06, 1.12):                                  # départs grossiers : décalage et profondeur (évite un optimum local)
        for tx in range(-20, 21, 5):
            for tz in range(-20, 21, 5):
                y = np.array([0.0, 1, 1, sz, tx, 0, tz], float)
                starts.append((sc(y), y))
    starts.sort(key=lambda t: -t[0])
    best = None
    for v0s, x in starts[:3] + ([ident] if not any(t is ident for t in starts[:3]) else []):
        cur = v0s
        steps = np.array([np.radians(4), 0.06, 0.04, 0.06, 8.0, 4.0, 8.0])
        for rnd in range(6):
            imp = True
            while imp:
                imp = False
                for i in range(7):
                    for sg in (1, -1):
                        y = x.copy()
                        y[i] += sg * steps[i]
                        v = sc(y)
                        if v > cur + 1e-4:
                            x, cur, imp = y, v, True
            steps /= 2
        log(f"départ {v0s:.3f} → {cur:.4f}")
        if best is None or cur > best[0]:
            best = (cur, x)
    cur, x = best
    H = L.fine_vox(_xf(P, x))
    return {"up": up, "yaw": yaw, "mirror": flip, "start": v0, "theta_deg": float(np.degrees(x[0])), "scale": x[1:4].tolist(),
            "shift_ldu": x[4:].tolist(), "volume": L.iou(T, H), "sil": F.silhouettes(T, H), "cells": int(H.sum()), "target_cells": int(T.sum())}, \
        _xf(verts, x), H


def surface_dist(verts_ldu, placed):
    """Écart signé (LDU) de chaque sommet à la peau extérieure de la vraie LEGO : + = dépasse, − = en retrait."""
    from scipy.spatial import cKDTree
    from brickforge.brickheadz_zones import tris
    rng = np.random.default_rng(0)
    P = []
    for p in placed:
        t = tris(p)
        if not len(t):
            continue
        t = t.reshape(-1, 3, 3)
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
        k = np.clip((area * 2).astype(int), 3, 3000)
        rep = np.repeat(np.arange(len(t)), k)
        u, w = rng.random((2, len(rep)))
        f = u + w > 1
        u[f], w[f] = 1 - u[f], 1 - w[f]
        P.append(a[rep] + (b[rep] - a[rep]) * u[:, None] + (c[rep] - a[rep]) * w[:, None])
    pts = np.vstack(P)
    r = 2
    n, ny = F.N * r, F.NY * r
    idx = lambda q: (np.clip(np.floor(q[:, 0] / (F.CX / r)).astype(int) + F.C0 * r, 0, n - 1),
                     np.clip(np.floor(-q[:, 1] / (F.CY / r)).astype(int), 0, ny - 1),
                     np.clip(np.floor(q[:, 2] / (F.CX / r)).astype(int) + F.C0 * r, 0, n - 1))
    g = np.zeros((n, ny, n), bool)
    g[idx(pts)] = True
    g = ndimage.binary_fill_holes(ndimage.binary_closing(g, iterations=1))
    skin = g & ~ndimage.binary_erosion(g)
    keep = skin[idx(pts)]
    d, _ = cKDTree(pts[keep]).query(verts_ldu, workers=-1)
    vi = idx(verts_ldu)
    inside = g[vi] & ~skin[vi]
    return np.where(inside, -d, d).astype(np.float32)


def run(glb, ref):
    glb = Path(glb)
    names, Ts, _ = L.targets()
    T = Ts[names.index(ref)]
    figs = {f"{f['num']}:{f['fig']}": f for f in json.loads((F.OUT / "figures.json").read_text())}
    mesh = load(glb)
    t0 = time.time()
    info, verts, H = fit(mesh, T)
    info.update({"ref": ref, "mesh": str(glb), "faces": int(len(mesh.faces)), "seconds": round(time.time() - t0)})
    d = surface_dist(verts, figs[ref]["placed"])
    info.update({"dist_median": float(np.median(np.abs(d))), "dist_lt2": float((np.abs(d) < 2).mean())})
    m2 = _up(mesh, info["up"]).copy()
    m2.vertices = verts
    m2.export(glb.parent / "fit.glb")
    (glb.parent / "fit_dist.bin").write_bytes(d.tobytes())
    np.save(glb.parent / "fit_cells.npy", H)
    (glb.parent / "fit.json").write_text(json.dumps(info, indent=1))
    print(json.dumps({k: v for k, v in info.items()}, ensure_ascii=False))
    return info


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "40377-1:0")
