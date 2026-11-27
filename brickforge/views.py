"""Chargement d'un jeu de vues (concept, dessus, profil, face, dos, dessous) et détourage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .grid import WORK_WIDTH, subject_mask

VIEW_NAMES = ("dessus", "profil", "face", "dos", "dessous")


@dataclass
class View:
    name: str
    path: Path
    img: np.ndarray            # image de travail (BGR, largeur WORK_WIDTH)
    mask: np.ndarray           # masque du sujet (uint8 0/255)
    scale: float               # image d'origine -> image de travail
    img_col: np.ndarray = field(init=False)  # image corrigée de l'éclairage, pour les couleurs
    bbox: tuple[int, int, int, int] = field(init=False)  # x0, y0, x1, y1 du masque

    def __post_init__(self) -> None:
        ys, xs = np.nonzero(self.mask)
        self.bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        self.img_col = flatten_lighting(self.img, self.mask)


def flatten_lighting(img: np.ndarray, mask: np.ndarray, target: float = 235.0) -> np.ndarray:
    """Compense un éclairage non uniforme : on ajuste un polynôme de degré 2 en (x, y) sur les
    pixels du fond (supposé blanc et uniforme), canal par canal, puis on divise l'image par ce champ."""
    h, w = mask.shape
    far = cv2.dilate(mask, np.ones((31, 31), np.uint8)) == 0
    ys, xs = np.nonzero(far)
    if len(xs) < 1000:
        return img.copy()
    idx = np.random.default_rng(0).choice(len(xs), size=min(20000, len(xs)), replace=False)
    xs, ys = xs[idx] / w, ys[idx] / h

    def basis(x, y):
        return np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], axis=-1)

    A = basis(xs, ys)
    gx, gy = np.meshgrid(np.arange(w) / w, np.arange(h) / h)
    B = basis(gx, gy)
    px, py = (xs * w).astype(int), (ys * h).astype(int)
    out = np.empty(img.shape, np.float32)
    for c in range(3):
        coef, *_ = np.linalg.lstsq(A, img[py, px, c].astype(np.float32), rcond=None)
        field_c = np.clip(B @ coef, 30, 255)
        out[..., c] = img[..., c] * (target / field_c)
    return np.clip(out, 0, 255).astype(np.uint8)


def load_view(path: Path, name: str) -> View:
    full = cv2.imread(str(path))
    if full is None:
        raise FileNotFoundError(path)
    scale = WORK_WIDTH / full.shape[1]
    img = cv2.resize(full, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return View(name=name, path=path, img=img, mask=subject_mask(img), scale=scale)


def load_subject(folder: Path) -> dict[str, View]:
    views = {}
    for name in VIEW_NAMES:
        for ext in (".jpeg", ".jpg", ".png", ".webp"):
            p = folder / f"{name}{ext}"
            if p.exists():
                views[name] = load_view(p, name)
                break
    return views
