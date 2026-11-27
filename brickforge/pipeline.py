"""Pipeline naïf de bout en bout : dossier de vues -> voxels -> plaques -> .ldr + BOM + aperçus.

Usage :
    python -m brickforge.pipeline imgs/lego_tortue [--out out/] [--profil-tete droite|gauche]

Le dossier doit contenir au minimum dessus, profil et face (dos et dessous sont optionnels,
utilisés pour les couleurs).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from . import render
from .bricks import build_pieces
from .colors import NAMES
from .ldraw import write_bom, write_ldr
from .views import load_subject
from .voxels import reconstruct


def run(folder: Path, out: Path, profil_tete: str = "droite") -> dict:
    views = load_subject(folder)
    missing = {"dessus", "profil", "face"} - views.keys()
    if missing:
        raise SystemExit(f"{folder}: vues manquantes : {', '.join(sorted(missing))}")

    model = reconstruct(views, profil_tete=profil_tete)
    placed = build_pieces(model.color)

    name = folder.name
    out.mkdir(parents=True, exist_ok=True)
    write_ldr(placed, out / f"{name}.ldr", title=f"Brick Forge - {name}")
    bom = write_bom(placed, out / f"{name}_bom.csv")
    cv2.imwrite(str(out / f"{name}_iso.png"), render.iso(model.color))
    cv2.imwrite(str(out / f"{name}_iso_arriere.png"), render.iso(model.color, head_towards_viewer=False))
    cv2.imwrite(str(out / f"{name}_dessus.png"), render.top_map(model.color))

    W, L, H = model.color.shape
    used_colors = Counter(p.color for p in placed)
    summary = {
        "sujet": name,
        "grille_tenons": [int(W), int(L)],
        "hauteur_plaques": int(H),
        "pas_px_origine": round(model.grid.p / views["dessus"].scale, 1),
        "voxels": int(model.filled.sum()),
        "pieces": len(placed),
        "references": len(bom),
        "types": dict(Counter(p.kind for p in placed)),
        "couleurs": {NAMES.get(c, str(c)): n for c, n in used_colors.most_common()},
    }
    (out / f"{name}_resume.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--profil-tete", choices=["droite", "gauche"], default="droite")
    args = ap.parse_args()
    print(json.dumps(run(args.folder, args.out, args.profil_tete), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
