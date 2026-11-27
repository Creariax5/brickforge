"""Lecture minimale de la bibliothèque LDraw (data/ldraw) : géométrie aplatie d'une pièce.

Sert à vérifier les dimensions et l'orientation des pièces du catalogue (où est le côté haut
d'une pente, où est l'origine), sans dépendre de la documentation.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

LDRAW = Path(__file__).resolve().parent.parent / "data" / "ldraw"
_DIRS = [LDRAW / "parts", LDRAW / "p", LDRAW / "parts" / "s", LDRAW / "p" / "48", LDRAW / "omr_parts"]


def _find(name: str) -> Path | None:
    name = name.replace("\\", "/").lower()
    for d in _DIRS:
        p = d / name
        if p.exists():
            return p
    return None


@lru_cache(maxsize=None)
def _triangles(name: str) -> np.ndarray:
    """Triangles (N, 3, 3) de la pièce, sous-fichiers inclus, dans le repère de la pièce."""
    path = _find(name)
    if path is None:
        return np.zeros((0, 3, 3))
    tris = []
    for line in path.read_text(errors="ignore").splitlines():
        tok = line.split()
        if not tok:
            continue
        t = tok[0]
        if t == "1" and len(tok) >= 15:
            x, y, z = map(float, tok[2:5])
            m = np.array(list(map(float, tok[5:14]))).reshape(3, 3)
            sub = _triangles(" ".join(tok[14:]))
            if len(sub):
                tris.append(sub @ m.T + np.array([x, y, z]))
        elif t == "3" and len(tok) >= 11:
            tris.append(np.array(list(map(float, tok[2:11]))).reshape(1, 3, 3))
        elif t == "4" and len(tok) >= 14:
            q = np.array(list(map(float, tok[2:14]))).reshape(4, 3)
            tris.append(np.stack([q[[0, 1, 2]], q[[0, 2, 3]]]))
    return np.concatenate(tris) if tris else np.zeros((0, 3, 3))


def part_triangles(part: str) -> np.ndarray:
    return _triangles(part if part.endswith(".dat") else part + ".dat")


def bbox(part: str) -> tuple[np.ndarray, np.ndarray]:
    v = part_triangles(part).reshape(-1, 3)
    return v.min(0), v.max(0)


def describe(part: str) -> str:
    v = part_triangles(part).reshape(-1, 3)
    lo, hi = v.min(0), v.max(0)
    title = (_find(part + ".dat") or Path("?")).read_text(errors="ignore").splitlines()[0][2:]
    # Hauteur maximale (y minimal, Y vers le bas) en fonction de x et de z : révèle le sens d'une pente
    top = v[v[:, 1] < lo[1] + 2]
    return (f"{part:7} {title}\n   bbox x[{lo[0]:g},{hi[0]:g}] y[{lo[1]:g},{hi[1]:g}] z[{lo[2]:g},{hi[2]:g}]"
            f"  sommet: x[{top[:, 0].min():g},{top[:, 0].max():g}] z[{top[:, 2].min():g},{top[:, 2].max():g}]")


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(describe(p))


@lru_cache(maxsize=None)
def _edges(name: str) -> np.ndarray:
    """Arêtes (type 2) de la pièce, (N, 2, 3), pour le rendu « contour » façon Studio."""
    path = _find(name)
    if path is None:
        return np.zeros((0, 2, 3))
    segs = []
    for line in path.read_text(errors="ignore").splitlines():
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "1" and len(tok) >= 15:
            x, y, z = map(float, tok[2:5])
            m = np.array(list(map(float, tok[5:14]))).reshape(3, 3)
            sub = _edges(" ".join(tok[14:]))
            if len(sub):
                segs.append(sub @ m.T + np.array([x, y, z]))
        elif tok[0] == "2" and len(tok) >= 8:
            segs.append(np.array(list(map(float, tok[2:8]))).reshape(1, 2, 3))
    return np.concatenate(segs) if segs else np.zeros((0, 2, 3))


def part_mesh(part: str) -> dict:
    """Géométrie d'une pièce pour le navigateur : triangles, arêtes, boîte englobante, haut du corps.
    Repère LDraw (LDU, Y vers le bas). « body_top » : y du dessus du corps, tenons exclus."""
    name = part if part.endswith(".dat") else part + ".dat"
    tris = _triangles(name).astype(np.float32)
    edges = _edges(name).astype(np.float32)
    if not len(tris):
        raise FileNotFoundError(part)
    v = tris.reshape(-1, 3)
    lo, hi = v.min(0), v.max(0)
    # dessus du corps : les tenons dépassent de 4 LDU au-dessus de y = 0 sur les pièces à tenons
    body_top = 0.0 if abs(lo[1] + 4) < 0.01 and (v[:, 1] > -0.01).any() else float(lo[1])
    title = (_find(name) or Path("?")).read_text(errors="ignore").splitlines()[0][2:].strip()
    return {"part": part, "title": " ".join(title.split()), "tris": tris.reshape(-1), "edges": edges.reshape(-1),
            "bbox": [lo.tolist(), hi.tolist()], "body_top": body_top, "height": float(hi[1] - body_top)}
