"""Estimation de la grille de tenons sur une vue (dessus ou dessous) d'un modèle en briques.

Étapes :
1. détourage du sujet (rembg) ;
2. détection des tenons (cercles) dans le masque ;
3. regroupement des tenons en grilles locales : chaque sous-ensemble (corps, nageoire,
   tête…) peut être tourné, donc on cherche un réseau carré (pas, angle, origine) par groupe ;
4. dimensions du sujet exprimées en tenons, le long de la grille du groupe principal.

Usage :
    python -m brickforge.grid imgs/lego_tortue/dessus.jpeg [--out out/]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

WORK_WIDTH = 1600  # largeur de travail en px (les images sont réduites pour la vitesse)


@dataclass
class LocalGrid:
    n_studs: int
    pitch_px: float          # pas des tenons, px de l'image d'origine
    angle_deg: float         # orientation du réseau, dans [0, 90)
    origin_px: tuple[float, float]
    centroid_px: tuple[float, float]
    residual: float          # écart moyen des tenons aux nœuds, en fraction de pas


@dataclass
class GridEstimate:
    image: str
    pitch_px: float          # pas global (médiane), px de l'image d'origine
    stud_radius_px: float
    n_studs: int             # tenons détectés
    n_assigned: int          # tenons rattachés à une grille locale
    groups: list[LocalGrid]  # triés par nombre de tenons décroissant
    main_group: int          # index du groupe principal (le plus proche du centre du sujet)
    size_studs: tuple[float, float]  # étendue du sujet le long des axes du groupe principal


# ---------------------------------------------------------------- détourage

_REMBG_SESSION = None


def subject_mask(img: np.ndarray) -> np.ndarray:
    """Masque binaire du sujet, par détourage neuronal (rembg, modèle isnet-general-use)."""
    global _REMBG_SESSION
    from rembg import new_session, remove  # import paresseux : chargement du modèle ~1 s

    if _REMBG_SESSION is None:
        _REMBG_SESSION = new_session("isnet-general-use")
    alpha = remove(img, session=_REMBG_SESSION, only_mask=True)
    mask = (np.asarray(alpha) > 128).astype(np.uint8) * 255
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n > 2:  # garder les composantes significatives (>2 % de la plus grande)
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = 1 + np.nonzero(areas > 0.02 * areas.max())[0]
        mask = np.isin(labels, keep).astype(np.uint8) * 255
    return mask


# ---------------------------------------------------------------- tenons

def detect_studs(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Centres et rayons (N, 3) des cercles candidats à l'intérieur du masque."""
    ys, xs = np.nonzero(mask)
    extent = max(xs.max() - xs.min(), ys.max() - ys.min())
    r_min = max(4, int(extent / 120))
    r_max = max(r_min + 2, int(extent / 30))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray = cv2.GaussianBlur(gray, (5, 5), 1.2)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT_ALT, dp=1.5, minDist=r_min * 2,
                               param1=150, param2=0.6, minRadius=r_min, maxRadius=r_max)
    if circles is None:
        return np.empty((0, 3))
    c = circles[0]
    inside = mask[c[:, 1].astype(int).clip(0, mask.shape[0] - 1),
                  c[:, 0].astype(int).clip(0, mask.shape[1] - 1)] > 0
    c = c[inside]
    if len(c) < 6:
        return c
    # Les tenons ont tous le même rayon : on garde le mode de la distribution des rayons
    hist, edges = np.histogram(c[:, 2], bins=np.arange(r_min, r_max + 2, 1.0))
    smooth = np.convolve(hist, np.ones(3), mode="same")
    r_mode = edges[int(np.argmax(smooth))] + 0.5
    return c[np.abs(c[:, 2] - r_mode) < 0.25 * r_mode]


# ---------------------------------------------------------------- grilles locales

ADJ_TOL = 0.22   # tolérance sur la distance entre tenons voisins (fraction de pas)
NODE_TOL = 0.25  # tolérance d'appartenance d'un tenon à un réseau (fraction de pas)


