"""Génère une page HTML autonome : modèle 3D (plaques + tenons) à côté des vues sources.

Usage :
    python -m brickforge.viewer imgs/lego_tortue [--out out/viewer]
"""

from __future__ import annotations

import argparse
import base64
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from . import colors
from .bricks import build_pieces
from .views import VIEW_NAMES, load_subject
from .voxels import reconstruct

TEMPLATE = Path(__file__).with_name("viewer_template.html")


def _thumb(path: Path, width: int = 520) -> str:
    img = cv2.imread(str(path))
    s = width / img.shape[1]
    img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 78])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _hex(code: int) -> str:
    b, g, r = colors.code_bgr(code)
    return f"#{r:02x}{g:02x}{b:02x}"


def build(folder: Path, out: Path, profil_tete: str = "droite") -> Path:
    views = load_subject(folder)
    model = reconstruct(views, profil_tete=profil_tete)
    placed = build_pieces(model.color)
    filled = model.filled
    W, L, H = filled.shape

    pieces = [[p.kind, p.i, p.j, p.k, p.di, p.dj, p.dk, p.color, p.dir[0], p.dir[1]] for p in placed]
    # Tenons visibles : cases de plaques dont la case du dessus est vide
    studs = []
    for p in placed:
        if p.kind != "plate":
            continue
        for i in range(p.i, p.i + p.di):
            for j in range(p.j, p.j + p.dj):
                if p.k + 1 >= H or not filled[i, j, p.k + 1]:
                    studs.append([i, j, p.k, p.color])

    by_color = Counter(p.color for p in placed)
    palette = [{"code": c, "name": colors.NAMES.get(c, str(c)), "hex": _hex(c), "n": n}
               for c, n in by_color.most_common()]
    srcs = []
    for name in ("concept",) + VIEW_NAMES:
        for ext in (".jpeg", ".jpg", ".png"):
            p = folder / f"{name}{ext}"
            if p.exists():
                srcs.append({"name": name, "src": _thumb(p)})
                break

    data = {
        "subject": folder.name.replace("lego_", ""),
        "size": [int(W), int(L), int(H)],
        "pieces": pieces,
        "studs": studs,
        "palette": palette,
        "colorHex": {str(c): _hex(c) for c in by_color},
        "nParts": len(placed),
        "kinds": dict(Counter(p.kind for p in placed)),
        "nRefs": len({(p.part, p.color) for p in placed}),
        "views": srcs,
    }
    title = data["subject"].capitalize() + " en briques"
    html = (TEMPLATE.read_text().replace("__TITLE__", title)
            .replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":"), default=int)))
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{folder.name}.html"
    dest.write_text(html)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/viewer"))
    ap.add_argument("--profil-tete", choices=["droite", "gauche"], default="droite")
    args = ap.parse_args()
    print(build(args.folder, args.out, args.profil_tete))


if __name__ == "__main__":
    main()
