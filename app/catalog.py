"""Catalogue des pièces proposées à l'annotation : celles que le moteur sait reconnaître, plus des
familles courantes dans les petits animaux (pour pouvoir annoter ce que le moteur ne connaît pas encore).
Les noms viennent de la bibliothèque LDraw (data/ldraw)."""

from __future__ import annotations

from pathlib import Path

from brickforge import identify

LDRAW = Path(__file__).resolve().parent.parent / "data" / "ldraw" / "parts"

# (référence, famille, (largeur, profondeur)) ; profondeur = le long de la pente pour les pentes
EXTRA = [
    ("93273", "curved", (1, 4)),   # pente courbe double 4x1 (arche)
    ("15068", "curved", (2, 2)),
    ("41769", "wedge", (2, 4)), ("41770", "wedge", (2, 4)),
    ("43722", "wedge", (2, 3)), ("43723", "wedge", (2, 3)),
    ("51739", "wedge", (2, 4)), ("26601", "wedge", (2, 2)),
    ("24299", "wedge", (2, 2)), ("24307", "wedge", (2, 2)),
    ("27925", "round", (2, 2)), ("25269", "round", (1, 1)),
    ("6141", "round", (1, 1)), ("4032", "round", (2, 2)),
    ("3062b", "round", (1, 1)), ("6143", "round", (2, 2)),
    ("3005", "brick", (1, 1)), ("3004", "brick", (1, 2)), ("3010", "brick", (1, 4)),
    ("3003", "brick", (2, 2)), ("3001", "brick", (2, 4)),
    ("87087", "snot", (1, 1)), ("99780", "snot", (1, 2)), ("99781", "snot", (1, 2)),
    ("3665", "slope", (1, 2)),     # pente inversée 45 2x1
    ("24246", "tile", (1, 1)),
    ("3039", "slope", (2, 2)), ("3040b", "slope", (1, 2)), ("4286", "slope", (1, 3)), ("3298", "slope", (2, 3)),
    ("3660", "slope", (2, 2)), ("4287", "slope", (1, 3)),
    ("11477", "curved", (1, 2)), ("50950", "curved", (1, 3)), ("61678", "curved", (1, 4)), ("93606", "curved", (2, 4)),
    ("42022", "curved", (1, 6)), ("24309", "curved", (1, 3)), ("88930", "curved", (2, 4)),
    ("29119", "wedge", (1, 2)), ("29120", "wedge", (1, 2)), ("3700", "brick", (1, 2)), ("3009", "brick", (1, 6)),
    ("3002", "brick", (2, 3)), ("2357", "brick", (2, 2)), ("3622", "brick", (1, 3)),
    ("3794b", "plate", (1, 2)), ("15573", "plate", (1, 2)), ("3031", "plate", (4, 4)), ("3710", "plate", (1, 4)),
    ("2420", "plate", (2, 2)), ("4081b", "snot", (1, 1)), ("60478", "snot", (1, 2)), ("48336", "snot", (1, 2)),
    ("3065", "brick", (1, 2)), ("98283", "brick", (1, 2)), ("33909", "tile", (2, 2)), ("35480", "plate", (1, 2)),
    # pièces des chèvres et pièces courantes de détail
    ("4589", "round", (1, 1)), ("3062b", "round", (1, 1)), ("85861", "round", (1, 1)), ("98138", "round", (1, 1)),
    ("11211", "snot", (1, 2)), ("87087", "snot", (1, 1)), ("53451", "other", (1, 1)), ("32607", "other", (1, 1)),
    ("3660", "slope", (2, 2)), ("3665", "slope", (1, 2)), ("24201", "curved", (1, 2)), ("32803", "curved", (2, 2)),
    ("13547", "curved", (1, 4)), ("93273", "curved", (1, 4)), ("22385", "tile", (2, 3)), ("3035", "plate", (4, 8)),
    ("3032", "plate", (4, 6)), ("3034", "plate", (2, 8)), ("3795", "plate", (2, 6)), ("3666", "plate", (1, 6)),
    ("3460", "plate", (1, 8)), ("3020", "plate", (2, 4)), ("3021", "plate", (2, 3)), ("3022", "plate", (2, 2)),
    ("3023", "plate", (1, 2)), ("3024", "plate", (1, 1)), ("3623", "plate", (1, 3)), ("3009", "brick", (1, 6)),
    ("22890", "other", (1, 2)), ("14418", "other", (1, 2)), ("4032", "round", (2, 2)), ("3941", "round", (2, 2)),
]


def _title(part: str) -> str:
    p = LDRAW / f"{part}.dat"
    try:
        t = " ".join(p.read_text(errors="ignore").splitlines()[0][2:].strip().split())
        if t.startswith("~Moved to "):   # alias : on prend le nom de la pièce cible
            return _title(t.split()[-1])
        return t
    except (OSError, IndexError):
        return part


def _build() -> list[dict]:
    seen, out = set(), []
    fams = [("plate", identify.PLATES), ("tile", identify.TILES), ("curved", identify.CURVED),
            ("slope", identify.STRAIGHT), ("round", identify.ROUND)]
    rows = [(part, fam, size) for fam, table in fams for size, part in table.items()] + EXTRA
    for part, fam, size in rows:
        if part in seen:
            continue
        seen.add(part)
        out.append({"part": part, "kind": fam, "size": list(size), "name": _title(part),
                    "known": part in {p for _, t in fams for p in t.values()}})
    out += _brickheadz(seen)
    return sorted(out, key=lambda r: (r["kind"], r["size"][0] * r["size"][1], r["part"]))


def _kind(name: str) -> str:
    n = name.lower()
    if "studs on" in n or "stud on" in n or "headlight" in n or "with clip" in n or "bracket" in n:
        return "snot"
    if "wedge" in n:
        return "wedge"
    if "curved" in n:
        return "curved"
    if "round" in n or "dish" in n:
        return "round"
    if n.startswith("tile"):
        return "tile"
    if "slope" in n:
        return "slope"
    if n.startswith("plate"):
        return "plate"
    if n.startswith("brick"):
        return "brick"
    return "other"


def _brickheadz(seen) -> list[dict]:
    """Les pièces de la bibliothèque de remplissage (BrickHeadz officielles) et des montages SNOT : 22885, 4070, 11476…"""
    import re
    from brickforge import fill
    out = []
    for part in list(fill.EXTRA) + list(fill.EXTRA2) + ["22885", "4070", "11476", "87087", "99780", "99781", "4733", "30414"]:
        if part in seen or not (LDRAW / f"{part}.dat").exists():
            continue
        seen.add(part)
        name = _title(part)
        m = re.search(r"(\d+)\s*x\s*(\d+)", name)
        size = (int(m.group(1)), int(m.group(2))) if m else (1, 1)
        out.append({"part": part, "kind": _kind(name), "size": list(size), "name": name, "known": False, "brickheadz": True})
    return out


CATALOG = _build()