def _angle90(vecs: np.ndarray) -> np.ndarray:
    """Angle de vecteurs ramené dans [0, 90°) (symétrie du réseau carré), en radians."""
    return np.mod(np.arctan2(vecs[:, 1], vecs[:, 0]), np.pi / 2)


def _mean_angle90(angles: np.ndarray) -> float:
    """Moyenne circulaire d'angles définis modulo 90°."""
    z = np.mean(np.exp(4j * angles))
    return float(np.mod(np.angle(z) / 4, np.pi / 2))


def _lattice_coords(pts: np.ndarray, p: float, th: float, origin: np.ndarray) -> np.ndarray:
    c, s = np.cos(th), np.sin(th)
    rel = pts - origin
    return np.stack([(rel[:, 0] * c + rel[:, 1] * s) / p, (-rel[:, 0] * s + rel[:, 1] * c) / p], axis=1)


def _fit_group(pts: np.ndarray, p: float, th: float) -> tuple[float, float, np.ndarray, float]:
    """Affine (pas, angle, origine) par moindres carrés une fois les indices de nœuds connus."""
    origin = pts[0].copy()
    for _ in range(3):
        uv = _lattice_coords(pts, p, th, origin)
        ij = np.round(uv)
        if len(np.unique(ij, axis=0)) < 2:
            break
        # pts ≈ origin + p·R(θ)·ij  → modèle linéaire en (ox, oy, a=p·cosθ, b=p·sinθ)
        A = np.zeros((2 * len(pts), 4))
        A[0::2, 0] = 1; A[0::2, 2] = ij[:, 0]; A[0::2, 3] = -ij[:, 1]
        A[1::2, 1] = 1; A[1::2, 2] = ij[:, 1]; A[1::2, 3] = ij[:, 0]
        sol, *_ = np.linalg.lstsq(A, pts.reshape(-1), rcond=None)
        origin = sol[:2]
        p, th = float(np.hypot(sol[2], sol[3])), float(np.arctan2(sol[3], sol[2]))
    uv = _lattice_coords(pts, p, th, origin)
    resid = float(np.mean(np.linalg.norm(uv - np.round(uv), axis=1)))
    # ramener θ dans [0, 90°) en choisissant l'axe correspondant
    return p, float(np.mod(th, np.pi / 2)), origin, resid


