"""Palette de couleurs LDraw et correspondance couleur photo -> couleur de brique."""

from __future__ import annotations

import cv2
import numpy as np

# (code LDraw, nom, RGB hex) — valeurs RGB approximatives (référence Rebrickable/BrickLink)
PALETTE: list[tuple[int, str, str]] = [
    (0, "Black", "212121"),
    (1, "Blue", "0055BF"),
    (2, "Green", "237841"),
    (4, "Red", "C91A09"),
    (10, "Bright Green", "4B9F4A"),
    (14, "Yellow", "F2CD37"),
    (15, "White", "F4F4F4"),
    (19, "Tan", "E4CD9E"),
    (25, "Orange", "FE8A18"),
    (27, "Lime", "BBE90B"),
    (28, "Dark Tan", "958A73"),
    (29, "Bright Pink", "E4ADC8"),
    (70, "Reddish Brown", "582A12"),
    (71, "Light Bluish Gray", "A0A5A9"),
    (72, "Dark Bluish Gray", "6C6E68"),
    (73, "Medium Blue", "5A93DB"),
    (84, "Medium Nougat", "AA7D55"),
    (92, "Nougat", "D09168"),
    (272, "Dark Blue", "19325A"),
    (308, "Dark Brown", "352100"),
    (320, "Dark Red", "720E0F"),
    (322, "Medium Azure", "36AEBF"),
    (330, "Olive Green", "9B9A5A"),
    (378, "Sand Green", "A0BCAC"),
    (484, "Dark Orange", "A95500"),
]

# couleurs affichables mais exclues de la reconnaissance photo (transparentes, nacrées)
DISPLAY_ONLY: list[tuple[int, str, str]] = [
    (42, "Trans-Neon Green", "C0FF00"),
    (297, "Pearl Gold", "AA7F2E"),
]

CODES = np.array([c for c, _, _ in PALETTE])
NAMES = {c: n for c, n, _ in PALETTE + DISPLAY_ONLY}
RGB = np.array([[int(h[i:i + 2], 16) for i in (0, 2, 4)] for _, _, h in PALETTE], dtype=np.uint8)
_LAB = cv2.cvtColor(RGB[None, :, ::-1], cv2.COLOR_BGR2LAB)[0].astype(np.float32)

L_WEIGHT = 0.5  # la luminance varie avec l'éclairage : on lui donne moins de poids que la teinte


def nearest_code(bgr: np.ndarray) -> int:
    """Code LDraw le plus proche d'une couleur BGR (uint8)."""
    lab = cv2.cvtColor(np.asarray(bgr, dtype=np.uint8).reshape(1, 1, 3), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    d = (_LAB - lab) * np.array([L_WEIGHT, 1, 1], dtype=np.float32)
    return int(CODES[np.argmin((d ** 2).sum(1))])


def code_bgr(code: int) -> tuple[int, int, int]:
    r, g, b = RGB[list(CODES).index(code)]
    return int(b), int(g), int(r)


def sample(img: np.ndarray, x: float, y: float, radius: float, mask: np.ndarray | None = None) -> np.ndarray | None:
    """Couleur médiane (BGR) d'un disque de l'image, restreint au masque s'il est fourni."""
    h, w = img.shape[:2]
    r = max(1, int(radius))
    x0, x1 = int(max(0, x - r)), int(min(w, x + r + 1))
    y0, y1 = int(max(0, y - r)), int(min(h, y + r + 1))
    if x0 >= x1 or y0 >= y1:
        return None
    patch = img[y0:y1, x0:x1].reshape(-1, 3)
    if mask is not None:
        keep = mask[y0:y1, x0:x1].reshape(-1) > 0
        if keep.sum() < 3:
            return None
        patch = patch[keep]
    return np.median(patch, axis=0).astype(np.uint8)
