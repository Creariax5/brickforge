"""Identification des pièces visibles sur une vue de dessus, à partir des segments SAM.

Pour chaque segment :
- emprise en tenons le long de la grille locale (corps, nageoire… chacun a son angle) ;
- tenons détectés à l'intérieur ;
- couleur médiane (image corrigée de l'éclairage) ;
- dégradé de luminance le long de la grille : une pente apparaît comme une surface dont
  la luminance varie régulièrement dans un sens (l'éclairage frappe différemment la partie
  haute et la partie basse), une tuile ou une plaque comme une surface uniforme.

Règles :
- au moins un tenon                      -> plaque (hauteur inconnue vue de dessus)
- forme ronde                            -> tuile / plaque ronde
- pas de tenon, dégradé fort et courbe   -> pente courbe (profondeur = axe du dégradé)
- pas de tenon, dégradé fort et linéaire -> pente droite
- pas de tenon, uniforme                 -> tuile

Usage :
    python -m brickforge.identify imgs/lego_tortue/dessus.jpeg [--segments out/lego_tortue_dessus_segments.npz]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from . import colors
from .grid import WORK_WIDTH, detect_studs, local_grids, subject_mask
from .views import flatten_lighting

# Pentes courbes sans tenon : (largeur, profondeur le long de la pente) -> référence
CURVED = {(1, 2): "11477", (2, 2): "15068", (1, 3): "50950", (1, 4): "61678", (2, 4): "93606", (1, 6): "42022"}
STRAIGHT = {(1, 1): "54200", (2, 1): "85984", (1, 2): "3040b", (2, 2): "3039", (1, 3): "4286", (3, 3): "4161"}
TILES = {(1, 1): "3070b", (1, 2): "3069b", (1, 3): "63864", (1, 4): "2431", (1, 6): "6636", (1, 8): "4162",
         (2, 2): "3068b", (2, 3): "26603", (2, 4): "87079", (2, 6): "69729"}
PLATES = {(1, 1): "3024", (1, 2): "3023", (1, 3): "3623", (1, 4): "3710", (1, 6): "3666", (1, 8): "3460",
          (2, 2): "3022", (2, 3): "3021", (2, 4): "3020", (2, 6): "3795", (2, 8): "3034"}
ROUND = {(1, 1): "98138", (2, 2): "14769"}


@dataclass
class Piece:
    seg: int                 # indice du segment SAM
    kind: str                # plate | tile | curved | slope | round | unknown
    part: str | None
    color: int
    size: tuple[int, int]    # (largeur, profondeur) ; pour une pente, profondeur = le long de la pente
    footprint: tuple[float, float]  # étendue mesurée (u, v) en tenons, avant arrondi
    center_px: tuple[float, float]
    group: int               # grille locale utilisée
    angle_deg: float         # angle de la grille locale
    n_studs: int
    slope_dir: tuple[float, float] | None  # sens de descente dans l'image (unitaire), si pente
    grad: float              # force du dégradé (unités de luminance par tenon)
    curv: float              # courbure du profil le long du dégradé
    fit_err: float           # écart entre l'emprise mesurée et l'emprise entière retenue
    polygon: list[list[float]] | None = None  # contour, en px de l'image d'origine
    stud_px: float = 0.0     # pas des tenons de la grille locale, en px de l'image d'origine


def _studs_and_grids(img_work: np.ndarray, mask_work: np.ndarray):
    studs = detect_studs(img_work, mask_work)
    r = float(np.median(studs[:, 2]))
    p, groups, labels = local_grids(studs[:, :2], r)
    return studs, r, p, groups, labels


def _is_stud_mask(seg: np.ndarray, area: float, r_stud: float) -> bool:
    """Un segment rond de la taille d'un tenon (SAM isole souvent les tenons)."""
    expected = np.pi * r_stud ** 2
    if not (0.35 * expected < area < 2.2 * expected):
        return False
    cnts, _ = cv2.findContours(seg.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    per = cv2.arcLength(c, True)
    return per > 0 and 4 * np.pi * cv2.contourArea(c) / per ** 2 > 0.7


def _polygon(seg: np.ndarray, scale: float) -> list[list[float]]:
    """Contour simplifié du segment, ramené en px de l'image d'origine."""
    cnts, _ = cv2.findContours(seg.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnts, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, 1.2, True).reshape(-1, 2)
    return [[round(float(x) / scale, 1), round(float(y) / scale, 1)] for x, y in c]


def _label_map(masks: np.ndarray) -> np.ndarray:
    """Carte d'étiquettes sans recouvrement : les petits segments sont peints par-dessus les grands."""
    order = np.argsort([-m.sum() for m in masks])
    lab = -np.ones(masks.shape[1:], int)
    for k in order:
        lab[masks[k]] = k
    return lab


def identify(image: Path, seg_path: Path, out_dir: Path | None = None, stem: str | None = None) -> list[Piece]:
    full = cv2.imread(str(image))
    data = np.load(seg_path)
    masks, s_seg = data["masks"], float(data["scale"])
    img = cv2.resize(full, None, fx=s_seg, fy=s_seg, interpolation=cv2.INTER_AREA)

    # Tenons et grilles locales à la résolution de travail, ramenés à la résolution des segments
    s_work = WORK_WIDTH / full.shape[1]
    img_w = cv2.resize(full, None, fx=s_work, fy=s_work, interpolation=cv2.INTER_AREA)
    mask_w = subject_mask(img_w)
    studs, r_w, p_w, groups, _ = _studs_and_grids(img_w, mask_w)
    k = s_seg / s_work
    stud_xy = studs[:, :2] * k
    r_stud, p = r_w * k, p_w * k
    grids = [{"p": g["p"] * k, "th": g["th"], "origin": g["origin"] * k,
              "pts": studs[g["members"], :2] * k} for g in groups]
    subj = cv2.resize(mask_w, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    col_img = flatten_lighting(img, subj)
    lum = cv2.cvtColor(col_img, cv2.COLOR_BGR2LAB)[:, :, 0].astype(np.float32)

    # 1. Les segments-tenons ne sont pas des pièces : on les retire (les tenons sont déjà détectés)
    areas = masks.reshape(len(masks), -1).sum(1)
    is_stud = np.array([_is_stud_mask(m, a, r_stud) for m, a in zip(masks, areas)])
    lab = _label_map(masks[~is_stud])
    keep_idx = np.nonzero(~is_stud)[0]
    # les pixels des tenons retirés reviennent au segment qui les entoure (fermeture morphologique)
    pieces: list[Piece] = []
    for local, seg_id in enumerate(keep_idx):
        seg = lab == local
        seg = cv2.morphologyEx(seg.astype(np.uint8), cv2.MORPH_CLOSE,
                               cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(2 * r_stud) | 1,) * 2)) > 0
        seg &= (lab == local) | (lab == -1)
        area = seg.sum()
        if area < 0.4 * p * p:          # trop petit pour être une pièce entière (morceau, reflet)
            continue
        ys, xs = np.nonzero(seg)
        cx, cy = xs.mean(), ys.mean()

        # Grille locale : celle dont les tenons sont les plus proches du segment
        gi = min(range(len(grids)), key=lambda g: np.min(np.hypot(*(grids[g]["pts"] - [cx, cy]).T)))
        g = grids[gi]
        c, s = np.cos(g["th"]), np.sin(g["th"])
        u = (xs * c + ys * s) / g["p"]
        v = (-xs * s + ys * c) / g["p"]
        fu, fv = np.ptp(u) + 1 / g["p"], np.ptp(v) + 1 / g["p"]
        wu, wv = max(1, int(round(fu))), max(1, int(round(fv)))
        fit_err = abs(fu - wu) + abs(fv - wv)

        # Tenons à l'intérieur
        inside = seg[np.clip(stud_xy[:, 1].astype(int), 0, seg.shape[0] - 1),
                     np.clip(stud_xy[:, 0].astype(int), 0, seg.shape[1] - 1)]
        n_studs = int(inside.sum())

        # Couleur
        bgr = np.median(col_img[seg], axis=0).astype(np.uint8)
        code = colors.nearest_code(bgr)

        # Dégradé de luminance : plan L = a·u + b·v + c sur le segment (hors tenons)
        L = lum[seg]
        A = np.stack([u - u.mean(), v - v.mean(), np.ones_like(u)], 1)
        coef, *_ = np.linalg.lstsq(A, L, rcond=None)
        a, b = coef[0], coef[1]
        grad = float(np.hypot(a, b))
        # axe du dégradé ramené sur l'axe de grille dominant
        along_u = abs(a) >= abs(b)
        t = (u - u.mean()) if along_u else (v - v.mean())
        q = np.polyfit(t, L, 2) if np.ptp(t) > 0.5 else [0, 0, 0]
        curv = float(q[0])

        # Forme ronde ?
        cnts, _ = cv2.findContours(seg.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cmax = max(cnts, key=cv2.contourArea)
        per = cv2.arcLength(cmax, True)
        circ = 4 * np.pi * cv2.contourArea(cmax) / per ** 2 if per else 0

        slope_dir = None
        if n_studs >= 1:
            kind = "plate"
            size = (min(wu, wv), max(wu, wv))
            part = PLATES.get(size)
        elif circ > 0.82 and wu == wv and wu <= 2:
            kind, size = "round", (wu, wv)
            part = ROUND.get(size)
        elif grad > 6.0:   # luminance (0..255) par tenon
            depth = wu if along_u else wv
            width = wv if along_u else wu
            size = (width, depth)
            # sens de descente : vers le côté sombre (lumière venant du dessus/devant)
            sign = -np.sign(a if along_u else b)
            d_grid = (sign, 0.0) if along_u else (0.0, sign)
            slope_dir = (float(d_grid[0] * c - d_grid[1] * s), float(d_grid[0] * s + d_grid[1] * c))
            if abs(curv) > 2.0 and size in CURVED:
                kind, part = "curved", CURVED[size]
            elif size in STRAIGHT:
                kind, part = "slope", STRAIGHT[size]
            elif size in CURVED:
                kind, part = "curved", CURVED[size]
            else:
                kind, part = "slope", None
        else:
            kind = "tile"
            size = (min(wu, wv), max(wu, wv))
            part = TILES.get(size)
        if part is None:
            kind = kind + "?"

        pieces.append(Piece(seg=int(seg_id), kind=kind, part=part, color=code, size=size,
                            footprint=(round(fu, 2), round(fv, 2)), center_px=(round(cx / s_seg, 1), round(cy / s_seg, 1)),
                            group=gi, angle_deg=round(float(np.rad2deg(g["th"])), 1), n_studs=n_studs,
                            slope_dir=slope_dir, grad=round(grad, 1), curv=round(curv, 2),
                            fit_err=round(fit_err, 2),
                            polygon=_polygon(seg, s_seg), stud_px=round(g["p"] / s_seg, 2)))

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        name = stem or f"{image.parent.name}_{image.stem}_pieces"
        cv2.imwrite(str(out_dir / f"{name}.jpg"), draw(img, lab, keep_idx, pieces, stud_xy, r_stud, s_seg))
        (out_dir / f"{name}.json").write_text(
            json.dumps([asdict(pc) for pc in pieces], ensure_ascii=False, indent=1, default=float))
    return pieces


_KIND_COL = {"plate": (60, 180, 60), "tile": (200, 160, 40), "curved": (40, 120, 255), "slope": (200, 60, 200),
             "round": (0, 200, 220)}


def draw(img, lab, keep_idx, pieces, stud_xy, r_stud, s_draw: float = 1.0) -> np.ndarray:
    big = 2
    vis = cv2.resize((img * 0.55 + 255 * 0.45).astype(np.uint8), None, fx=big, fy=big, interpolation=cv2.INTER_CUBIC)
    local_of = {int(s): i for i, s in enumerate(keep_idx)}
    for pc in pieces:
        seg = (lab == local_of[pc.seg]).astype(np.uint8)
        seg = cv2.resize(seg, (vis.shape[1], vis.shape[0]), interpolation=cv2.INTER_NEAREST)
        col = _KIND_COL.get(pc.kind.rstrip("?"), (0, 0, 255))
        cnts, _ = cv2.findContours(seg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, cnts, -1, col, 2)
        cx, cy = int(pc.center_px[0] * big * s_draw), int(pc.center_px[1] * big * s_draw)
        if pc.slope_dir:
            dx, dy = pc.slope_dir
            cv2.arrowedLine(vis, (cx, cy), (int(cx + dx * 22), int(cy + dy * 22)), col, 2, tipLength=0.4)
        label = f"{pc.part or '?'} {pc.size[0]}x{pc.size[1]}"
        cv2.putText(vis, label, (cx - 28, cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(vis, label, (cx - 28, cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (20, 20, 20), 1, cv2.LINE_AA)
    for x, y in stud_xy:
        cv2.circle(vis, (int(x * big), int(y * big)), int(r_stud * big), (60, 180, 60), 1)
    return vis


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--segments", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out"))
    args = ap.parse_args()
    seg = args.segments or Path("out") / f"{args.image.parent.name}_{args.image.stem}_segments.npz"
    pieces = identify(args.image, seg, args.out)
    from collections import Counter
    print(len(pieces), "pièces :", dict(Counter(p.kind for p in pieces)))
    print("références :", dict(Counter(p.part for p in pieces).most_common()))


if __name__ == "__main__":
    main()
