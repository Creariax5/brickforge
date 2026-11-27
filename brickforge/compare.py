"""Comparaison rendu 3D / vues Gemini : calage de caméra, scores, cartes de différences.

Pour chaque vue (concept, dessus, profil, face, dos, dessous) :
1. silhouette de la photo (rembg, mise en cache) ;
2. recherche de la caméra (orientation, distance, cadrage, focale) qui fait coïncider la silhouette
   du rendu avec celle de la photo (maximise l'IoU) ;
3. rendu couleur avec cette caméra, puis scores :
   - silhouette : IoU des silhouettes ;
   - contour : écart moyen entre les contours, en % de la taille du sujet ;
   - couleur : part des pixels communs dont la couleur diffère nettement (ΔE pondéré) ;
4. images : rendu, superposition, carte des différences.

Usage : python -m brickforge.compare imgs/lego_tortue [--views profil,face] [--refit]
Sorties : out/compare/<sujet>/{<vue>_photo.jpg,_render.png,_diff.png}, scores.json, cameras.json, history.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import minimize

from . import colors
from .grid import subject_mask
from .ldlib import part_triangles
from .views import flatten_lighting

ROOT = Path(__file__).resolve().parent.parent
VIEWS = ["concept", "dessus", "profil", "face", "dos", "dessous"]
# Familles de couleurs : l'éclairage des photos ne permet pas de distinguer les nuances proches
FAMILY = {70: 1, 308: 1, 320: 1, 484: 2, 25: 2, 84: 2, 92: 2, 19: 3, 15: 3, 28: 3, 378: 4, 330: 4, 2: 4, 10: 4,
          71: 5, 72: 5, 0: 6, 14: 7}
LIMITS = {"dessus": {"az": 0, "el": 89}, "dessous": {"az": 0, "el": -89}, "profil": {"az": 90, "el": 12},
          "face": {"az": 180, "el": 12}, "dos": {"az": 0, "el": 12}}
FIT_W = 260          # largeur des images pendant le calage
OUT_W = 900          # largeur des images de sortie
# Orientation de départ (azimut, élévation, degrés) : az 0 = caméra côté +Z (arrière), 90 = côté +X (profil)
INIT = {"dessus": [(0, 89), (0, 70)], "dessous": [(0, -89), (0, -70)],
        "profil": [(90, e) for e in (5, 15, 25)] + [(-90, 10)], "face": [(180, e) for e in (5, 15, 25)],
        "dos": [(0, e) for e in (5, 15, 25)], "concept": [(a, e) for a in range(0, 360, 45) for e in (15, 35)]}


# ------------------------------------------------------------------ scène

def load_scene(assembly: dict):
    """Triangles du modèle (N, 3, 3) en LDU, repère Y vers le haut, et couleur BGR par triangle."""
    tris, cols, codes = [], [], []
    cache = {}
    for p in assembly["parts"]:
        if p.get("hidden"):
            continue
        if p["part"] not in cache:
            cache[p["part"]] = part_triangles(p["part"]).astype(np.float32)
        t = cache[p["part"]]
        if not len(t):
            continue
        R = np.array(p["m"][3:], np.float32).reshape(3, 3)
        w = t @ R.T + np.array(p["m"][:3], np.float32)
        w[..., 1] *= -1                                   # LDraw : Y vers le bas
        tris.append(w)
        try:
            c = colors.code_bgr(int(p["color"]))
        except ValueError:
            c = (128, 128, 128)
        cols.append(np.repeat(np.array([c], np.float32), len(w), 0))
        codes.append(np.full(len(w), int(p["color"]), np.int32))
    hull_v = [np.unique(w.reshape(-1, 3).round(1), axis=0) for w in tris]   # sommets uniques par pièce
    hull_idx = np.cumsum([0] + [len(h) for h in hull_v])
    hull_v = np.concatenate(hull_v)
    tris = np.concatenate(tris)
    cols = np.concatenate(cols)
    codes = np.concatenate(codes)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    return tris, cols, n, hull_v, hull_idx, codes


# ------------------------------------------------------------------ caméra

def camera_basis(az, el, roll):
    a, e, r = map(math.radians, (az, el, roll))
    d = np.array([math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e)])  # cible -> caméra
    f = -d
    # vues quasi verticales : la tête (-Z) vers le haut de l'image, au-dessus comme en dessous
    upref = np.array([0.0, 1.0, 0.0]) if abs(el) < 80 else np.array([-math.sin(a), 0.0, -math.cos(a)])
    right = np.cross(f, upref)
    right /= np.linalg.norm(right)
    up = np.cross(right, f)
    c, s = math.cos(r), math.sin(r)
    right, up = c * right + s * up, -s * right + c * up
    return d, f, right, up


def project(verts, cam, size, center):
    """cam = dict(az, el, roll, dist, focal, sx, sy). Renvoie (x, y, profondeur)."""
    W, H = size
    d, f, right, up = camera_basis(cam["az"], cam["el"], cam["roll"])
    C = center + d * cam["dist"]
    rel = verts - C
    X, Y, Z = rel @ right, rel @ up, rel @ f
    Z = np.maximum(Z, 1.0)
    fp = cam["focal"] * W
    x = W / 2 + cam["sx"] * W + fp * X / Z
    y = H / 2 + cam["sy"] * H - fp * Y / Z
    return x, y, Z


def render(scene, cam, size, center, color=True):
    tris, cols, normals, hull_v, hull_idx, codes = scene
    W, H = size
    if not color:   # silhouette rapide : enveloppe convexe projetée de chaque pièce
        x, y, _ = project(hull_v, cam, size, center)
        P = np.round(np.stack([x, y], 1) * 4).astype(np.int32)
        m = np.zeros((H, W), np.uint8)
        polys = [cv2.convexHull(P[hull_idx[i]:hull_idx[i + 1]]) for i in range(len(hull_idx) - 1)]
        cv2.fillPoly(m, polys, 1, shift=2)
        return m
    v = tris.reshape(-1, 3)
    x, y, z = project(v, cam, size, center)
    from .zraster import raster
    tid = raster(x.reshape(-1, 3), y.reshape(-1, 3), z.reshape(-1, 3), W, H)   # z-buffer
    d, f, right, up = camera_basis(cam["az"], cam["el"], cam["roll"])
    light = -f * 0.6 + up * 0.6 + right * 0.3
    light /= np.linalg.norm(light)
    shade = 0.55 + 0.45 * np.abs(normals @ light)
    fg = tid >= 0
    img = np.full((H, W, 3), 255, np.uint8)
    img[fg] = np.clip(cols[tid[fg]] * shade[tid[fg], None], 0, 255).astype(np.uint8)
    mask = fg.astype(np.uint8)
    code_img = np.where(fg, codes[np.maximum(tid, 0)], -1).astype(np.int32)
    return img, mask, code_img


# ------------------------------------------------------------------ calage

def iou(a, b):
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return inter / union if union else 0.0


def _bbox(m):
    ys, xs = np.nonzero(m)
    return xs.min(), ys.min(), xs.max(), ys.max()


def fit_camera(scene, center, radius, target_mask, inits, prev=None, limits=None, fixed_dist=None):
    H, W = target_mask.shape
    size = (W, H)
    tx0, ty0, tx1, ty1 = _bbox(target_mask)
    t_w = max(tx1 - tx0, ty1 - ty0)

    def make(az, el, roll=0.0, focal=1.4, dist=None, sx=0.0, sy=0.0):
        return {"az": az, "el": el, "roll": roll, "focal": focal,
                "dist": dist if dist else radius * 6, "sx": sx, "sy": sy}

    def align(cam):
        """Ajuste distance et décalage pour que les boîtes englobantes coïncident."""
        for _ in range(2):
            m = render(scene, cam, size, center, color=False)
            if not m.any():
                return cam
            x0, y0, x1, y1 = _bbox(m)
            r_w = max(x1 - x0, y1 - y0)
            cam["dist"] *= r_w / max(t_w, 1)
            m = render(scene, cam, size, center, color=False)
            if not m.any():
                return cam
            x0, y0, x1, y1 = _bbox(m)
            cam["sx"] += ((tx0 + tx1) - (x0 + x1)) / 2 / W
            cam["sy"] += ((ty0 + ty1) - (y0 + y1)) / 2 / H
        return cam

    keys = ["az", "el", "roll", "dist", "focal", "sx", "sy"]
    scale = np.array([6, 6, 4, radius * 0.5, 0.25, 0.04, 0.04])
    # silhouettes adoucies : la perte varie continûment avec la caméra (l'IoU dur fait des marches)
    soft_t = cv2.GaussianBlur(target_mask.astype(np.float32), (0, 0), 3.0)

    def penalty(cam):
        """Garde la caméra proche de l'angle prévu pour la vue (sinon l'optimiseur « triche » en tournant)."""
        if not limits:
            return 0.0
        pen = 0.0
        daz = (cam["az"] - limits["az"] + 180) % 360 - 180
        for v, lim in ((daz, 5), (cam["el"] - limits["el"], 8 if abs(limits["el"]) < 60 else 30),
                       (((cam["roll"] + 180) % 360 - 180) if abs(limits["el"]) < 60 else 0, 3)):
            if abs(v) > lim:
                pen += 0.05 * (abs(v) - lim)
        return pen

    def loss_cam(cam):
        cam = dict(cam)
        p_ = penalty(cam)
        cam["focal"] = max(cam["focal"], 0.3)
        m = render(scene, cam, size, center, color=False).astype(np.float32)
        m = cv2.GaussianBlur(m, (0, 0), 3.0)
        inter = np.minimum(m, soft_t).sum()
        union = np.maximum(m, soft_t).sum()
        return 1 - inter / max(union, 1e-6) + p_

    def optimize(cam, free):
        x0 = np.array([cam[k] for k in keys])
        idx = [keys.index(k) for k in free]

        def f(u):
            v = x0.copy()
            v[idx] += u * scale[idx]
            return loss_cam(dict(zip(keys, v)))
        r = minimize(f, np.zeros(len(idx)), method="Powell",
                     options={"maxfev": 60 * len(idx), "xtol": 1e-3, "ftol": 1e-4})
        v = x0.copy()
        v[idx] += r.x * scale[idx]
        return dict(zip(keys, v)), r.fun

    # silhouettes presque symétriques : on essaie aussi chaque départ retourné de 180°
    starts = [align(make(a, e, roll=r)) for a, e in inits for r in ((0, 180) if abs(e) > 60 else (0,))]
    if prev:
        starts.append(dict(prev))
    if fixed_dist:
        for c in starts:   # même cadrage, mais distance imposée : la taille est rattrapée par la focale
            c["focal"] *= fixed_dist / c["dist"]
            c["dist"] = fixed_dist
    starts.sort(key=loss_cam)
    best, best_l = None, 9.0
    size_key = "focal" if fixed_dist else "dist"
    all_keys = [k for k in keys if not (fixed_dist and k == "dist")]
    for cam in starts[:3]:                                   # les 3 meilleurs départs
        cam, _ = optimize(cam, [size_key, "sx", "sy"])       # 1. cadrage seul
        cam, _ = optimize(cam, ["az", "el", "roll"])         # 2. orientation
        cam, l = optimize(cam, all_keys)                     # 3. tout
        if l < best_l:
            best, best_l = cam, l
    final = render(scene, best, size, center, color=False) > 0
    return best, iou(final, target_mask)


# ------------------------------------------------------------------ scores et images

def contour_distance(a, b):
    """Écart moyen symétrique entre les contours de deux masques, en px."""
    def edge(m):
        m = m.astype(np.uint8)
        return cv2.morphologyEx(m, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    ea, eb = edge(a), edge(b)
    if not ea.any() or not eb.any():
        return float("inf")
    da = cv2.distanceTransform((~eb).astype(np.uint8), cv2.DIST_L2, 3)
    db = cv2.distanceTransform((~ea).astype(np.uint8), cv2.DIST_L2, 3)
    return float((da[ea].mean() + db[eb].mean()) / 2)


def color_mismatch(photo, code_img, both, model_codes):
    """Couleur zone par zone : pour chaque zone connexe de même code dans le rendu, couleur médiane
    de la photo -> couleur LEGO la plus proche (parmi celles du modèle) -> même famille que la pièce ?
    Robuste aux ombres et reflets, qui faussent une comparaison pixel par pixel."""
    lab = cv2.cvtColor(photo, cv2.COLOR_BGR2LAB).astype(np.float32)
    pal = np.array([colors.code_bgr(c) for c in model_codes], np.uint8)[None]
    pal = cv2.cvtColor(pal, cv2.COLOR_BGR2LAB)[0].astype(np.float32)
    w = np.array([colors.L_WEIGHT, 1, 1], np.float32)
    bad = np.zeros_like(both)
    photo_code = np.full(code_img.shape, -1, np.int32)
    tot = wrong = 0
    for c in model_codes:
        n, lab_cc = cv2.connectedComponents(((code_img == c) & both).astype(np.uint8))
        for k in range(1, n):
            zone = lab_cc == k
            area = int(zone.sum())
            if area < 25:
                continue
            med = np.median(lab[zone], axis=0)
            guess = model_codes[int((((pal - med) * w) ** 2).sum(1).argmin())]
            photo_code[zone] = guess
            tot += area
            if FAMILY.get(guess, guess) != FAMILY.get(c, c):
                bad |= zone
                wrong += area
    return bad, wrong / max(tot, 1), photo_code


def diff_image(photo, pmask, rmask, bad_color):
    g = cv2.cvtColor(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    out = (g * 0.45 + 255 * 0.55).astype(np.uint8)
    only_p = pmask & ~rmask
    only_r = rmask & ~pmask
    out[only_p] = (40, 40, 230)     # rouge : présent sur la photo, absent du modèle
    out[only_r] = (230, 120, 30)    # bleu : présent dans le modèle, absent de la photo
    out[bad_color] = (0, 165, 255)  # orange : bonne forme, mauvaise couleur
    return out


# ------------------------------------------------------------------ pipeline

def _score_view(subject_dir, view, scene, center, radius, cams, out, refit=False, fixed_dist=None, log=print):
    """Cale la caméra d'une vue, rend, calcule les scores et écrit les images. Renvoie le dict de scores."""
    src = next((subject_dir / f"{view}{e}" for e in (".jpeg", ".jpg", ".png") if (subject_dir / f"{view}{e}").exists()), None)
    if src is None:
        return None
    t0 = time.time()
    full = cv2.imread(str(src))
    s = OUT_W / full.shape[1]
    photo = cv2.resize(full, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    mpath = out / f"{view}_mask.png"
    if mpath.exists() and mpath.stat().st_mtime > src.stat().st_mtime:
        pmask = cv2.imread(str(mpath), 0) > 0
    else:
        pmask = subject_mask(photo) > 0
        cv2.imwrite(str(mpath), pmask.astype(np.uint8) * 255)
    H, W = pmask.shape
    k = FIT_W / W
    small = cv2.resize(pmask.astype(np.uint8), (FIT_W, int(H * k)), interpolation=cv2.INTER_NEAREST) > 0
    prev = cams.get(view)
    if prev and not refit:
        # recalage rapide à partir de la caméra précédente (le modèle a pu changer un peu)
        cam, fit = fit_camera(scene, center, radius, small, [], prev=prev, limits=LIMITS.get(view), fixed_dist=fixed_dist)
    else:
        cam, fit = fit_camera(scene, center, radius, small, INIT[view], prev=prev if not refit else None,
                              limits=LIMITS.get(view), fixed_dist=fixed_dist)
    cams[view] = cam
    rend, rmask, code_img = render(scene, cam, (W, H), center)
    rmask = rmask > 0
    both = pmask & rmask
    model_codes = sorted({int(c) for c in np.unique(code_img) if c >= 0})
    bad, bad_rate, _ = color_mismatch(flatten_lighting(photo, pmask.astype(np.uint8) * 255), code_img, both, model_codes)
    de = 0.0
    cd = contour_distance(pmask, rmask)
    size = max(np.ptp(np.nonzero(pmask)[0]), np.ptp(np.nonzero(pmask)[1]))
    res = {
        "silhouette": round(iou(pmask, rmask), 4),
        "contour_pct": round(100 * cd / size, 2),
        "couleur_ok": round(1 - bad_rate, 4),
        "manque_pct": round(100 * (pmask & ~rmask).sum() / pmask.sum(), 1),
        "en_trop_pct": round(100 * (rmask & ~pmask).sum() / pmask.sum(), 1),
        "camera": {k2: round(v2, 3) for k2, v2 in cam.items()},
        "duree_s": round(time.time() - t0, 1),
    }
    cv2.imwrite(str(out / f"{view}_photo.jpg"), photo, [cv2.IMWRITE_JPEG_QUALITY, 85])
    render_rgba = np.dstack([rend, rmask.astype(np.uint8) * 255])
    cv2.imwrite(str(out / f"{view}_render.png"), render_rgba)
    cv2.imwrite(str(out / f"{view}_diff.png"), diff_image(photo, pmask, rmask, bad))
    log(f"{view:8} silhouette {res['silhouette']:.3f}  contour {res['contour_pct']:5.2f} %  "
        f"couleur {res['couleur_ok']:.3f}  ({res['duree_s']} s)")
    return res


def compare(subject_dir: Path, views=None, refit=False, log=print) -> dict:
    subject = subject_dir.name
    out = ROOT / "out" / "compare" / subject
    out.mkdir(parents=True, exist_ok=True)
    assembly = json.loads((subject_dir / "assemblage.json").read_text())
    scene = load_scene(assembly)
    v = scene[0].reshape(-1, 3)
    center = (v.min(0) + v.max(0)) / 2
    radius = float(np.linalg.norm(v.max(0) - v.min(0)) / 2)
    cams_path = out / "cameras.json"
    cams = json.loads(cams_path.read_text()) if cams_path.exists() else {}
    results = {}
    for view in views or VIEWS:
        r = _score_view(subject_dir, view, scene, center, radius, cams, out, refit=refit, log=log)
        if r is not None:
            results[view] = r
    # Cohérence des distances : même prise de vue pour toutes les photos. Une vue dont la caméra s'est
    # rapprochée ou éloignée (> 15 %) pour « tricher » est recalée avec la distance médiane.
    dists = [cams[v]["dist"] for v in results if v != "concept"]
    if len(dists) >= 3:
        ref = float(np.median(dists))
        redo = [v for v in results if v != "concept" and abs(cams[v]["dist"] / ref - 1) > 0.15]
        for v in redo:
            log(f"{v:8} distance {cams[v]['dist']:.0f} trop loin de la médiane {ref:.0f} : recalage")
            results[v] = _score_view(subject_dir, v, scene, center, radius, cams, out, refit=True, fixed_dist=ref, log=log)
    cams_path.write_text(json.dumps(cams, indent=1))
    sc_path = out / "scores.json"
    all_scores = json.loads(sc_path.read_text()).get("views", {}) if sc_path.exists() else {}
    all_scores.update(results)
    summary = {
        "silhouette": round(float(np.mean([r["silhouette"] for r in all_scores.values()])), 4),
        "contour_pct": round(float(np.mean([r["contour_pct"] for r in all_scores.values()])), 2),
        "couleur_ok": round(float(np.mean([r["couleur_ok"] for r in all_scores.values()])), 4),
    }
    doc = {"subject": subject, "updated": datetime.now().isoformat(timespec="seconds"),
           "assembly_updated": assembly.get("updated") or assembly.get("created"),
           "n_parts": len(assembly["parts"]), "summary": summary, "views": all_scores}
    sc_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    with (out / "history.jsonl").open("a") as f:
        f.write(json.dumps({"t": doc["updated"], "n_parts": doc["n_parts"], **summary,
                            "views": {k2: {kk: v2[kk] for kk in ("silhouette", "contour_pct", "couleur_ok")}
                                      for k2, v2 in all_scores.items()}}) + "\n")
    log(f"moyenne  silhouette {summary['silhouette']:.3f}  contour {summary['contour_pct']:.2f} %  couleur {summary['couleur_ok']:.3f}")
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--views", default="")
    ap.add_argument("--refit", action="store_true", help="recaler les caméras depuis zéro")
    a = ap.parse_args()
    compare(a.folder, [v for v in a.views.split(",") if v] or None, a.refit)


if __name__ == "__main__":
    main()
