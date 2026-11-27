"""Calcule le modèle 3D (pipeline voxels -> pièces) d'un sujet et l'écrit en JSON pour l'app.

Usage : python -m app.model3d <sujet> <sortie.json>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from brickforge import colors
from brickforge.bricks import build_pieces
from brickforge.views import load_subject
from brickforge.voxels import reconstruct

ROOT = Path(__file__).resolve().parent.parent


def _hex(code: int) -> str:
    b, g, r = colors.code_bgr(code)
    return f"#{r:02x}{g:02x}{b:02x}"


def main() -> None:
    subject, out = sys.argv[1], Path(sys.argv[2])
    views = load_subject(ROOT / "imgs" / subject)
    model = reconstruct(views)
    placed = build_pieces(model.color)
    filled = model.filled
    W, L, H = filled.shape
    studs = []
    for p in placed:
        if p.kind == "plate":
            for i in range(p.i, p.i + p.di):
                for j in range(p.j, p.j + p.dj):
                    if p.k + 1 >= H or not filled[i, j, p.k + 1]:
                        studs.append([i, j, p.k, p.color])
    by_color = Counter(p.color for p in placed)
    data = {
        "size": [W, L, H],
        "pieces": [[p.kind, p.i, p.j, p.k, p.di, p.dj, p.dk, p.color, p.dir[0], p.dir[1]] for p in placed],
        "studs": studs,
        "colorHex": {str(c): _hex(c) for c in by_color},
        "palette": [{"code": c, "name": colors.NAMES.get(c, str(c)), "hex": _hex(c), "n": n} for c, n in by_color.most_common()],
        "nParts": len(placed),
        "nRefs": len({(p.part, p.color) for p in placed}),
        "kinds": dict(Counter(p.kind for p in placed)),
        "parts": dict(Counter(p.part for p in placed).most_common()),
    }
    out.write_text(json.dumps(data, default=int))


if __name__ == "__main__":
    main()
