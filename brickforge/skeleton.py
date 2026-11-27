"""Le squelette commun des BrickHeadz : les pièces (même pièce, même position, même orientation) présentes dans beaucoup
des 101 figurines officielles, et la fréquence de matière case par case.

Sorties :
  research/assets/16-skeleton.json   pièces avec leur fréquence (pour la vue 3D à seuil)
  data/brickheadz/skeleton.json      résumé (pièces ≥ 50 %, constructibilité du squelette)

    python -m brickforge.skeleton
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from brickforge import fill as F
from brickforge.buildcheck import check

ROOT = Path(__file__).resolve().parent.parent


def base(part):
    """Pièce imprimée → pièce de base (même forme)."""
    return re.sub(r"(p[a-z]*\d.*|pat.*|pr\d.*)$", "", part) if re.match(r"^\d+[a-z]?p", part) else part


SYM = {"3003", "3022", "3068b", "4032a", "4032", "3024", "3070b", "87580", "3062b", "4073", "6141", "98138", "3958", "3031", "2420",
       "3005", "3062", "14769", "24246", "25269", "1745", "35480"}            # pièces dont un quart de tour ne change pas la place occupée


def key(p, q=4):
    """Pièce sans couleur ni impression, position arrondie à q LDU, orientation (ignorée pour les pièces symétriques)."""
    m = p["m"]
    b = base(p["part"])
    rot = "sym" if b in SYM else tuple(int(round(v)) for v in m[3:])
    return (b, tuple(int(round(v / q)) for v in m[:3]), rot)


def head_base(f):
    """Hauteur (y LDraw) du bas de la tête : le plus bas étage de briques 22885 (noyau de tête), ou None."""
    ys = [p["m"][1] for p in f["placed"] if base(p["part"]) == "22885"]
    return max(ys) if ys else None


def aligned(f):
    """Pièces de la figurine, la tête recalée sur un bas de tête commun (y = HEAD_Y), le reste sur le socle."""
    hb = head_base(f)
    out = []
    for p in f["placed"]:
        if hb is not None and p["m"][1] <= hb + 4:               # au niveau ou au-dessus du premier étage de 22885 : la tête
            q = dict(p)
            q["m"] = [p["m"][0], p["m"][1] - hb + HEAD_Y] + list(p["m"][2:])
            q["zone"] = "tete"
            out.append(q)
        else:
            out.append({**p, "zone": "corps"})
    return out


HEAD_Y = -104.0                                                   # bas de tête médian (13 plates) : sert seulement à l'affichage


def _vox(placed):
    from brickforge.fill_learn import real_vox
    return real_vox(placed)


def main():
    figs = json.loads((F.OUT / "figures.json").read_text())
    for f in figs:
        f["placed"] = aligned(f)
    n = len(figs)
    cnt, ex, colors = Counter(), {}, defaultdict(Counter)
    for f in figs:
        seen = set()
        for p in f["placed"]:
            k = key(p)
            if k in seen:
                continue
            seen.add(k)
            cnt[k] += 1
            ex.setdefault(k, p)
            colors[k][p.get("color", 71)] += 1
    rows = []
    for k, c in cnt.most_common():
        if c < 5:
            break
        p = ex[k]
        rows.append({"part": k[0], "m": p["m"], "freq": round(c / n, 3), "color": colors[k].most_common(1)[0][0], "zone": p["zone"]})
    # combien de pièces d'une figurine typique viennent du squelette
    per = []
    for f in figs:
        ks = {key(p) for p in f["placed"]}
        per.append({t: sum(1 for k in ks if cnt[k] >= t * n) / max(1, len(ks)) for t in (0.3, 0.5, 0.7, 0.9)})
    share = {str(t): round(float(np.median([d[t] for d in per])), 3) for t in (0.3, 0.5, 0.7, 0.9)}
    summ = {"figures": n}
    for t in (0.9, 0.7, 0.5, 0.3):
        sk = [r for r in rows if r["freq"] >= t]
        placed = [{"part": r["part"], "color": r["color"], "m": r["m"]} for r in sk]
        chk = check(placed) if placed else {"floating": [], "collisions": []}
        summ[f">={int(t * 100)}%"] = {"pieces": len(sk), "parts": Counter(r["part"] for r in sk).most_common(12),
                                      "floating": len(chk["floating"]), "collisions": len(chk["collisions"])}
    summ["share_of_figure"] = share
    # fréquence de matière case par case : vraie forme de chaque figurine, tête recalée comme les pièces
    from multiprocessing import Pool
    with Pool(14) as pool:
        vox = pool.map(_vox, [[{k: v for k, v in p.items() if k != "zone"} for p in f["placed"]] for f in figs])
    occ = np.mean(np.array(vox).astype(np.float32), 0)
    for t in (0.5, 0.7, 0.9):
        summ[f"cases>={int(t * 100)}%"] = int((occ >= t).sum())
    summ["cases_figure_mediane"] = int(np.median([v.sum() for v in vox]))
    cells = [[int(i), int(j), int(k), round(float(occ[i, j, k]), 2)] for i, j, k in np.argwhere(occ >= 0.1)]
    out = {"pieces": rows, "cells": cells, "cx": F.CX, "cy": F.CY, "c0": F.C0, "n": n, "summary": summ}
    (ROOT / "research" / "assets" / "16-skeleton.json").write_text(json.dumps(out))
    (F.OUT / "skeleton.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False))
    print(json.dumps(summ, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
