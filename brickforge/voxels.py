"""Reconstruction naïve en voxels (1 tenon × 1 tenon × 1 plaque) à partir des vues.

Principe (enveloppe visuelle) :
- la vue de DESSUS fixe la grille (pas, angle) et l'emprise au sol : quelles colonnes existent ;
- le PROFIL donne, pour chaque position le long du corps, la hauteur haute/basse de la silhouette ;
- la FACE donne la même chose pour chaque position en largeur ;
- un voxel est plein s'il est dans l'emprise du dessus ET dans les deux intervalles de hauteur.

Couleurs : voxel du dessus -> vue de dessus ; flancs -> profil (symétrie gauche/droite) ;
avant -> face ; arrière -> dos ; dessous -> vue de dessous.

Conventions d'image attendues :
- dessus / dessous : tête vers le haut de l'image ;
- profil : tête vers la droite (sinon --profil-tete gauche) ;
- face : le sujet regarde l'objectif.

Repère de la grille : i = largeur (x image du dessus), j = longueur (0 = tête), k = hauteur en plaques.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import colors
from .grid import detect_studs, local_grids
from .views import View

PLATES_PER_STUD = 20 / 8  # 1 pas de tenon = 20 LDU, 1 plaque = 8 LDU


@dataclass
class TopGrid:
    p: float               # pas en px (image de travail)
    th: float              # angle, dans [-45°, 45°) en radians
    origin: np.ndarray     # centre de la cellule (0, 0) en px
    occ: np.ndarray        # (W, L) bool : emprise au sol
    i0: int                # indice de grille de la colonne occ[0, :]
    j0: int

    def center(self, i: int, j: int) -> np.ndarray:
        c, s = np.cos(self.th), np.sin(self.th)
        eu, ev = np.array([c, s]), np.array([-s, c])
        return self.origin + self.p * ((i + self.i0) * eu + (j + self.j0) * ev)


def top_grid(top: View, min_fill: float = 0.5) -> TopGrid:
    studs = detect_studs(top.img, top.mask)
    if len(studs) < 4:
        raise RuntimeError("vue de dessus : trop peu de tenons détectés")
    centers = studs[:, :2]
    p_global, groups, _ = local_grids(centers, float(np.median(studs[:, 2])))
    if not groups:
        raise RuntimeError("vue de dessus : aucune grille trouvée")
    # Orientation et origine : groupe principal (le plus proche du centre parmi ceux d'au moins 3 tenons)
    ys, xs = np.nonzero(top.mask)
    center = np.array([xs.mean(), ys.mean()])
    cand = [g for g in groups if len(g["members"]) >= 3] or groups
    g0 = min(cand, key=lambda g: np.linalg.norm(centers[g["members"]].mean(0) - center))
    th = g0["th"] if g0["th"] < np.pi / 4 else g0["th"] - np.pi / 2
    # Pas : médiane globale (compromis entre le haut du modèle, plus proche de l'objectif, et le bas)
    p = p_global
    origin = g0["origin"]

    c, s = np.cos(th), np.sin(th)
    rel = np.stack([xs, ys], 1) - origin
    u = np.round((rel[:, 0] * c + rel[:, 1] * s) / p).astype(int)
    v = np.round((-rel[:, 0] * s + rel[:, 1] * c) / p).astype(int)
    i0, j0 = u.min(), v.min()
    counts = np.zeros((u.max() - i0 + 1, v.max() - j0 + 1))
    np.add.at(counts, (u - i0, v - j0), 1)
    occ = counts / (p * p) >= min_fill
    # Recadrer sur les cellules occupées
    ii, jj = np.nonzero(occ)
    occ = occ[ii.min():ii.max() + 1, jj.min():jj.max() + 1]
    return TopGrid(p=p, th=th, origin=origin, occ=occ, i0=int(i0 + ii.min()), j0=int(j0 + jj.min()))


def _silhouette_profile(view: View, n_cells: int, reverse: bool) -> tuple[np.ndarray, np.ndarray, float]:
    """Pour chaque cellule le long de l'axe horizontal de la vue : (haut, bas) de la silhouette,
    en tenons au-dessus du sol, et l'échelle (tenons / px)."""
    x0, y0, x1, y1 = view.bbox
    s = n_cells / (x1 - x0 + 1)          # tenons par px
    ground = y1
    top = np.zeros(n_cells)
    bot = np.zeros(n_cells)
    for c in range(n_cells):
        t = (c + 0.5) / n_cells
        xc = x1 - t * (x1 - x0) if reverse else x0 + t * (x1 - x0)
        half = max(1, int(0.25 / s))
        cols = view.mask[:, int(max(0, xc - half)):int(xc + half + 1)]
        tops, bots = [], []
        for col in cols.T:
            ys = np.nonzero(col)[0]
            if len(ys):
                tops.append(ys.min())
                bots.append(ys.max())
        if tops:
            top[c] = (ground - np.median(tops)) * s
            bot[c] = (ground - np.median(bots)) * s
    return top, bot, s


