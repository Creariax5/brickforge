"""Points d'accroche et « motif » de chaque pièce sur la grille de construction.

Grille : une case = 1 tenon (20 LDU) × 1 tenon × 1 plaque (8 LDU). Repère LDraw (Y vers le bas).
Pour une pièce et une orientation (rotation de 0/90/180/270° autour de la verticale), on calcule :
- occ   (X, Z, K) : part de chaque case remplie par la pièce (0..1), K = 0 au bas de la pièce ;
- solid (X, Z, K) : cases interdites aux autres pièces (occ > seuil) ;
- female (X, Z)   : cases du dessous qui peuvent s'emboîter sur un tenon (cavités) ;
- male [(i, j, k)] : tenons vers le haut ; une pièce posée dont le bas est à la couche k s'y emboîte ;
- origin_offset : position LDraw de l'origine de la pièce par rapport au coin (0, 0, bas) du motif.

Les tenons viennent des sous-pièces de la bibliothèque LDraw (stud.dat, stud2.dat…) ; les cavités et le
volume, de la géométrie (lancer de rayons verticaux).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from scipy import ndimage

from .ldlib import _find, part_mesh, part_triangles

MALE_STUDS = {"stud.dat", "stud2.dat", "stud2a.dat", "stud2s.dat", "stud10.dat", "stud6.dat", "stud6a.dat"}
SAMPLES = 3          # échantillons par axe horizontal dans une case
OCC_SOLID = 0.08     # au-delà, la case est réservée à la pièce


def _rot_y(q: int) -> np.ndarray:
    c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][q % 4]
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], float)


def male_studs_local(part: str) -> list[tuple[np.ndarray, np.ndarray]]:
    """(position de la base du tenon, direction du tenon) dans le repère de la pièce."""
    out = []

    def walk(name, M, t, depth):
        p = _find(name)
        if p is None or depth > 6:
            return
        for line in p.read_text(errors="ignore").splitlines():
            tok = line.split()
            if len(tok) < 15 or tok[0] != "1":
                continue
            sub = " ".join(tok[14:]).lower().replace("\\", "/")
            m = np.array(list(map(float, tok[5:14]))).reshape(3, 3)
            v = np.array(list(map(float, tok[2:5])))
            M2, t2 = M @ m, M @ v + t
            base = sub.split("/")[-1]
            if base in MALE_STUDS:
                d = M2 @ np.array([0.0, -1.0, 0.0])
                out.append((t2, d / np.linalg.norm(d)))
            elif not base.startswith("stud"):
                walk(sub, M2, t2, depth + 1)

    walk(part if part.endswith(".dat") else part + ".dat", np.eye(3), np.zeros(3), 0)
    return out


def _vertical_hits(tris: np.ndarray, pts: np.ndarray):
    """Pour chaque point (x, z) : y min et y max des intersections d'une verticale avec les triangles."""
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    ymin = np.full(len(pts), np.inf)
    ymax = np.full(len(pts), -np.inf)
    v0 = (c - a)[:, [0, 2]]
    v1 = (b - a)[:, [0, 2]]
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    ok = np.abs(den) > 1e-9
    a, v0, v1, d00, d01, d11, den = a[ok], v0[ok], v1[ok], d00[ok], d01[ok], d11[ok], den[ok]
    ya, yb, yc = tris[ok, 0, 1], tris[ok, 1, 1], tris[ok, 2, 1]
    for start in range(0, len(pts), 256):
        P = pts[start:start + 256]
        v2 = P[:, None, :] - a[None, :, [0, 2]]
        d20 = (v2 * v0[None]).sum(2); d21 = (v2 * v1[None]).sum(2)
        u = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
        inside = (u >= -1e-6) & (w >= -1e-6) & (u + w <= 1 + 1e-6)
        y = ya + u * (yc - ya) + w * (yb - ya)
        y = np.where(inside, y, np.nan)
        with np.errstate(all="ignore"):
            ymin[start:start + 256] = np.nanmin(np.where(inside, y, np.inf), axis=1)
            ymax[start:start + 256] = np.nanmax(np.where(inside, y, -np.inf), axis=1)
    return ymin, ymax


@dataclass
class Kernel:
    part: str
    q: int                      # orientation (quarts de tour)
    occ: np.ndarray             # (X, Z, K) part remplie
    solid: np.ndarray           # (X, Z, K) bool
    female: np.ndarray          # (X, Z) bool
    male: list                  # [(i, j, k)]
    origin_offset: np.ndarray   # LDU : origine de la pièce - (coin x, bas y, coin z) du motif
    R: np.ndarray = field(repr=False)

    @property
    def shape(self):
        return self.occ.shape


