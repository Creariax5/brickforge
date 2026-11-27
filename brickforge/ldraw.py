"""Export LDraw (.ldr) et nomenclature (BOM)."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from . import colors
from .bricks import Placed

STUD = 20   # LDU
PLATE = 8   # LDU

# Rotations autour de Y (matrices LDraw a b c d e f g h i)
_IDENT = "1 0 0 0 1 0 0 0 1"
_ROT_Y90 = "0 0 1 0 1 0 -1 0 0"      # X local -> -Z monde ; Z local -> X monde
_ROT_Y180 = "-1 0 0 0 1 0 0 0 -1"
_ROT_Y270 = "0 0 -1 0 1 0 1 0 0"
# Pentes : géométrie canonique descendant vers -Z ; rotation selon le sens de descente (di, dj)
_SLOPE_ROT = {(0, -1): _IDENT, (0, 1): _ROT_Y180, (-1, 0): _ROT_Y90, (1, 0): _ROT_Y270}


def ldraw_line(p: Placed) -> str:
    """Grille -> LDraw : i -> X, j -> Z, couche k -> -Y (Y vers le bas en LDraw)."""
    x = (p.i + p.di / 2) * STUD
    z = (p.j + p.dj / 2) * STUD
    if p.kind in ("cheese", "curved"):
        y = -p.k * PLATE                         # origine au centre de la face inférieure
        rot = _SLOPE_ROT[p.dir]
    else:
        y = -(p.k + 1) * PLATE                   # plaques et tuiles : origine sur la face supérieure
        rot = _IDENT if p.di >= p.dj else _ROT_Y90
    return f"1 {p.color} {x:g} {y:g} {z:g} {rot} {p.part}.dat"


def write_ldr(placed: list[Placed], path: Path, title: str) -> None:
    lines = [f"0 {title}", f"0 Name: {path.name}", "0 Author: Brick Forge (généré)", ""]
    lines += [ldraw_line(p) for p in sorted(placed, key=lambda p: (p.k, p.j, p.i))]
    path.write_text("\n".join(lines) + "\n")


def write_bom(placed: list[Placed], path: Path) -> Counter:
    bom = Counter((p.part, p.color) for p in placed)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["part", "color_ldraw", "color_name", "qty"])
        for (part, col), n in sorted(bom.items(), key=lambda x: -x[1]):
            w.writerow([part, col, colors.NAMES.get(col, "?"), n])
    return bom
