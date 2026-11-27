"""Prédictions du détecteur de pièces sur des images (sortie JSON pour l'app).

Usage : python -m brickforge.predict --weights runs/segment/pieces_v1/weights/last.pt img1.jpg [img2.jpg ...]
Sortie (stdout) : [{"image", "w", "h", "objects": [{"part", "conf", "poly": [[x, y], ...] (normalisés)}]}]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--weights", default="runs/segment/pieces_v1/weights/last.pt")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="cpu")      # le GPU est occupé par l'entraînement
    a = ap.parse_args()
    from ultralytics import YOLO
    model = YOLO(a.weights)
    names = model.names
    out = []
    for r in model.predict(a.images, conf=a.conf, imgsz=a.imgsz, device=a.device, verbose=False, retina_masks=False):
        h, w = r.orig_shape
        objs = []
        if r.masks is not None:
            for poly, c, cf in zip(r.masks.xyn, r.boxes.cls.tolist(), r.boxes.conf.tolist()):
                if len(poly) < 3:
                    continue
                step = max(1, len(poly) // 60)                     # contours allégés
                objs.append({"part": names[int(c)], "conf": round(cf, 3),
                             "poly": [[round(float(x), 4), round(float(y), 4)] for x, y in poly[::step]]})
        out.append({"image": Path(r.path).name, "w": w, "h": h, "objects": objs})
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