@lru_cache(maxsize=None)
def kernel(part: str, q: int) -> Kernel | None:
    m = part_mesh(part)
    R = _rot_y(q)
    tris = part_triangles(part).astype(np.float64) @ R.T
    body_top = m["body_top"]
    body = tris[(tris[..., 1] >= body_top - 0.5).all(1)]          # sans les tenons du dessus
    if not len(body):
        return None
    v = body.reshape(-1, 3)
    lo, hi = v.min(0), v.max(0)
    # bords de cases : multiples de 10 LDU (pièce de largeur impaire centrée sur une case, paire sur un bord)
    X = max(1, int(round((hi[0] - lo[0]) / 20)))
    Z = max(1, int(round((hi[2] - lo[2]) / 20)))
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    x0 = round((cx - X * 10) / 10) * 10
    z0 = round((cz - Z * 10) / 10) * 10
    x1, z1 = x0 + 20 * X, z0 + 20 * Z
    ybot = hi[1]
    K = max(1, int(math.ceil((ybot - lo[1]) / 8 - 0.05)))
    if X < 1 or Z < 1 or X > 12 or Z > 12:
        return None
    # échantillons horizontaux
    off = (np.arange(SAMPLES) + 0.5) / SAMPLES * 20
    gx = x0 + (np.arange(X)[:, None] * 20 + off[None]).reshape(-1)
    gz = z0 + (np.arange(Z)[:, None] * 20 + off[None]).reshape(-1)
    PX, PZ = np.meshgrid(gx, gz, indexing="ij")
    pts = np.stack([PX.ravel(), PZ.ravel()], 1)
    ytop, ymax = _vertical_hits(body, pts)
    ytop = ytop.reshape(X * SAMPLES, Z * SAMPLES)
    ymax = ymax.reshape(X * SAMPLES, Z * SAMPLES)
    hit = np.isfinite(ytop)
    # dessous : échantillons dont la surface la plus basse touche le bas de la pièce ; trous bouchés
    # (une brique est creuse, mais sa cavité reste à elle)
    bottom = hit & (ymax >= ybot - 0.6)
    cell_bottom = bottom.reshape(X, SAMPLES, Z, SAMPLES).any((1, 3))
    female = ndimage.binary_fill_holes(cell_bottom)
    foot = np.repeat(np.repeat(female, SAMPLES, 0), SAMPLES, 1)
    ybot_col = np.where(foot, ybot, np.where(hit, ymax, -np.inf))
    # remplissage par couche : fraction de la hauteur de la couche entre le dessus et le bas de la colonne
    occ = np.zeros((X, Z, K))
    for k in range(K):
        ya, yb = ybot - 8 * (k + 1), ybot - 8 * k          # couche k : y dans [ya, yb]
        f = np.clip((np.minimum(yb, ybot_col) - np.maximum(ya, np.where(hit, ytop, np.inf))) / 8, 0, 1)
        f[~hit & ~foot] = 0
        occ[:, :, k] = f.reshape(X, SAMPLES, Z, SAMPLES).mean((1, 3))
    solid = occ > OCC_SOLID
    # tenons vers le haut
    male = []
    for pos, d in male_studs_local(part):
        pos = R @ pos
        d = R @ d
        if d[1] < -0.9:                                      # tenon vers le haut seulement (pour l'instant)
            i, j = int((pos[0] - x0) // 20), int((pos[2] - z0) // 20)
            k = int(round((ybot - pos[1]) / 8))
            if 0 <= i < X and 0 <= j < Z:
                male.append((i, j, k))
    return Kernel(part, q, occ, solid, female, sorted(set(male)),
                  np.array([-x0, -ybot, -z0], float), R)


def orientations(part: str) -> list[Kernel]:
    """Orientations distinctes d'une pièce (une 2x2 symétrique n'en garde qu'une)."""
    out, seen = [], set()
    for q in range(4):
        k = kernel(part, q)
        if k is None:
            continue
        sig = (k.occ.shape, k.occ.round(2).tobytes(), tuple(k.male), k.female.tobytes())
        if sig not in seen:
            seen.add(sig)
            out.append(k)
    return out


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:] or ["3024", "3023", "3001", "3070b", "3040b", "11477", "54200", "24201", "79491", "3062b"]:
        for k in orientations(p):
            print(f"{p:6} q{k.q} motif {k.shape}  tenons {k.male}  cavités {int(k.female.sum())}  "
                  f"remplissage par couche {[round(float(k.occ[:, :, i].mean()), 2) for i in range(k.shape[2])]}")