@dataclass
class VoxelModel:
    color: np.ndarray      # (W, L, H) int : code LDraw, -1 = vide
    grid: TopGrid

    @property
    def filled(self) -> np.ndarray:
        return self.color >= 0


def reconstruct(views: dict[str, View], profil_tete: str = "droite") -> VoxelModel:
    top = views["dessus"]
    g = top_grid(top)
    W, L = g.occ.shape

    # Profil : axe horizontal = longueur. Tête à droite -> j = 0 à droite -> lecture inversée.
    p_top, p_bot, s_prof = _silhouette_profile(views["profil"], L, reverse=(profil_tete == "droite"))
    # Face : axe horizontal = largeur, en miroir (la droite du sujet est à gauche de l'image).
    f_top, f_bot, s_face = _silhouette_profile(views["face"], W, reverse=True)

    H = int(np.ceil(max(p_top.max(), f_top.max()) * PLATES_PER_STUD)) + 1
    k_center = (np.arange(H) + 0.5) / PLATES_PER_STUD  # hauteur du centre de chaque couche, en tenons
    filled = np.zeros((W, L, H), bool)
    for i in range(W):
        for j in range(L):
            if not g.occ[i, j]:
                continue
            lo = max(p_bot[j], f_bot[i])
            hi = min(p_top[j], f_top[i])
            filled[i, j] = (k_center >= lo) & (k_center <= hi)

    color = np.full((W, L, H), -1, int)
    _paint(color, filled, g, views, s_prof, s_face, profil_tete)
    return VoxelModel(color=color, grid=g)


