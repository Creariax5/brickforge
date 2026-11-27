"""Découpage d'une vue en pièces avec SAM (Segment Anything), sans entraînement.

Usage :
    python -m brickforge.segment imgs/lego_tortue/dessus.jpeg [--out out/]

Produit out/<sujet>_<vue>_segments.jpg (masques colorés) et un .npz avec les masques.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from .grid import subject_mask

MODELS = Path(__file__).resolve().parent.parent / "data" / "models"
# MobileSAM (~40 Mo, encodeur TinyViT) : tient sur CPU avec peu de mémoire. SAM vit_b dépasse 3 Go.
CHECKPOINTS = {"mobile": ("vit_t", MODELS / "mobile_sam.pt"),
               "vit_b": ("vit_b", MODELS / "sam_vit_b.pth"),
               "vit_h": ("vit_h", MODELS / "sam_vit_h.pth")}
SAM_WIDTH = 1024  # SAM travaille de toute façon en 1024 px de côté


def segment(img: np.ndarray, mask, points_per_side: int = 48, model: str = "mobile") -> list[dict]:
    import torch

    if model == "mobile":
        from mobile_sam import SamAutomaticMaskGenerator, sam_model_registry
    else:
        from segment_anything import SamAutomaticMaskGenerator, sam_model_registry
    arch, ckpt = CHECKPOINTS[model]
    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    torch.set_num_threads(8)
    if device == "mps":
        # MPS ne gère pas le float64 : SAM convertit ses points en float64 -> on force le float32
        if model == "mobile":
            from mobile_sam.utils.transforms import ResizeLongestSide
        else:
            from segment_anything.utils.transforms import ResizeLongestSide
        _orig = ResizeLongestSide.apply_coords
        if not getattr(_orig, "_f32", False):
            def _apply_coords_f32(self, coords, original_size):
                return _orig(self, coords, original_size).astype(np.float32)
            _apply_coords_f32._f32 = True
            ResizeLongestSide.apply_coords = _apply_coords_f32
    sam = sam_model_registry[arch](checkpoint=str(ckpt)).to(device)
    sam.eval()
    print(f"modèle {model} sur {device}")
    gen = SamAutomaticMaskGenerator(
        sam,
        points_per_side=points_per_side,
        points_per_batch=64 if device != "cpu" else 16,
        pred_iou_thresh=0.86,
        stability_score_thresh=0.9,
        min_mask_region_area=60,
    )
    with torch.inference_mode():
        return gen.generate(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def filter_subject(masks: list[dict], mask: np.ndarray) -> list[dict]:
    # On ne garde que les segments à l'intérieur du sujet, et pas le sujet entier
    area_subject = (mask > 0).sum()
    keep = []
    for m in masks:
        seg = m["segmentation"]
        inside = (mask[seg] > 0).mean()
        if inside > 0.9 and m["area"] < 0.25 * area_subject:
            keep.append(m)
    return keep


def draw(img: np.ndarray, masks: list[dict]) -> np.ndarray:
    vis = (img * 0.35).astype(np.uint8)
    rng = np.random.default_rng(1)
    for m in sorted(masks, key=lambda m: -m["area"]):
        c = rng.integers(60, 255, 3)
        vis[m["segmentation"]] = (0.45 * img[m["segmentation"]] + 0.55 * c).astype(np.uint8)
        cnts, _ = cv2.findContours(m["segmentation"].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, cnts, -1, (255, 255, 255), 1)
    return vis


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--points", type=int, default=48)
    ap.add_argument("--model", choices=list(CHECKPOINTS), default="mobile")
    ap.add_argument("--name", help="préfixe des fichiers de sortie (défaut : <sujet>_<vue>[_modèle])")
    args = ap.parse_args()

    full = cv2.imread(str(args.image))
    s = SAM_WIDTH / max(full.shape[:2])
    img = cv2.resize(full, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    t = time.time()
    masks = segment(img, None, args.points, args.model)
    mask = subject_mask(img)
    masks = filter_subject(masks, mask)
    print(f"{len(masks)} segments en {time.time() - t:.0f} s")

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.name or (f"{args.image.parent.name}_{args.image.stem}" + ("" if args.model == "mobile" else f"_{args.model}"))
    sfx = "" if args.name else "_segments"
    cv2.imwrite(str(args.out / f"{stem}{sfx}.jpg"), draw(img, masks))
    np.savez_compressed(args.out / f"{stem}{sfx}.npz",
                        masks=np.stack([m["segmentation"] for m in masks]) if masks else np.zeros((0,) + img.shape[:2], bool),
                        scale=s)


if __name__ == "__main__":
    main()
