"""Étape 1 du focus BrickHeadz : analyse des BrickHeadz officiels modélisés en 3D (OMR LDraw).

Pour chaque set : figurine(s) isolée(s), orientée(s) face vers -Z (les yeux regardent la caméra),
recalée(s) au centre du socle, puis passée(s) en grille de voxels colorés.
Sorties : data/brickheadz/figures.json (une entrée par figurine), data/brickheadz/grids.npz (grilles),
images de synthèse dans research/assets/09-*.png.

    python -m brickforge.brickheadz
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from brickforge.ldlib import _find, part_triangles

ROOT = Path(__file__).resolve().parent.parent
OMR = ROOT / "data" / "omr"
OUT = ROOT / "data" / "brickheadz"
ASSETS = ROOT / "research" / "assets"
VX, VY = 10.0, 4.0           # voxel : demi-tenon en largeur/profondeur, demi-plate en hauteur (LDU)


# ---------------------------------------------------------------- utilitaires

def ldcolors():
    cols = {}
    for l in (ROOT / "data" / "ldraw" / "LDConfig.ldr").read_text(errors="ignore").splitlines():
        m = re.match(r"0 !COLOUR (\S+)\s+CODE\s+(\d+)\s+VALUE\s+#([0-9A-Fa-f]{6})", l)
        if m:
            cols[int(m.group(2))] = (m.group(1).replace("_", " "), m.group(3))
    return cols


COLS = ldcolors()
_titles = {}


def title(part):
    if part not in _titles:
        f = _find(part + ".dat")
        _titles[part] = f.read_text(errors="ignore").splitlines()[0][2:].strip() if f else part
    return _titles[part]


def mat(p):
    return np.array(p["m"][3:], float).reshape(3, 3), np.array(p["m"][:3], float)


def world_tris(p):
    t = part_triangles(p["part"]).reshape(-1, 3).astype(float)
    if not len(t):
        return t
    M, o = mat(p)
    return t @ M.T + o


def model_json(num):
    for d in (OMR / num.split("-")[0], OMR / num):
        f = d / f"{num}.json"
        if f.exists():
            return json.loads(f.read_text())
    return None


# ---------------------------------------------------------------- figurines

def split_figures(parts):
    """Composantes connexes en projection horizontale (boîtes englobantes qui se touchent) ; on garde les grosses."""
    boxes = []
    for p in parts:
        t = world_tris(p)
        if not len(t):
            boxes.append(None)
            continue
        boxes.append((t[:, [0, 2]].min(0) - 1, t[:, [0, 2]].max(0) + 1))
    idx = [i for i, b in enumerate(boxes) if b is not None]
    par = {i: i for i in idx}

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for a in range(len(idx)):
        for b in range(a + 1, len(idx)):
            i, j = idx[a], idx[b]
            (l1, h1), (l2, h2) = boxes[i], boxes[j]
            if (l1 <= h2).all() and (l2 <= h1).all():
                par[find(i)] = find(j)
    groups = defaultdict(list)
    for i in idx:
        groups[find(i)].append(parts[i])
    figs = sorted(groups.values(), key=len, reverse=True)
    return [g for g in figs if len(g) >= 40], [g for g in figs if len(g) < 40]


EYE_RX = re.compile(r"eye|pupil", re.I)


def front_dir(fig):
    """Direction de la face : axe « dessus » des tuiles/pièces rondes d'yeux posées à la verticale (SNOT), dans le haut du modèle."""
    ys = np.concatenate([world_tris(p)[:, 1] for p in fig if len(part_triangles(p["part"]))])
    top, bot = ys.min(), ys.max()
    votes = Counter()
    for p in fig:
        name = title(p["part"])
        round_ = re.search(r"Tile\s+(1 x 1|2 x 2) Round|Plate\s+1 x 1 Round|Dish", name)
        if not (EYE_RX.search(name) or (round_ and p["color"] in (0, 15))):
            continue
        M, o = mat(p)
        if o[1] > top + 0.6 * (bot - top):      # trop bas : pas un œil
            continue
        up = -M[:, 1]                            # le « dessus » de la pièce (Y LDraw vers le bas)
        if abs(up[1]) > 0.5:                     # posée à plat : pas en façade
            continue
        k = int(np.argmax(np.abs(up[[0, 2]])))
        axis = ("x", "z")[k]
        sign = int(np.sign(up[[0, 2]][k]))
        votes[(axis, sign)] += 3 if EYE_RX.search(name) else 1
    return votes.most_common(1)[0][0] if votes else ("z", -1)


def rot_to_front(axis, sign):
    """Rotation (autour de Y) qui amène la face vers -Z."""
    if (axis, sign) == ("z", -1):
        return np.eye(3)
    if (axis, sign) == ("z", 1):
        return np.diag([-1.0, 1, -1])
    if (axis, sign) == ("x", 1):                 # +X → -Z
        return np.array([[0, 0, 1.0], [0, 1, 0], [-1, 0, 0]])
    return np.array([[0, 0, -1.0], [0, 1, 0], [1, 0, 0]])  # -X → -Z


