"""Mesure d'une détection de pièces par rapport à la vérité terrain annotée.

Vérité terrain : imgs/<sujet>/gt_<vue>.json
    {"view": "dessus", "pieces": [{"id", "polygon", "kind", "part", "color", "size", "dir"}], "updated"}
Prédiction : liste de pièces (identify.Piece en dict), avec "polygon" et "slope_dir".

Appariement : IoU des contours (rasterisés), glouton par IoU décroissante, seuil 0,5.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

IOU_MIN = 0.5
RASTER = 0.25  # résolution de rasterisation (fraction de l'image d'origine)
DIRS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}


def dir_label(vec) -> str | None:
    if not vec:
        return None
    dx, dy = vec
    return max(DIRS, key=lambda k: DIRS[k][0] * dx + DIRS[k][1] * dy)


def norm_kind(k: str | None) -> str | None:
    return k.rstrip("?") if k else k


def _raster(poly, shape) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    if poly and len(poly) >= 3:
        pts = (np.array(poly, np.float32) * RASTER).round().astype(np.int32)
        cv2.fillPoly(m, [pts], 1)
    return m.astype(bool)


def match(gt: list[dict], pred: list[dict], image_size: tuple[int, int]) -> list[tuple[int, int, float]]:
    w, h = image_size
    shape = (int(h * RASTER) + 1, int(w * RASTER) + 1)
    G = [_raster(g["polygon"], shape) for g in gt]
    P = [_raster(p["polygon"], shape) for p in pred]
    pairs = []
    for i, g in enumerate(G):
        ga = g.sum()
        if not ga:
            continue
        for j, p in enumerate(P):
            inter = np.logical_and(g, p).sum()
            if inter:
                iou = inter / (ga + p.sum() - inter)
                if iou >= IOU_MIN:
                    pairs.append((i, j, float(iou)))
    pairs.sort(key=lambda t: -t[2])
    used_g, used_p, out = set(), set(), []
    for i, j, iou in pairs:
        if i not in used_g and j not in used_p:
            used_g.add(i)
            used_p.add(j)
            out.append((i, j, iou))
    return out


def evaluate(gt_doc: dict, pred: list[dict], image_size: tuple[int, int]) -> dict:
    gt = [g for g in gt_doc.get("pieces", []) if g.get("polygon")]
    pairs = match(gt, pred, image_size)
    n_gt, n_pred, n_m = len(gt), len(pred), len(pairs)
    checks = {"kind": [], "part": [], "color": [], "size": [], "dir": []}
    errors = []
    for i, j, iou in pairs:
        g, p = gt[i], pred[j]
        pdir = dir_label(p.get("slope_dir"))
        res = {
            "kind": norm_kind(g.get("kind")) == norm_kind(p.get("kind")),
            "part": g.get("part") == p.get("part"),
            "color": g.get("color") == p.get("color"),
            "size": list(g.get("size") or []) == list(p.get("size") or []),
        }
        if g.get("dir"):
            res["dir"] = g["dir"] == pdir
        for k, ok in res.items():
            checks[k].append(ok)
            if not ok:
                errors.append({"type": k, "gt": g["id"], "pred": j, "iou": round(iou, 2),
                               "attendu": g.get(k if k != "dir" else "dir"),
                               "obtenu": pdir if k == "dir" else p.get(k)})
    matched_g = {i for i, _, _ in pairs}
    matched_p = {j for _, j, _ in pairs}
    errors += [{"type": "manquée", "gt": gt[i]["id"], "attendu": gt[i].get("part")} for i in range(n_gt) if i not in matched_g]
    errors += [{"type": "en trop", "pred": j, "obtenu": pred[j].get("part")} for j in range(n_pred) if j not in matched_p]

    def rate(v):
        return round(sum(v) / len(v), 3) if v else None

    prec = n_m / n_pred if n_pred else None
    rec = n_m / n_gt if n_gt else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    # « Pièce parfaite » : appariée avec la bonne référence et la bonne couleur
    perfect = sum(1 for i, j, _ in pairs if gt[i].get("part") == pred[j].get("part")
                  and gt[i].get("color") == pred[j].get("color"))
    return {
        "n_gt": n_gt, "n_pred": n_pred, "n_matched": n_m,
        "precision": round(prec, 3) if prec is not None else None,
        "recall": round(rec, 3) if rec is not None else None,
        "f1": round(f1, 3) if f1 else None,
        "kind_acc": rate(checks["kind"]), "part_acc": rate(checks["part"]),
        "color_acc": rate(checks["color"]), "size_acc": rate(checks["size"]), "dir_acc": rate(checks["dir"]),
        "perfect": perfect, "perfect_rate": round(perfect / n_gt, 3) if n_gt else None,
        "pairs": [{"gt": gt[i]["id"], "pred": j, "iou": round(iou, 2)} for i, j, iou in pairs],
        "errors": errors,
    }


def load_gt(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None
