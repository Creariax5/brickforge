"""Conversion voxels -> pièces.

Ordre de placement :
1. pentes sur les bords du dessus (là où la surface descend d'au moins 2 plaques) :
   pente courbe 2x1 (11477) / 2x2 (15068) sur deux cases, sinon cheese slope 1x1 (54200) / 1x2 (85984) ;
2. tuiles sur toutes les cases visibles par le dessus (finition lisse) ;
3. plaques pour le reste, par fusion gloutonne par couche et par couleur, joints croisés.

Repère : i = largeur, j = longueur (0 = tête), k = couche de plaque (0 = sol).
Une « direction » de pente est le sens dans lequel elle DESCEND : (di, dj) parmi (±1, 0), (0, ±1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# (largeur, longueur) -> référence LDraw ; orientation canonique : longueur le long de X.
PLATES: dict[tuple[int, int], str] = {
    (1, 1): "3024", (1, 2): "3023", (1, 3): "3623", (1, 4): "3710", (1, 6): "3666", (1, 8): "3460",
    (2, 2): "3022", (2, 3): "3021", (2, 4): "3020", (2, 6): "3795", (2, 8): "3034",
    (4, 4): "3031", (4, 6): "3032", (4, 8): "3035",
}
TILES: dict[tuple[int, int], str] = {
    (1, 1): "3070b", (1, 2): "3069b", (1, 3): "63864", (1, 4): "2431", (1, 6): "6636", (1, 8): "4162",
    (2, 2): "3068b", (2, 3): "26603", (2, 4): "87079", (2, 6): "69729",
}
# Pentes de 2 plaques de haut. Géométrie LDraw vérifiée (ldlib) : origine au centre de la face
# inférieure, côté haut vers +Z, la pente descend vers -Z. Clé : (largeur perpendiculaire, profondeur).
SLOPES: dict[str, dict[tuple[int, int], str]] = {
    "cheese": {(1, 1): "54200", (2, 1): "85984"},
    "curved": {(1, 2): "11477", (2, 2): "15068"},
}
SLOPE_PLATES = 2
DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]


@dataclass
class Placed:
    part: str
    color: int
    kind: str   # "plate" | "tile" | "cheese" | "curved"
    i: int      # coin (min) en largeur
    j: int      # coin (min) en longueur
    k: int      # couche la plus basse occupée
    di: int     # étendue en i
    dj: int     # étendue en j
    dk: int = 1                      # nombre de couches occupées
    dir: tuple[int, int] = (0, 0)    # sens de descente (pentes)


# ---------------------------------------------------------------- pentes

def _tops(filled: np.ndarray) -> np.ndarray:
    """Hauteur du dessus de chaque colonne (indice de la couche la plus haute + 1, 0 si vide)."""
    H = filled.shape[2]
    any_ = filled.any(axis=2)
    top = H - np.argmax(filled[:, :, ::-1], axis=2)
    return np.where(any_, top, 0)


def place_slopes(color: np.ndarray, used: np.ndarray) -> list[Placed]:
    filled = color >= 0
    W, L, _ = filled.shape
    top = _tops(filled)

    def t(i, j):
        return top[i, j] if 0 <= i < W and 0 <= j < L else 0

    def free_cap(i, j):
        """Les 2 couches du haut de la colonne sont pleines, libres, et de même couleur."""
        h = top[i, j]
        if h < SLOPE_PLATES:
            return False
        ks = slice(h - SLOPE_PLATES, h)
        return filled[i, j, ks].all() and not used[i, j, ks].any()

    singles: list[tuple[str, int, int, tuple[int, int]]] = []  # (kind, i, j, dir) pour l'appariement

    # 1. Pentes courbes 2x1 : case extérieure c1 au bord, case intérieure c2 derrière
    for (di, dj) in DIRS:
        for i in range(W):
            for j in range(L):
                h = top[i, j]
                i2, j2 = i - di, j - dj
                if not (0 <= i2 < W and 0 <= j2 < L) or h < SLOPE_PLATES:
                    continue
                if t(i + di, j + dj) > h - SLOPE_PLATES or top[i2, j2] != h or t(i2 - di, j2 - dj) < h:
                    continue
                if not (free_cap(i, j) and free_cap(i2, j2)):
                    continue
                if color[i, j, h - 1] != color[i2, j2, h - 1]:
                    continue
                for a, b in ((i, j), (i2, j2)):
                    used[a, b, h - SLOPE_PLATES:h] = True
                singles.append(("curved", min(i, i2), min(j, j2), (di, dj)))

    # 2. Cheese slopes 1x1 : bord à une case
    for (di, dj) in DIRS:
        for i in range(W):
            for j in range(L):
                h = top[i, j]
                if h < SLOPE_PLATES or t(i + di, j + dj) > h - SLOPE_PLATES or t(i - di, j - dj) < h:
                    continue
                if not free_cap(i, j):
                    continue
                used[i, j, h - SLOPE_PLATES:h] = True
                singles.append(("cheese", i, j, (di, dj)))

    # 3. Appariement côte à côte (même type, même sens, même couleur, même hauteur) -> pièce 2 de large
    placed: list[Placed] = []
    by_key = {}
    for kind, i, j, d in singles:
        h = top[i, j]
        by_key[(kind, i, j, d)] = (h, int(color[i, j, h - 1]))
    done = set()
    for kind, i, j, d in singles:
        if (kind, i, j, d) in done:
            continue
        h, c = by_key[(kind, i, j, d)]
        depth = 2 if kind == "curved" else 1
        side = (1, 0) if d[0] == 0 else (0, 1)  # direction perpendiculaire à la pente
        mate = (kind, i + side[0], j + side[1], d)
        wide = mate in by_key and mate not in done and by_key[mate] == (h, c)
        width = 2 if wide else 1
        done.add((kind, i, j, d))
        if wide:
            done.add(mate)
        part = SLOPES[kind][(width, depth)]
        if d[0] == 0:   # pente le long de j
            ext_i, ext_j = width, depth
        else:           # pente le long de i
            ext_i, ext_j = depth, width
        placed.append(Placed(part, c, kind, i, j, h - SLOPE_PLATES, ext_i, ext_j, SLOPE_PLATES, d))
    return placed


# ---------------------------------------------------------------- tuiles et plaques

def _merge(layer_color: np.ndarray, avail: np.ndarray, sizes: dict, kind: str, k: int, prefer_i: bool) -> list[Placed]:
    W, L = layer_color.shape
    taken = ~avail
    order = sorted(sizes, key=lambda s: -s[0] * s[1])
    orients = []
    for a, b in order:
        for o in (((b, a), (a, b)) if prefer_i else ((a, b), (b, a))):
            if o not in orients:
                orients.append(o)
    out = []
    for di, dj in orients:
        part = sizes[(min(di, dj), max(di, dj))]
        for i in range(W - di + 1):
            for j in range(L - dj + 1):
                if taken[i, j]:
                    continue
                block = layer_color[i:i + di, j:j + dj]
                if taken[i:i + di, j:j + dj].any() or (block != block[0, 0]).any():
                    continue
                taken[i:i + di, j:j + dj] = True
                out.append(Placed(part, int(block[0, 0]), kind, i, j, k, di, dj))
    return out


def build_pieces(color: np.ndarray, slopes: bool = True, tiles: bool = True) -> list[Placed]:
    filled = color >= 0
    W, L, H = filled.shape
    used = np.zeros_like(filled)
    placed = place_slopes(color, used) if slopes else []

    exposed_top = filled.copy()
    exposed_top[:, :, :-1] &= ~filled[:, :, 1:]
    for k in range(H):
        free = filled[:, :, k] & ~used[:, :, k]
        prefer_i = k % 2 == 0  # alternance : joints croisés d'une couche à l'autre
        if tiles:
            tile_mask = free & exposed_top[:, :, k]
            placed += _merge(color[:, :, k], tile_mask, TILES, "tile", k, prefer_i)
            free &= ~tile_mask
        placed += _merge(color[:, :, k], free, PLATES, "plate", k, prefer_i)
    return placed


# Compatibilité avec la v0
def merge_plates(color: np.ndarray) -> list[Placed]:
    return build_pieces(color, slopes=False, tiles=False)