def normalize(fig):
    axis, sign = front_dir(fig)
    R = rot_to_front(axis, sign)
    T = [(p, world_tris(p) @ R.T) for p in fig]
    pts = np.vstack([t for _, t in T if len(t)])
    lo, hi = pts.min(0), pts.max(0)
    # origine : centre en X/Z, dessous du socle (Y LDraw vers le bas → y max)
    # origine X/Z : axe de la tête (moyenne des briques à tenons latéraux 22885 du haut, sinon centre de la tête), calé sur la grille de 10 LDU
    h = hi[1] - pts[:, 1]
    core = [R @ mat(p)[1] for p in fig if p["part"] == "22885" and hi[1] - (R @ mat(p)[1])[1] > 0.45 * h.max()]
    if len(core) >= 2:
        cx, cz = np.mean(core, axis=0)[[0, 2]]
    else:
        hp = pts[h > 0.55 * h.max()]
        cx, cz = np.median(hp[:, 0]), np.median(hp[:, 2])
    off = np.array([round(cx / 10) * 10, hi[1], round(cz / 10) * 10])
    out = []
    for p, t in T:
        M, o = mat(p)
        M2, o2 = R @ M, R @ o - off
        out.append({**p, "m": [*o2.round(3).tolist(), *M2.round(6).ravel().tolist()], "_tris": (t - off) if len(t) else t})
    # corps = colonne sous la tête (le socle des saisonniers porte des décors sur les côtés)
    allp = np.vstack([p["_tris"] for p in out if len(p["_tris"])])
    h = -allp[:, 1]
    head = allp[h > 0.55 * h.max()]
    hx, hz = (head[:, 0].min(), head[:, 0].max()), (head[:, 2].min(), head[:, 2].max())
    body = [p for p in out if hx[0] - 10 <= p["m"][0] <= hx[1] + 10 and hz[0] - 10 <= p["m"][2] <= hz[1] + 10]
    return out, (axis, sign), hi - lo, {"head_studs": [round((hx[1] - hx[0]) / 20, 1), round((hz[1] - hz[0]) / 20, 1)],
                                       "body_parts": len(body), "props_parts": len(out) - len(body)}


# ---------------------------------------------------------------- voxels

def voxelize(fig, shape=(24, 96, 24)):
    """Grille [x, hauteur, z] de codes couleur LDraw (-1 = vide), centrée ; surface échantillonnée sur les triangles."""
    nx, ny, nz = shape
    g = np.full(shape, -1, np.int16)
    for p in fig:
        t = p["_tris"]
        if not len(t):
            continue
        t = t.reshape(-1, 3, 3)
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        # échantillons barycentriques, densité selon la taille du triangle
        area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
        n = np.clip((area / 4).astype(int), 3, 400)
        rep = np.repeat(np.arange(len(t)), n)
        u, v = np.random.default_rng(0).random((2, len(rep)))
        flip = u + v > 1
        u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
        pts = a[rep] + (b[rep] - a[rep]) * u[:, None] + (c[rep] - a[rep]) * v[:, None]
        ix = np.floor(pts[:, 0] / VX + nx / 2).astype(int)
        iy = np.floor(-pts[:, 1] / VY).astype(int)              # hauteur vers le haut
        iz = np.floor(pts[:, 2] / VX + nz / 2).astype(int)
        ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny) & (iz >= 0) & (iz < nz)
        g[ix[ok], iy[ok], iz[ok]] = p["color"]
    return g


def front_image(g):
    """Vue de face orthographique (première couleur rencontrée depuis -Z) → image RGB [hauteur, x]."""
    nx, ny, nz = g.shape
    img = np.full((ny, nx, 3), 200, np.uint8)
    for x in range(nx):
        for y in range(ny):
            col = g[x, y]
            k = np.nonzero(col >= 0)[0]
            if len(k):
                hx = COLS.get(int(col[k[0]]), ("", "999999"))[1]
                img[ny - 1 - y, x] = [int(hx[i:i + 2], 16) for i in (0, 2, 4)]
    return img


# ---------------------------------------------------------------- analyse


