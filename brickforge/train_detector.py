"""Entraîne le détecteur de pièces (YOLO segmentation d'instances) sur les données synthétiques.

Prépare un découpage entraînement / validation par scène (les vues d'une même scène restent ensemble),
écrit le fichier de configuration du jeu de données, puis lance l'entraînement.

Usage : python -m brickforge.train_detector --data out/synth --epochs 40 [--model yolo11s-seg.pt] [--device mps]
Résultat : runs/segment/<nom>/weights/best.pt
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def prepare(data: Path, val_frac=0.1, seed=0) -> Path:
    imgs = sorted((data / "images").glob("*.jpg"))
    scenes = sorted({p.stem.rsplit("_", 1)[0] for p in imgs})
    random.Random(seed).shuffle(scenes)
    val = set(scenes[: max(1, int(len(scenes) * val_frac))])
    tr = [str(p.resolve()) for p in imgs if p.stem.rsplit("_", 1)[0] not in val]
    va = [str(p.resolve()) for p in imgs if p.stem.rsplit("_", 1)[0] in val]
    (data / "train.txt").write_text("\n".join(tr) + "\n")
    (data / "val.txt").write_text("\n".join(va) + "\n")
    names = (data / "classes.txt").read_text().split()
    yaml = data / "dataset.yaml"
    yaml.write_text(f"path: {data.resolve()}\ntrain: train.txt\nval: val.txt\nnames:\n" +
                    "".join(f"  {i}: '{n}'\n" for i, n in enumerate(names)))
    print(f"{len(tr)} images d'entraînement, {len(va)} de validation, {len(names)} classes")
    return yaml


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "out" / "synth")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--model", default="yolo11s-seg.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--name", default="pieces")
    a = ap.parse_args()
    yaml = prepare(a.data)
    from ultralytics import YOLO
    model = YOLO(a.model)
    model.train(data=str(yaml), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device, name=a.name,
                project=str(ROOT / "runs" / "segment"), exist_ok=True, workers=6, patience=15,
                # augmentations : les photos Gemini sont plus réalistes que nos rendus
                hsv_h=0.01, hsv_s=0.5, hsv_v=0.4, degrees=8, scale=0.4, translate=0.1, fliplr=0.5,
                mosaic=0.5, close_mosaic=5, plots=True)


if __name__ == "__main__":
    main()
