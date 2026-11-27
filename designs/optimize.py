"""Ajuste automatiquement les réglages d'un modèle pour qu'il ressemble le plus aux vues Gemini.

Recherche par coordonnées : chaque réglage est essayé un cran au-dessus et en dessous ; on garde
la meilleure amélioration, et on recommence jusqu'à ce que plus rien n'améliore.

Score : moyenne sur les vues de (silhouette − écart de contour / 100), caméras figées sur leur
dernier calage (seul le modèle change). Contraintes physiques : aucune pièce flottante, rien sous la table.

Usage : python -m designs.optimize tortue
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from brickforge import compare as C
from designs.check import check, world_boxes

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")

# réglage -> (valeur de départ, pas, min, max)
PARAMS = {
    "tortue": {
        "FRONT_TILT": (13, 3, 0, 30), "REAR_TILT": (9, 3, 0, 30),
        "FRONT_YAW": (30, 8, 0, 60), "REAR_YAW": (49, 8, 15, 75),
        "HEAD_DK": (1, 1, -2, 2), "FRONT_SHORT": (1, 1, 0, 1), "HEAD_DZ": (0, 1, -1, 2),   # DROP figé à 3 : hauteur du dôme validée à l oeil sur le profil
    },
}
EVAL_W = 450


class Scorer:
    def __init__(self, subject):
        self.dir = ROOT / "imgs" / f"lego_{subject}"
        out = ROOT / "out" / "compare" / self.dir.name
        self.cams = json.loads((out / "cameras.json").read_text())
        self.masks = {}
        for v in self.cams:
            m = cv2.imread(str(out / f"{v}_mask.png"), 0)
            if m is None:
                continue
            k = EVAL_W / m.shape[1]
            self.masks[v] = cv2.resize(m, (EVAL_W, int(m.shape[0] * k)), interpolation=cv2.INTER_NEAREST) > 0

    def score(self, assembly):
        scene = C.load_scene(assembly)
        v = scene[0].reshape(-1, 3)
        center = (v.min(0) + v.max(0)) / 2
        res = {}
        for view, pm in self.masks.items():
            H, W = pm.shape
            rm = C.render(scene, self.cams[view], (W, H), center, color=False) > 0
            size = max(np.ptp(np.nonzero(pm)[0]), np.ptp(np.nonzero(pm)[1]))
            res[view] = (C.iou(pm, rm), 100 * C.contour_distance(pm, rm) / size)
        total = float(np.mean([s - c / 100 for s, c in res.values()]))
        return total, res


def build(subject, values):
    env = dict(os.environ, **{k: str(v) for k, v in values.items()})
    subprocess.run([PY, "-m", f"designs.{subject}"], env=env, cwd=ROOT, capture_output=True, check=True)
    return json.loads((ROOT / "imgs" / f"lego_{subject}" / "assemblage.json").read_text())


def feasible(subject, assembly):
    floating = check(f"lego_{subject}", verbose=False)
    B = world_boxes(assembly["parts"])
    lowest = min(-hi[1] / 8 for lo, hi in B)
    return not floating and lowest > -0.05, len(floating), lowest


def main(subject):
    space = PARAMS[subject]
    cur = {k: v[0] for k, v in space.items()}
    scorer = Scorer(subject)
    cache = {}

    def evaluate(vals):
        key = tuple(sorted(vals.items()))
        if key not in cache:
            a = build(subject, vals)
            ok, nfl, low = feasible(subject, a)
            s, detail = scorer.score(a) if ok else (-1.0, {})
            cache[key] = (s, ok, nfl, low, detail)
            tag = "ok" if ok else f"REJETÉ (flottantes {nfl}, plus bas {low:.2f})"
            print(f"  {vals}  score {s:.4f}  {tag}", flush=True)
        return cache[key]

    best = evaluate(cur)[0]
    print(f"départ : {best:.4f}", flush=True)
    t0 = time.time()
    improved = True
    while improved:
        improved = False
        cands = []
        for k, (_, step, lo, hi) in space.items():
            for d in (-step, step):
                v = cur[k] + d
                if lo <= v <= hi:
                    cands.append({**cur, k: v})
        results = [(evaluate(c)[0], c) for c in cands]
        s, c = max(results, key=lambda r: r[0])
        if s > best + 1e-4:
            best, cur = s, c
            improved = True
            print(f"→ meilleur {best:.4f} avec {cur}", flush=True)
    # affinage : demi-pas sur les réglages continus
    for k, (_, step, lo, hi) in space.items():
        if step >= 2:
            for d in (-step // 2, step // 2):
                v = cur[k] + d
                if lo <= v <= hi:
                    s = evaluate({**cur, k: v})[0]
                    if s > best + 1e-4:
                        best, cur = s, {**cur, k: v}
                        print(f"→ meilleur {best:.4f} avec {cur}", flush=True)
    build(subject, cur)
    det = cache[tuple(sorted(cur.items()))][4]
    print(f"FINAL {best:.4f} {json.dumps(cur)} ({time.time() - t0:.0f} s)")
    for v, (s, c) in det.items():
        print(f"   {v:8} silhouette {s:.3f}  contour {c:.2f} %")
    (ROOT / "out" / "compare" / f"lego_{subject}" / "optim.json").write_text(json.dumps({"best": best, "values": cur}))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tortue")