def analyse():
    OUT.mkdir(parents=True, exist_ok=True)
    idx = {r["num"]: r for r in json.loads((OMR / "index.json").read_text())}
    import sqlite3
    db = sqlite3.connect(ROOT / "data" / "rebrickable" / "rb.sqlite")
    nums = [r[0] for r in db.execute("SELECT num FROM sets WHERE theme LIKE 'BrickHeadz%' ORDER BY year, num") if r[0] in idx]
    figures, grids, extras = [], [], Counter()
    for num in nums:
        d = model_json(num)
        if not d:
            print("absent", num)
            continue
        parts = [p for p in d["parts"] if "LSynth" not in title(p["part"])]      # ficelles/toiles en segments : pas des pièces
        figs, small = split_figures(parts)
        for s in small:
            extras[len(s)] += 1
        for k, fig in enumerate(figs):
            nf, front, size, body = normalize(fig)
            g = voxelize(nf)
            grids.append(g)
            heights = Counter(int(-p["m"][1] // 8) for p in nf)
            figures.append({
                "num": num, "set": idx[num]["name"], "fig": k, "nfigs": len(figs), "year": db.execute("SELECT year FROM sets WHERE num=?", (num,)).fetchone()[0],
                "parts": len(nf), "front": f"{'+' if front[1] > 0 else '-'}{front[0]}",
                "size_studs": [round(size[0] / 20, 1), round(size[2] / 20, 1)], "height_plates": round(size[1] / 8, 1), **body,
                "colors": Counter(p["color"] for p in nf).most_common(),
                "part_list": Counter(p["part"] for p in nf).most_common(),
                "placed": [{"part": p["part"], "color": p["color"], "m": p["m"]} for p in nf],
            })
            print(f"{num} {idx[num]['name'][:30]:30} fig{k} {len(nf):3} pièces  face {figures[-1]['front']}  "
                  f"tête {body['head_studs']} tenons, {figures[-1]['height_plates']} plates, décors {body['props_parts']}", flush=True)
    (OUT / "figures.json").write_text(json.dumps(figures, ensure_ascii=False))
    np.savez_compressed(OUT / "grids.npz", grids=np.stack(grids), keys=np.array([f"{f['num']}#{f['fig']}" for f in figures]))
    return figures, np.stack(grids)


def report(figures, grids):
    import cv2
    n = len(figures)
    occ = (grids >= 0)
    # 1. galerie des vues de face
    tiles = []
    for f, g in zip(figures, grids):
        im = cv2.resize(front_image(g)[::-1][::-1], (24 * 4, 96 * 2), interpolation=cv2.INTER_NEAREST)
        tiles.append(np.pad(im, ((4, 4), (4, 4), (0, 0)), constant_values=255))
    cols = 14
    rows = [np.hstack(tiles[i:i + cols] + [np.full_like(tiles[0], 255)] * (cols - len(tiles[i:i + cols]))) for i in range(0, n, cols)]
    cv2.imwrite(str(ASSETS / "09-brickheadz-galerie.png"), cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR))
    # 2. carte de présence moyenne (face et profil) : où il y a de la matière dans presque tous les modèles
    front = occ.any(axis=3).mean(0).T[::-1]     # [hauteur, x]
    side = occ.any(axis=1).mean(0)[::-1]        # [hauteur, z]
    hm = lambda a: cv2.applyColorMap((a * 255).astype(np.uint8), cv2.COLORMAP_VIRIDIS)
    big = lambda a: cv2.resize(a, (a.shape[1] * 8, a.shape[0] * 4), interpolation=cv2.INTER_NEAREST)
    sep = np.full((96 * 4, 16, 3), 255, np.uint8)
    cv2.imwrite(str(ASSETS / "09-brickheadz-presence.png"), np.hstack([big(hm(front)), sep, big(hm(side))]))
    # 3. statistiques
    H = np.array([f["height_plates"] for f in figures])
    W = np.array([f["head_studs"] for f in figures])
    single = [f for f in figures if f["nfigs"] == 1]
    use = Counter()
    for f in figures:
        for p, _ in f["part_list"]:
            use[p] += 1
    tot = Counter()
    for f in figures:
        for p, c in f["part_list"]:
            tot[p] += c
    # squelette : (pièce, position arrondie, orientation) présents dans beaucoup de figurines
    sk = Counter()
    for f in figures:
        seen = set()
        for p in f["placed"]:
            key = (p["part"], tuple(np.round(np.array(p["m"][:3]) / 2) * 2), tuple(np.round(p["m"][3:], 2)))
            if key not in seen:
                seen.add(key)
                sk[key] += 1
    # profil de largeur par hauteur (combien de demi-tenons occupés en X et en Z, médiane)
    wx = np.median(occ.any(axis=3).sum(1), axis=0) / 2       # [hauteur] en tenons
    wz = np.median(occ.any(axis=1).sum(2), axis=0) / 2
    return {"n": n, "sets": len({f["num"] for f in figures}), "single": len(single),
            "height": [float(np.median(H)), float(H.min()), float(H.max())],
            "width": [float(np.median(W[:, 0])), float(np.median(W[:, 1]))],
            "parts": [int(np.median([f["parts"] for f in figures])), min(f["parts"] for f in figures), max(f["parts"] for f in figures)],
            "with_props": sum(f["props_parts"] >= 10 for f in figures),
            "fronts": Counter(f["front"] for f in figures).most_common(),
            "top_use": [(p, title(p), use[p], tot[p]) for p, _ in use.most_common(40)],
            "skeleton": [(k[0], title(k[0]), k[1], v) for k, v in sk.most_common(40)],
            "profile_x": wx.tolist(), "profile_z": wz.tolist(),
            "unique_parts": len(use)}


if __name__ == "__main__":
    figs, grids = analyse()
    r = report(figs, grids)
    (OUT / "stats.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in r.items() if k not in ("profile_x", "profile_z")}, ensure_ascii=False, indent=1)[:6000])