def _paint(color, filled, g: TopGrid, views, s_prof, s_face, profil_tete, n_colors: int = 8) -> None:
    """Échantillonne une couleur brute par voxel visible, puis regroupe toutes les couleurs observées
    en n_colors teintes (k-means) avant de les associer à la palette : l'ombre et les reflets d'une
    même pièce retombent ainsi dans la même couleur."""
    W, L, H = filled.shape
    top = views["dessus"]
    r = 0.3 * g.p
    raw = np.zeros((W, L, H, 3), np.uint8)
    has = np.zeros((W, L, H), bool)

    top_col = np.zeros((W, L, 3), np.uint8)
    top_ok = np.zeros((W, L), bool)
    for i in range(W):
        for j in range(L):
            if g.occ[i, j]:
                x, y = g.center(i, j)
                bgr = colors.sample(top.img_col, x, y, r, top.mask)
                if bgr is not None:
                    top_col[i, j], top_ok[i, j] = bgr, True

    def side(view: View | None, frac_h: float, k: int, s: float):
        if view is None:
            return None
        x0, _, x1, y1 = view.bbox
        x = x0 + frac_h * (x1 - x0)
        y = y1 - ((k + 0.5) / PLATES_PER_STUD) / s
        return colors.sample(view.img_col, x, y, 0.15 / s, view.mask)

    prof, face, dos, dessous = (views.get(n) for n in ("profil", "face", "dos", "dessous"))
    pad = np.pad(filled, 1)
    for i, j, k in zip(*np.nonzero(filled)):
        ip, jp, kp = i + 1, j + 1, k + 1
        c = None
        if not pad[ip, jp, kp + 1]:                                   # face supérieure visible
            c = top_col[i, j] if top_ok[i, j] else None
        elif not pad[ip - 1, jp, kp] or not pad[ip + 1, jp, kp]:      # flanc gauche/droit
            t = (j + 0.5) / L
            c = side(prof, 1 - t if profil_tete == "droite" else t, k, s_prof)
        elif not pad[ip, jp - 1, kp]:                                 # avant (tête)
            c = side(face, 1 - (i + 0.5) / W, k, s_face)
        elif not pad[ip, jp + 1, kp]:                                 # arrière
            c = side(dos, (i + 0.5) / W, k, s_face)
        elif not pad[ip, jp, kp - 1] and dessous is not None:         # dessous
            x0, y0, x1, y1 = dessous.bbox
            x = x1 - (i + 0.5) / W * (x1 - x0)                        # miroir gauche/droite
            y = y0 + (j + 0.5) / L * (y1 - y0)
            c = colors.sample(dessous.img_col, x, y, 0.3 * (x1 - x0) / W, dessous.mask)
        exposed = not (pad[ip - 1:ip + 2, jp, kp].all() and pad[ip, jp - 1:jp + 2, kp].all()
                       and pad[ip, jp, kp - 1:kp + 2].all())
        if not exposed:
            continue                                                  # intérieur : couleur libre
        if c is None and top_ok[i, j]:
            c = top_col[i, j]                                         # repli
        if c is not None:
            raw[i, j, k], has[i, j, k] = c, True

    # Symétrie gauche/droite : on moyenne les couleurs brutes des voxels miroirs (atténue
    # ombres et reflets, qui ne sont pas symétriques alors que le sujet l'est)
    axis = symmetry_axis(g.occ)
    raw_f = raw.astype(np.float32)
    for i in range(W):
        m = axis - i
        if not (0 <= m < W) or m <= i:
            continue
        both = has[i] & has[m]
        avg = (raw_f[i][both] + raw_f[m][both]) / 2
        raw_f[i][both] = avg
        raw_f[m][both] = avg
    raw = raw_f.astype(np.uint8)

    # Regroupement des teintes
    samples = raw[has].reshape(-1, 1, 3)
    lab = cv2.cvtColor(samples, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    lab[:, 0] *= colors.L_WEIGHT
    k_eff = min(n_colors, len(np.unique(samples.reshape(-1, 3), axis=0)))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    _, labels, centers = cv2.kmeans(lab, k_eff, None, crit, 5, cv2.KMEANS_PP_CENTERS)
    centers[:, 0] /= colors.L_WEIGHT
    center_bgr = cv2.cvtColor(np.clip(centers, 0, 255).astype(np.uint8)[None], cv2.COLOR_LAB2BGR)[0]
    codes = np.array([colors.nearest_code(c) for c in center_bgr])
    color[has] = codes[labels.ravel()]
    smooth_colors(color, has)
    # Intérieur et voxels sans échantillon : une seule couleur de remplissage (la plus fréquente),
    # pour que le pavage puisse utiliser de grandes plaques
    fallback = int(np.bincount(color[has]).argmax())
    color[filled & ~has] = fallback


def symmetry_axis(occ: np.ndarray) -> int:
    """Axe de symétrie en largeur : entier s tel que la colonne i a pour miroir s - i."""
    W = occ.shape[0]
    best, best_s = -1.0, W - 1
    for s in range(W // 2, 2 * W - 2 - W // 2 + 1):
        idx = np.arange(W)
        m = s - idx
        ok = (m >= 0) & (m < W)
        score = (occ[idx[ok]] == occ[m[ok]]).mean() * ok.mean()
        if score > best:
            best, best_s = score, s
    return best_s


def smooth_colors(color: np.ndarray, has: np.ndarray, iters: int = 2, majority: float = 0.6) -> None:
    """Filtre majoritaire 3D sur les voxels de surface : un voxel prend la couleur dominante
    de ses voisins si elle représente au moins `majority` d'entre eux (supprime le bruit isolé)."""
    W, L, H = color.shape
    for _ in range(iters):
        new = color.copy()
        for i, j, k in np.argwhere(has):
            nb = color[max(0, i - 1):i + 2, max(0, j - 1):j + 2, max(0, k - 1):k + 2]
            hb = has[max(0, i - 1):i + 2, max(0, j - 1):j + 2, max(0, k - 1):k + 2]
            vals = nb[hb]
            if len(vals) < 5:
                continue
            codes, counts = np.unique(vals, return_counts=True)
            top = counts.argmax()
            if codes[top] != color[i, j, k] and counts[top] >= majority * len(vals):
                new[i, j, k] = codes[top]
        color[:] = new