def local_grids(centers: np.ndarray, r_stud: float) -> tuple[float, list[dict], np.ndarray]:
    """Regroupe les tenons en grilles locales.

    1. pas initial p ≈ r / 0,3 (diamètre tenon 4,8 mm pour un pas de 8 mm), affiné sur les voisins ;
    2. arêtes entre tenons adjacents (distance ≈ p) ou diagonaux (≈ p√2) ;
    3. composantes connexes → petits groupes, angle par moyenne circulaire ;
    4. fusion des groupes compatibles (même angle, mêmes nœuds de réseau, proches) ;
    5. rattachement des tenons isolés qui tombent sur un réseau voisin.
    Retourne (pas global, groupes, label par tenon (-1 = non rattaché)).
    """
    n = len(centers)
    d = centers[:, None, :] - centers[None, :, :]
    dist = np.linalg.norm(d, axis=2)
    np.fill_diagonal(dist, np.inf)

    p0 = r_stud / 0.3
    nn = dist.min(axis=1)
    near = nn[(nn > 0.75 * p0) & (nn < 1.3 * p0)]
    p = float(np.median(near)) if len(near) >= 3 else p0

    adj = np.abs(dist - p) < ADJ_TOL * p
    diag = np.abs(dist - p * np.sqrt(2)) < ADJ_TOL * p * np.sqrt(2)
    edges = adj | diag

    # Composantes connexes (parcours en largeur), en n'acceptant une arête que si son angle
    # est cohérent avec celui déjà estimé pour le groupe
    labels = -np.ones(n, dtype=int)
    groups: list[list[int]] = []
    for seed in range(n):
        if labels[seed] >= 0 or not edges[seed].any():
            continue
        gid = len(groups)
        members, queue, angs = [seed], [seed], []
        labels[seed] = gid
        while queue:
            i = queue.pop()
            for j in np.nonzero(edges[i])[0]:
                if labels[j] >= 0:
                    continue
                a = _angle90(d[j, i][None])[0]
                if diag[i, j]:
                    a = np.mod(a - np.pi / 4, np.pi / 2)
                if angs:
                    ref = _mean_angle90(np.array(angs))
                    diff = abs((a - ref + np.pi / 4) % (np.pi / 2) - np.pi / 4)
                    if diff > np.deg2rad(12):
                        continue
                angs.append(a)
                labels[j] = gid
                members.append(j)
                queue.append(j)
        groups.append(members)

    fitted = []
    for members in groups:
        pts = centers[members]
        if len(members) >= 2:
            sub = d[np.ix_(members, members)][adj[np.ix_(members, members)]]
            th = _mean_angle90(_angle90(sub)) if len(sub) else 0.0
        else:
            th = 0.0
        gp, gth, go, res = _fit_group(pts, p, th) if len(members) >= 2 else (p, 0.0, pts[0], 0.0)
        fitted.append({"members": list(members), "p": gp, "th": gth, "origin": go, "res": res})

    # Fusion : du plus gros au plus petit
    fitted.sort(key=lambda g: -len(g["members"]))
    merged: list[dict] = []
    for g in fitted:
        pts_g = centers[g["members"]]
        for m in merged:
            dth = abs((g["th"] - m["th"] + np.pi / 4) % (np.pi / 2) - np.pi / 4)
            if dth > np.deg2rad(8):
                continue
            gap = np.min(np.linalg.norm(pts_g[:, None] - centers[m["members"]][None], axis=2))
            if gap > 6 * p:
                continue
            uv = _lattice_coords(pts_g, m["p"], m["th"], m["origin"])
            if np.all(np.abs(uv - np.round(uv)) < NODE_TOL):
                m["members"] += g["members"]
                m["p"], m["th"], m["origin"], m["res"] = _fit_group(centers[m["members"]], m["p"], m["th"])
                break
        else:
            merged.append(g)

    # Les groupes d'un seul tenon ne définissent pas de grille : on les rattache ou on les écarte
    real = [g for g in merged if len(g["members"]) >= 2]
    labels = -np.ones(n, dtype=int)
    for k, g in enumerate(real):
        labels[g["members"]] = k
    for i in np.nonzero(labels < 0)[0]:
        for k, g in enumerate(real):
            if np.min(np.linalg.norm(centers[g["members"]] - centers[i], axis=1)) > 3 * p:
                continue
            uv = _lattice_coords(centers[i][None], g["p"], g["th"], g["origin"])
            if np.all(np.abs(uv - np.round(uv)) < NODE_TOL):
                g["members"].append(int(i))
                labels[i] = k
                break
    return p, real, labels


def extent_in_lattice(mask: np.ndarray, p: float, th: float) -> tuple[float, float]:
    ys, xs = np.nonzero(mask)
    c, s = np.cos(th), np.sin(th)
    u = xs * c + ys * s
    v = -xs * s + ys * c
    return float((u.max() - u.min()) / p), float((v.max() - v.min()) / p)


# ---------------------------------------------------------------- pipeline

