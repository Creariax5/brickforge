"""Générateur de données synthétiques pour entraîner un détecteur de pièces.

Chaque scène :
1. une forme aléatoire (union d'ellipsoïdes et de boîtes, posée au sol) ;
2. un assemblage VALIDE construit dedans par le moteur d'emboîtement (pièces sur des tenons libres) ;
3. une palette de 3 à 6 couleurs LEGO, attribuée par zones (bandes, côtés, aléatoire) ;
4. plusieurs rendus (caméra, éclairage, fond, flou, bruit aléatoires) avec, pour chaque pixel,
   l'indice de la pièce visible -> étiquettes de segmentation d'instances gratuites.

Sortie (format YOLO-seg) :
  out/synth/images/<id>.jpg   out/synth/labels/<id>.txt   out/synth/meta/<id>.json   out/synth/classes.txt

Usage : python -m brickforge.synth --scenes 20 --views 4 [--seed 0] [--out out/synth] [--size 640]
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

from . import colors
from .builder import Builder, PARTS
from .compare import camera_basis, project
from .ldlib import part_triangles
from .target import Target
from .zraster import raster

ROOT = Path(__file__).resolve().parent.parent
CLASSES = PARTS                                   # une classe par référence de pièce
COLOR_POOL = [0, 1, 2, 4, 14, 15, 19, 25, 28, 70, 71, 72, 84, 92, 308, 320, 322, 330, 378, 484, 27, 29, 73, 10]


# ------------------------------------------------------------------ formes aléatoires

def random_shape(rng, size=(26, 26, 18)) -> np.ndarray:
    I, J, K = size
    ii, jj, kk = np.meshgrid(np.arange(I) + 0.5, np.arange(J) + 0.5, (np.arange(K) + 0.5) * 0.4, indexing="ij")
    f = np.zeros(size, np.float32)
    for _ in range(rng.integers(1, 5)):
        c = np.array([rng.uniform(7, I - 7), rng.uniform(7, J - 7), rng.uniform(0.5, 4.5)])
        r = np.array([rng.uniform(2.5, 8), rng.uniform(2.5, 8), rng.uniform(1.5, 5.5)])
        if rng.random() < 0.7:
            d = ((ii - c[0]) / r[0]) ** 2 + ((jj - c[1]) / r[1]) ** 2 + ((kk - c[2]) / r[2]) ** 2
            f = np.maximum(f, np.clip(1.5 - d, 0, 1))
        else:
            d = np.maximum.reduce([np.abs(ii - c[0]) / r[0], np.abs(jj - c[1]) / r[1], np.abs(kk - c[2]) / r[2]])
            f = np.maximum(f, np.clip((1.2 - d) * 3, 0, 1))
    f[:, :, 0] = np.maximum(f[:, :, 0], f[:, :, 1] * (rng.random() < 0.5))   # appui au sol
    return f


def build_scene(rng) -> list[dict]:
    frac = random_shape(rng)
    t = Target(frac=frac, x0=-260.0, z0=-260.0, center=np.zeros(3), cams={}, views={})
    import brickforge.builder as B
    # variété : on fait varier les réglages du constructeur d'une scène à l'autre
    B.PIECE_COST = float(rng.uniform(0.15, 0.6))
    B.STUD_SHOWN = float(rng.uniform(0.0, 0.8))
    b = Builder(t, log=lambda *a: None)
    b.run(max_parts=int(rng.integers(30, 160)))
    return b.placed


def build_scene_random(rng) -> list[dict]:
    """Assemblage « en vrac » équilibré : à chaque pas on tire une pièce (les moins vues d'abord),
    une orientation, et une position valide au hasard (emboîtée sur un tenon libre, sans collision),
    en restant compact autour du centre. Toutes les références apparaissent autant."""
    from scipy.signal import correlate
    I, J, K = 22, 22, 16
    frac = np.ones((I, J, K), np.float32)
    t = Target(frac=frac, x0=-220.0, z0=-220.0, center=np.zeros(3), cams={}, views={})
    b = Builder(t, log=lambda *a: None)
    b.studs[:] = False
    # base : une plaque au sol au centre
    base = [k for k in b.kernels if k.part in ("3020", "3032", "3031", "3034", "3795")]
    kb = base[int(rng.integers(len(base)))]
    b.studs[:, :, 0] = True
    b.place(kb, (I // 2 - kb.shape[0] // 2, J // 2 - kb.shape[1] // 2, 0))
    b.studs[:, :, 0] = False
    n_target = int(rng.integers(25, 90))
    by_part = {}
    for k in b.kernels:
        by_part.setdefault(k.part, []).append(k)
    names = list(by_part)
    ii, jj = np.meshgrid(np.arange(I), np.arange(J), indexing="ij")
    tries = 0
    while len(b.placed) < n_target and tries < n_target * 6:
        tries += 1
        w = np.array([1.0 / (1 + SEEN.get(n, 0)) for n in names])
        part = names[int(rng.choice(len(names), p=w / w.sum()))]
        kn = by_part[part][int(rng.integers(len(by_part[part])))]
        X, Z, Kk = kn.shape
        if X > I or Z > J or Kk > K:
            continue
        coll = correlate(b.occupied.astype(np.float32), kn.solid.astype(np.float32), mode="valid") > 0.5
        fem = np.zeros((X, Z, 1), np.float32)
        fem[:, :, 0] = kn.female
        sup = correlate(b.studs[:, :, :K - Kk + 1].astype(np.float32), fem, mode="valid") > 0.5
        ok = sup & ~coll[:, :, :sup.shape[2]]
        cand = np.argwhere(ok)
        if not len(cand):
            continue
        # compacité : on préfère les positions proches du centre et pas trop hautes
        d = np.hypot(cand[:, 0] + X / 2 - I / 2, cand[:, 1] + Z / 2 - J / 2) + 0.3 * cand[:, 2]
        pw = np.exp(-d / 3.0)
        c = cand[int(rng.choice(len(cand), p=pw / pw.sum()))]
        b.place(kn, tuple(int(v) for v in c))
        SEEN[part] = SEEN.get(part, 0) + 1
    return b.placed


SEEN: dict[str, int] = {}


def paint(placed, rng):
    pal = list(rng.choice(COLOR_POOL, size=int(rng.integers(3, 7)), replace=False))
    mode = rng.integers(0, 3)
    for p in placed:
        i, j, k = p["cell"]
        if mode == 0:                         # bandes horizontales
            c = pal[(k // 3) % len(pal)]
        elif mode == 1:                       # bandes selon x
            c = pal[(i // 2) % len(pal)]
        else:
            c = pal[int(rng.integers(len(pal)))]
        p["color"] = int(c)


# ------------------------------------------------------------------ rendu avec carte d'instances

_tri_cache: dict[str, np.ndarray] = {}


def scene_triangles(placed):
    tris, owner, cols = [], [], []
    for n, p in enumerate(placed):
        if p["part"] not in _tri_cache:
            _tri_cache[p["part"]] = part_triangles(p["part"]).astype(np.float32)
        t = _tri_cache[p["part"]]
        R = np.array(p["m"][3:], np.float32).reshape(3, 3)
        w = t @ R.T + np.array(p["m"][:3], np.float32)
        w[..., 1] *= -1                       # Y vers le haut
        tris.append(w)
        owner.append(np.full(len(w), n, np.int32))
        cols.append(np.repeat(np.array([colors.code_bgr(p["color"])], np.float32), len(w), 0))
    tris = np.concatenate(tris)
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    return tris, np.concatenate(owner), np.concatenate(cols), nrm


def background(rng, H, W):
    base = rng.uniform(185, 250)                              # fonds blancs / gris clair, légère teinte
    top = np.clip(base + rng.normal(0, 6, 3), 0, 255)
    bot = np.clip(top + rng.uniform(-35, 10) + rng.normal(0, 4, 3), 0, 255)
    g = np.linspace(0, 1, H)[:, None, None]
    img = (top * (1 - g) + bot * g).astype(np.float32)
    img = np.repeat(img, W, 1)
    if rng.random() < 0.5:                    # table : bande plus claire en bas
        y0 = int(H * rng.uniform(0.45, 0.7))
        img[y0:] = np.clip(img[y0:] * rng.uniform(1.0, 1.12), 0, 255)
    return img


def render_view(scene, cam, size, center, rng):
    tris, owner, cols, nrm = scene
    W, H = size
    x, y, z = project(tris.reshape(-1, 3), cam, size, center)
    tid = raster(x.reshape(-1, 3), y.reshape(-1, 3), z.reshape(-1, 3), W, H)
    d, f, right, up = camera_basis(cam["az"], cam["el"], cam["roll"])
    light = -f * rng.uniform(0.2, 0.8) + up * rng.uniform(0.4, 1.0) + right * rng.uniform(-0.6, 0.6)
    light /= np.linalg.norm(light)
    amb = rng.uniform(0.45, 0.65)
    shade = amb + (1 - amb) * np.abs(nrm @ light)
    img = background(rng, H, W)
    fg = tid >= 0
    inst = np.where(fg, owner[np.maximum(tid, 0)], -1).astype(np.int32)
    img[fg] = np.clip(cols[tid[fg]] * shade[tid[fg], None], 0, 255)
    # interstices sombres entre les pièces (comme sur les photos)
    edge = (cv2.morphologyEx(inst.astype(np.float32), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0) & (inst >= 0)
    img[edge] *= rng.uniform(0.55, 0.8)
    # ombre douce au sol
    m = (inst >= 0).astype(np.float32)
    sh = cv2.GaussianBlur(m, (0, 0), rng.uniform(4, 12))
    sh = np.roll(sh, int(rng.uniform(2, 10)), axis=0)
    img = img * (1 - 0.25 * sh[..., None] * (1 - m[..., None]))
    # optique : flou, bruit, balance des blancs
    if rng.random() < 0.6:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.3, 1.2))
    img = img * rng.uniform(0.92, 1.08, 3) + rng.normal(0, rng.uniform(1, 5), img.shape)
    return np.clip(img, 0, 255).astype(np.uint8), inst


def random_camera(rng, radius):
    el = rng.uniform(-10, 85) if rng.random() < 0.9 else rng.uniform(-85, -40)
    return {"az": rng.uniform(0, 360), "el": el, "roll": rng.normal(0, 3), "focal": rng.uniform(1.2, 2.6),
            "dist": radius * rng.uniform(4.5, 7.5), "sx": rng.normal(0, 0.04), "sy": rng.normal(0, 0.04)}


def frame(scene, cam, size, center, rng):
    """Cadre le sujet comme sur les vues Gemini : il occupe 55 à 90 % de la plus grande dimension."""
    W, H = size
    v = scene[0].reshape(-1, 3)[::7]
    for it in range(2):
        x, y, _z = project(v, cam, size, center)
        w = max(x.max() - x.min(), y.max() - y.min()) / max(W, H)
        if it == 0:
            cam["focal"] *= rng.uniform(0.55, 0.9) / max(w, 1e-3)
        x, y, _z = project(v, cam, size, center)
        cam["sx"] += (W / 2 - (x.max() + x.min()) / 2) / W + rng.normal(0, 0.03)
        cam["sy"] += (H / 2 - (y.max() + y.min()) / 2) / H + rng.normal(0, 0.03)


def yolo_labels(inst, placed, min_px=40):
    H, W = inst.shape
    lines, objs = [], []
    for n in np.unique(inst):
        if n < 0:
            continue
        m = (inst == n).astype(np.uint8)
        area = int(m.sum())
        if area < min_px:
            continue
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cnts, key=cv2.contourArea)
        if len(c) < 3:
            continue
        c = cv2.approxPolyDP(c, 1.0, True).reshape(-1, 2)
        if len(c) < 3:
            continue
        p = placed[n]
        cls = CLASSES.index(p["part"])
        coords = " ".join(f"{x / W:.4f} {y / H:.4f}" for x, y in c)
        lines.append(f"{cls} {coords}")
        objs.append({"inst": int(n), "part": p["part"], "color": p["color"], "q": p["q"], "area": area})
    return lines, objs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenes", type=int, default=20)
    ap.add_argument("--views", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "synth")
    ap.add_argument("--size", type=int, default=640)
    a = ap.parse_args()
    for d in ("images", "labels", "meta"):
        (a.out / d).mkdir(parents=True, exist_ok=True)
    (a.out / "classes.txt").write_text("\n".join(CLASSES) + "\n")
    rng = np.random.default_rng(a.seed)
    t0, n_img = time.time(), 0
    for s in range(a.scenes):
        # moitié formes « sculptées » (style modèle), moitié assemblages équilibrés (toutes les pièces)
        placed = build_scene(rng) if rng.random() < 0.5 else build_scene_random(rng)
        if len(placed) < 5:
            continue
        paint(placed, rng)
        scene = scene_triangles(placed)
        v = scene[0].reshape(-1, 3)
        center = (v.min(0) + v.max(0)) / 2
        radius = float(np.linalg.norm(v.max(0) - v.min(0)) / 2)
        for vi in range(a.views):
            cam = random_camera(rng, radius)
            H = W = a.size
            frame(scene, cam, (W, H), center, rng)
            img, inst = render_view(scene, cam, (W, H), center, rng)
            lines, objs = yolo_labels(inst, placed)
            if not lines:
                continue
            sid = f"{a.seed:03d}_{s:05d}_{vi}"
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(70, 95))])
            (a.out / "images" / f"{sid}.jpg").write_bytes(buf.tobytes())
            (a.out / "labels" / f"{sid}.txt").write_text("\n".join(lines) + "\n")
            (a.out / "meta" / f"{sid}.json").write_text(json.dumps({"camera": cam, "objects": objs}))
            n_img += 1
        print(f"scène {s + 1}/{a.scenes} : {len(placed)} pièces, {n_img} images ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