def estimate_grid(path: Path, out_dir: Path | None = None) -> GridEstimate:
    full = cv2.imread(str(path))
    if full is None:
        raise FileNotFoundError(path)
    scale = WORK_WIDTH / full.shape[1]
    img = cv2.resize(full, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    mask = subject_mask(img)
    studs = detect_studs(img, mask)
    if len(studs) < 4:
        raise RuntimeError(f"{path}: trop peu de tenons détectés ({len(studs)})")
    centers = studs[:, :2]
    r_stud = float(np.median(studs[:, 2]))
    p, groups, labels = local_grids(centers, r_stud)
    if not groups:
        raise RuntimeError(f"{path}: aucune grille locale trouvée")

    # Groupe principal : parmi les groupes d'au moins 3 tenons, le plus proche du centre du sujet
    ys, xs = np.nonzero(mask)
    center = np.array([xs.mean(), ys.mean()])
    cand = [k for k, g in enumerate(groups) if len(g["members"]) >= 3] or list(range(len(groups)))
    main = min(cand, key=lambda k: np.linalg.norm(centers[groups[k]["members"]].mean(0) - center))
    g0 = groups[main]
    su, sv = extent_in_lattice(mask, g0["p"], g0["th"])

    def to_full(v):
        return (round(float(v[0] / scale), 1), round(float(v[1] / scale), 1))

    est = GridEstimate(
        image=str(path), pitch_px=round(p / scale, 2), stud_radius_px=round(r_stud / scale, 2),
        n_studs=len(centers), n_assigned=int((labels >= 0).sum()),
        groups=[LocalGrid(n_studs=len(g["members"]), pitch_px=round(g["p"] / scale, 2),
                          angle_deg=round(float(np.rad2deg(g["th"])), 1), origin_px=to_full(g["origin"]),
                          centroid_px=to_full(centers[g["members"]].mean(0)), residual=round(g["res"], 3))
                for g in groups],
        main_group=main, size_studs=(round(su, 1), round(sv, 1)),
    )

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_dir / f"{path.parent.name}_{path.stem}_grid.jpg"),
                    draw_overlay(img, mask, studs, labels, groups, main))
    return est


_PALETTE = [(0, 200, 0), (255, 140, 0), (200, 0, 200), (0, 200, 255), (255, 0, 100),
            (120, 120, 255), (0, 120, 120), (180, 180, 0)]


def draw_overlay(img, mask, studs, labels, groups, main) -> np.ndarray:
    vis = img.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(vis, contours, -1, (255, 0, 255), 2)
    overlay = vis.copy()
    for k, g in enumerate(groups):
        col = _PALETTE[k % len(_PALETTE)]
        p, th, o = g["p"], g["th"], g["origin"]
        pts = studs[g["members"], :2]
        uv = _lattice_coords(pts, p, th, o)
        lo, hi = np.floor(uv.min(0)) - 1, np.ceil(uv.max(0)) + 1
        if k == main:  # grille du groupe principal étendue à tout le sujet
            lo, hi = lo - 12, hi + 12
        c, s = np.cos(th), np.sin(th)
        eu, ev = np.array([c, s]), np.array([-s, c])
        for i in np.arange(lo[0], hi[0] + 1):
            a = o + p * ((i - 0.5) * eu + (lo[1] - 0.5) * ev)
            b = o + p * ((i - 0.5) * eu + (hi[1] - 0.5) * ev)
            cv2.line(overlay, tuple(a.astype(int)), tuple(b.astype(int)), col, 1)
        for j in np.arange(lo[1], hi[1] + 1):
            a = o + p * ((lo[0] - 0.5) * eu + (j - 0.5) * ev)
            b = o + p * ((hi[0] - 0.5) * eu + (j - 0.5) * ev)
            cv2.line(overlay, tuple(a.astype(int)), tuple(b.astype(int)), col, 1)
    vis = cv2.addWeighted(overlay, 0.45, vis, 0.55, 0)
    for (x, y, r), lab in zip(studs, labels):
        col = _PALETTE[lab % len(_PALETTE)] if lab >= 0 else (0, 0, 255)
        cv2.circle(vis, (int(x), int(y)), int(r), col, 2 if lab >= 0 else 1)
    return vis


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out"))
    args = ap.parse_args()
    for path in args.images:
        try:
            est = estimate_grid(path, args.out)
            print(json.dumps(asdict(est), ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"image": str(path), "error": str(e)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
