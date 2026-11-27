"""Étape 3 v2 du focus BrickHeadz : construire la FORME, pas seulement la couleur.

v1 (bh_build.py) recolorait un gabarit entier : un bec, un chapeau ou des oreilles absents du gabarit ne pouvaient pas apparaître.
v2 :
  1. gabarit de base = figurine à la silhouette la plus proche (comme v1) ;
  2. modules par zone : pour chaque zone « qui dépasse » (devant la face : bec, museau, nez ; dessus : chapeau, cheveux,
     oreilles ; côtés : oreilles ; arrière : cheveux, queue), on greffe les pièces de la figurine dont le module colle le mieux
     au volume de la fiche (avec un petit décalage autorisé), si c'est mieux que celui du gabarit, sans collision et accroché au reste ;
  3. comblement : là où la fiche a de la matière et le modèle non, des plaques posées sur des tenons existants (par couches, de bas en haut) ;
  4. recoloration (v1) et contrôle (pièce, couleur) réelles.
Mesures de FORME en plus de la couleur : IoU 3D du volume, silhouettes de face, de profil et de dessus.

    python -m brickforge.bh_build2                # validation croisée v1 / v2 sur les 101 figurines
    python -m brickforge.bh_build2 40377-1 0      # Donald v2 → sujet de l'app
"""

import json
import sys
from collections import Counter

import numpy as np
from scipy import ndimage

from brickforge.bh_build import (RealCombos, fiche_of, id_grid, names, recolor, silhouette_score, to_mpd, views)
from brickforge.brickheadz import ASSETS, COLS, OUT
from brickforge.brickheadz_zones import NX, NY, NZ

# coordonnées (tenons, plates) du centre de chaque case de la grille
_ix, _iy, _iz = np.meshgrid(np.arange(NX), np.arange(NY), np.arange(NZ), indexing="ij")
XS = (_ix - NX / 2 + 0.5) / 2
YP = (_iy + 0.5) * 10 / 8
ZS = (_iz - NZ / 2 + 0.5) / 2
REGIONS = {
    "devant": (YP >= 11) & (YP < 26) & (ZS < -3.4),          # bec, museau, nez, barbe qui dépasse
    "dessus": (YP >= 26),                                     # chapeau, cheveux, oreilles du dessus
    "cotes": (YP >= 11) & (np.abs(XS) > 4.0),                 # oreilles latérales (au-delà des panneaux de la tête, ~3,5 tenons)
    "arriere": (YP >= 11) & (YP < 26) & (ZS > 3.6),           # chignon, cheveux, queue
}


def zone_of_voxels(vx):
    """Zone majoritaire des cases d'une pièce (ou None si dans le corps du gabarit)."""
    z = Counter()
    for k, R in REGIONS.items():
        z[k] = int(R[vx[:, 0], vx[:, 1], vx[:, 2]].sum())
    k, n = z.most_common(1)[0]
    return k if n >= 0.5 * len(vx) else None


def solid(occ):
    return ndimage.binary_fill_holes(ndimage.binary_closing(occ, iterations=1))


def hull(fiche):
    f, l, t = (fiche["views"][d] >= 0 for d in ("front", "left", "top"))    # [x,y] [y,z] [x,z]
    return f[:, :, None] & l[None, :, :] & t[:, None, :]


class Lib:
    """Pour chaque figurine : grille d'identité, pièces par zone, cases de chaque pièce."""

    def __init__(self, figures):
        self.figs = figures
        self.grid, self.vox, self.zone, self._mod = [], [], [], {}
        for f in figures:
            g = id_grid(f["placed"])
            vx = [np.argwhere(g == i) for i in range(len(f["placed"]))]
            self.grid.append(g)
            self.vox.append(vx)
            self.zone.append([zone_of_voxels(v) if len(v) else None for v in vx])

    def module_snaps(self, j, k):
        from brickforge.buildcheck import world_snaps
        if ("s", j, k) not in self._mod:
            idx, _ = self.module(j, k)
            self._mod[("s", j, k)] = world_snaps([self.figs[j]["placed"][i] for i in idx])
        return self._mod[("s", j, k)]

    def module(self, j, k):
        if (j, k) not in self._mod:
            idx = [i for i, z in enumerate(self.zone[j]) if z == k]
            vx = np.unique(np.vstack([self.vox[j][i] for i in idx]), axis=0) if idx else np.zeros((0, 3), int)
            self._mod[(j, k)] = (idx, vx)
        return self._mod[(j, k)]


def shifted(vx, d):
    v = vx + np.array(d)
    ok = (v[:, 0] >= 0) & (v[:, 0] < NX) & (v[:, 1] >= 0) & (v[:, 1] < NY) & (v[:, 2] >= 0) & (v[:, 2] < NZ)
    return v[ok]


SHIFTS = [(dx, dy, dz) for dy in (-2, -1, 0, 1, 2) for dx in (-1, 0, 1) for dz in (-1, 0, 1)]       # en cases de 10 LDU


def to_ldu(d):
    dx, dy, dz = d
    return np.array([dx * 10.0, -round(dy * 10 / 8) * 8.0, dz * 10.0])      # hauteur ramenée à un nombre entier de plates


def graft(lib, base, H, banned):
    """Remplace les modules du gabarit (zones qui dépassent) par de meilleurs modules pris ailleurs,
    à condition qu'ils s'emboîtent sur des tenons du reste du modèle (points d'accroche, brickforge/buildcheck.py)."""
    from brickforge.buildcheck import links_between, world_snaps
    placed = [dict(p) for p in lib.figs[base]["placed"]]
    keep = np.ones(len(placed), bool)
    added, log = [], []
    occ_base = lib.grid[base] >= 0
    for k, R in REGIONS.items():
        HR = H & R
        nHR = int(HR.sum())
        own_idx, own_vx = lib.module(base, k)

        def score(vx):
            if not len(vx):
                return 1.0 if nHR == 0 else 0.0
            inter = H[vx[:, 0], vx[:, 1], vx[:, 2]].sum()
            return inter / max(1, len(vx) + nHR - HR[vx[:, 0], vx[:, 1], vx[:, 2]].sum())
        cur = score(own_vx)
        rest_ids = [i for i in range(len(placed)) if keep[i] and i not in own_idx]
        rest = occ_base.copy()
        for i in own_idx:
            v = lib.vox[base][i]
            rest[v[:, 0], v[:, 1], v[:, 2]] = False
        ws_rest = None
        cands = []
        for j in range(len(lib.figs)):
            if j in banned or j == base:
                continue
            idx, vx = lib.module(j, k)
            if not idx:
                continue
            sc = sorted(((score(shifted(vx, d)), d) for d in SHIFTS), key=lambda a: -a[0])
            cands.append((sc[0][0], j, sc[:10], idx))
        empty = score(np.zeros((0, 3), int))
        cands.sort(key=lambda a: -a[0])
        choice = None
        for best, j, shifts, idx in cands[:8]:
            if best <= max(cur, empty) + 0.04:
                break
            if ws_rest is None:
                ws_rest = world_snaps([placed[i] for i in rest_ids])
            ws_mod = lib.module_snaps(j, k)
            for s_, d in shifts:
                if s_ <= max(cur, empty) + 0.04:
                    break
                vx = shifted(lib.module(j, k)[1], d)
                if not len(vx) or rest[vx[:, 0], vx[:, 1], vx[:, 2]].mean() > 0.12:
                    continue
                n = len(links_between(ws_rest, ws_mod, to_ldu(d)))
                if n >= 1:                                   # le module s'emboîte sur au moins un tenon du reste
                    choice = (s_, j, d, idx, n)
                    break
            if choice:
                break
        if choice:
            s_, j, d, idx, n = choice
            for i in own_idx:
                keep[i] = False
            off = to_ldu(d)
            for i in idx:
                p = lib.figs[j]["placed"][i]
                m = list(p["m"])
                m[0] += off[0]; m[1] += off[1]; m[2] += off[2]
                added.append({**p, "m": [round(v, 3) for v in m], "_from": lib.figs[j]["set"]})
            log.append((k, lib.figs[j]["set"], round(cur, 2), round(s_, 2), n))
        elif empty > cur + 0.04 and own_idx and nHR == 0:
            for i in own_idx:
                keep[i] = False
            log.append((k, "retiré", round(cur, 2), round(empty, 2), 0))
    return [p for p, k_ in zip(placed, keep) if k_] + added, log


def fill(placed, H, max_new=80):
    """Comble avec des plaques 1 × 1 posées UNIQUEMENT sur un tenon libre réel (dirigé vers le haut) :
    la plaque est accrochée par construction ; on n'en pose que si la case est dans le volume de la fiche et vide."""
    from brickforge.buildcheck import world_snaps
    occ = id_grid(placed) >= 0
    studs = [(pos, s) for (_i, pos, ax, s) in world_snaps(placed) if s["g"] == "M" and (-ax)[1] < -0.95 and s["len"] <= 6]
    free = {}
    for pos, s in studs:
        free[(round(pos[0]), round(pos[1]), round(pos[2]))] = True
    new = []

    def cell(x, ytop, z):
        """Cases de la grille (10 LDU) d'une plaque 1 × 1 dont le dessus est à ytop (LDraw, y vers le bas)."""
        ix0, ix1 = int(np.floor((x - 9) / 10 + NX / 2)), int(np.floor((x + 9) / 10 + NX / 2))
        iz0, iz1 = int(np.floor((z - 9) / 10 + NZ / 2)), int(np.floor((z + 9) / 10 + NZ / 2))
        iy0, iy1 = int(np.floor((-ytop - 7.5) / 10)), int(np.floor((-ytop - 0.5) / 10))
        return slice(ix0, ix1 + 1), slice(iy0, iy1 + 1), slice(iz0, iz1 + 1)
    changed = True
    while changed and len(new) < max_new:
        changed = False
        for (x, y, z) in sorted(free, key=lambda k: -k[1]):          # du bas vers le haut
            if not free.get((x, y, z)):
                continue
            ytop = y - 8
            sx, sy, sz = cell(x, ytop, z)
            if sx.start < 0 or sz.start < 0 or sx.stop > NX or sz.stop > NZ or sy.start < 0 or sy.stop > NY:
                continue
            ix, iy, iz = int((x) / 10 + NX / 2), int((-y + 4) / 10), int((z) / 10 + NZ / 2)
            if occ[sx, sy, sz].any() or not H[min(ix, NX - 1), min(iy, NY - 1), min(iz, NZ - 1)]:
                continue
            new.append({"part": "3024", "color": 16, "m": [float(x), float(ytop), float(z), 1, 0, 0, 0, 1, 0, 0, 0, 1], "_from": "comblement"})
            occ[sx, sy, sz] = True
            free[(x, y, z)] = False
            free[(x, ytop, z)] = True
            changed = True
            if len(new) >= max_new:
                break
    return placed + new, len(new)


# ---------------------------------------------------------------- mesures de forme

def shape_metrics(ref_placed, placed, fiche):
    a, b = solid(id_grid(ref_placed) >= 0), solid(id_grid(placed) >= 0)
    iou3 = (a & b).sum() / max(1, (a | b).sum())
    vb = views(id_grid(placed), placed)
    sil = {}
    for d in ("front", "left", "top"):
        x, y = fiche["views"][d] >= 0, vb[d] >= 0
        sil[d] = (x & y).sum() / max(1, (x | y).sum())
    t, v = fiche["views"]["front"], vb["front"]
    acc = ((t == v) & (t >= 0)).sum() / max(1, ((t >= 0) | (v >= 0)).sum())
    return {"iou3d": round(float(iou3), 3), "sil_front": round(float(sil["front"]), 3), "sil_side": round(float(sil["left"]), 3),
            "sil_top": round(float(sil["top"]), 3), "front_acc": round(float(acc), 3)}


def build(lib, fiches, t, real, version=2):
    ft = fiches[t]
    ban = names(lib.figs[t])
    banned = {j for j in range(len(lib.figs)) if j == t or names(lib.figs[j]) & ban}
    s, base = max((silhouette_score(ft, fiches[j]), j) for j in range(len(lib.figs)) if j not in banned)
    if version == 1:
        return recolor(lib.figs[base], ft, real=real), {"base": lib.figs[base]["set"], "grafts": [], "filled": 0}
    H = hull(ft)
    placed, log = graft(lib, base, H, banned)
    placed, nfill = fill(placed, H)
    out = recolor({"placed": placed}, ft, real=real, keep_hidden=True)
    out = [{**p, "color": (15 if p["color"] == 16 else p["color"])} for p in out]      # comblement caché : blanc par défaut
    out = harmonize_hidden(out, real)
    out, removed, _r = repair(out)                          # garantie : rien ne vole, rien ne se chevauche
    return out, {"base": lib.figs[base]["set"], "grafts": log, "filled": nfill, "removed": len(removed)}


def harmonize_hidden(placed, real=None):
    """Pièces cachées : couleur majoritaire de leurs voisines visibles (rien ne détonne si on les aperçoit en biais)."""
    from brickforge.bh_build import first_hit
    g = id_grid(placed)
    vis = set()
    for ax, rev in ((2, False), (2, True), (0, False), (0, True), (1, True)):
        k = first_hit(g, ax, rev)
        ii = np.nonzero(k >= 0)
        if ax == 2:
            ids = g[ii[0], ii[1], k[ii]]
        elif ax == 0:
            ids = g[k[ii], ii[0], ii[1]]
        else:
            ids = g[ii[0], k[ii], ii[1]]
        vis.update(ids.tolist())
    out = [dict(p) for p in placed]
    for i, p in enumerate(placed):
        if i in vis:
            continue
        m = ndimage.binary_dilation(g == i, iterations=2)
        neigh = Counter(placed[j]["color"] for j in g[m].tolist() if j >= 0 and j != i and j in vis)
        for c, _ in neigh.most_common():
            if real is None or real.exists(p["part"], c) is not False:
                out[i]["color"] = c
                break
    return out


def side_rgb(v, scale=4):
    """Vue de profil [y, z] → image."""
    import cv2
    img = np.full(v.shape + (3,), 200, np.uint8)
    for (r, c), code in np.ndenumerate(v[::-1]):
        if code >= 0:
            hx = COLS.get(int(code), ("", "999999"))[1]
            img[r, c] = [int(hx[i:i + 2], 16) for i in (4, 2, 0)]
    return cv2.resize(img, (img.shape[1] * scale, img.shape[0] * scale), interpolation=cv2.INTER_NEAREST)


def evaluate():
    import cv2
    from brickforge.bh_build import front_rgb
    figures = json.loads((OUT / "figures.json").read_text())
    print("bibliothèque…", flush=True)
    lib = Lib(figures)
    fiches = [fiche_of(f) for f in figures]
    real = RealCombos()
    rows = []
    show = {"40377-1#0", "41624-1#0", "40350-1#0", "40271-1#0", "41617-1#0", "41609-1#0", "40436-1#0", "41592-1#0"}
    tiles = []
    for t, f in enumerate(figures):
        r = {"key": fiches[t]["key"], "set": f["set"]}
        built = {}
        for ver in (1, 2):
            pl, info = build(lib, fiches, t, real, ver)
            built[ver] = pl
            m = shape_metrics(f["placed"], pl, fiches[t])
            ex = [real.exists(p["part"], p["color"]) for p in pl]
            ex = [e for e in ex if e is not None]
            r[f"v{ver}"] = {**m, "real": round(sum(ex) / max(1, len(ex)), 3), "parts": len(pl), **info}
        rows.append(r)
        print(f"{r['key']:10} {f['set'][:24]:24} v1 vol {r['v1']['iou3d']:.2f} profil {r['v1']['sil_side']:.2f} face {r['v1']['front_acc']:.2f}"
              f"  →  v2 vol {r['v2']['iou3d']:.2f} profil {r['v2']['sil_side']:.2f} face {r['v2']['front_acc']:.2f}  greffes {[g[0] + ':' + g[1][:14] for g in r['v2']['grafts']]} +{r['v2']['filled']}", flush=True)
        if r["key"] in show:
            ref_v = views(id_grid(f["placed"]), f["placed"])
            ims = []
            for pl in (f["placed"], built[1], built[2]):
                v = views(id_grid(pl), pl)
                ims += [front_rgb(v["front"]), side_rgb(v["left"])]
            crop = lambda im: im[im.shape[0] - 36 * 4 * 8 // 10:]
            sep = lambda im: np.full((crop(im).shape[0], 10, 3), 255, np.uint8)
            row = []
            for i, im in enumerate(ims):
                row += [crop(im), sep(im) if i % 2 else np.full((crop(im).shape[0], 3, 3), 255, np.uint8)]
            tiles.append(np.hstack(row))
    cv2.imwrite(str(ASSETS / "09d-v2-forme.png"), np.vstack([np.pad(t_, ((5, 5), (0, 0), (0, 0)), constant_values=255) for t_ in tiles]))
    summ = {}
    for ver in ("v1", "v2"):
        summ[ver] = {k: float(np.median([r[ver][k] for r in rows])) for k in ("iou3d", "sil_front", "sil_side", "sil_top", "front_acc", "real", "parts")}
    summ["v2_better_3d"] = sum(r["v2"]["iou3d"] > r["v1"]["iou3d"] + 0.01 for r in rows)
    summ["v2_worse_3d"] = sum(r["v2"]["iou3d"] < r["v1"]["iou3d"] - 0.01 for r in rows)
    summ["grafts"] = Counter(g[0] for r in rows for g in r["v2"]["grafts"])
    (OUT / "rebuild_v2_eval.json").write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1))
    print(json.dumps(summ, ensure_ascii=False, indent=1))


def build_one(num, fig):
    from brickforge import omr
    figures = json.loads((OUT / "figures.json").read_text())
    t = next(i for i, f in enumerate(figures) if f["num"] == num and f["fig"] == int(fig))
    lib = Lib(figures)
    fiches = [fiche_of(f) for f in figures]
    real = RealCombos()
    pl, info = build(lib, fiches, t, real, 2)
    m = shape_metrics(figures[t]["placed"], pl, fiches[t])
    name = "lego_bh_" + "".join(ch if ch.isalnum() else "_" for ch in figures[t]["set"].lower()).strip("_")[:30] + "_v2"
    d = OUT / "builds"
    d.mkdir(exist_ok=True)
    to_mpd(pl, name, d / f"{name}.mpd", author="Brick Forge v2 (gabarit + modules + comblement)")
    omr.import_set(d / f"{name}.mpd", name, f"https://cdn.rebrickable.com/media/sets/{num}.jpg")
    print(figures[t]["set"], info, m)




# ---------------------------------------------------------------- constructibilité (brickforge/buildcheck.py)

def repair(placed, max_rounds=4):
    """Rend le modèle constructible : retire les pièces qui volent, puis, pour chaque collision, la pièce ajoutée
    (greffe ou comblement) plutôt que celle du gabarit ; recommence tant qu'il reste des défauts."""
    from brickforge.buildcheck import check
    removed = []
    for _ in range(max_rounds):
        r = check(placed)
        drop = set(r["floating"])
        for i, j, _n in r["collisions"]:
            a, b = placed[i], placed[j]
            if "_from" in a and "_from" not in b:
                drop.add(i)
            elif "_from" in b and "_from" not in a:
                drop.add(j)
            else:
                drop.add(i if len(part_tris_count(a)) < len(part_tris_count(b)) else j)
        if not drop:
            return placed, removed, r
        removed += [placed[i]["part"] for i in drop]
        placed = [p for k, p in enumerate(placed) if k not in drop]
    return placed, removed, check(placed)


def part_tris_count(p):
    from brickforge.ldlib import part_triangles
    return part_triangles(p["part"])


def audit():
    """v1 / v2 / v2 réparée : pièces qui volent, collisions, puis forme et couleur."""
    from brickforge.buildcheck import check
    figures = json.loads((OUT / "figures.json").read_text())
    lib = Lib(figures)
    fiches = [fiche_of(f) for f in figures]
    real = RealCombos()
    rows = []
    for t, f in enumerate(figures):
        row = {"key": fiches[t]["key"], "set": f["set"]}
        off = check(f["placed"])
        row["officiel"] = {"floating": len(off["floating"]), "collisions": len(off["collisions"])}
        for ver in (1, 2):
            pl, info = build(lib, fiches, t, real, ver)
            r = check(pl)
            row[f"v{ver}"] = {"floating": len(r["floating"]), "collisions": len(r["collisions"]), "parts": len(pl),
                              **shape_metrics(f["placed"], pl, fiches[t])}
            if ver == 2:
                rp, removed, r2 = repair(pl)
                rp = recolor({"placed": rp}, fiches[t], real=real)
                row["v2r"] = {"floating": len(r2["floating"]), "collisions": len(r2["collisions"]), "parts": len(rp),
                              "removed": len(removed), **shape_metrics(f["placed"], rp, fiches[t])}
        rows.append(row)
        print(f"{row['key']:10} {f['set'][:24]:24} officiel {row['officiel']['floating']:2}/{row['officiel']['collisions']}  "
              f"v1 volent {row['v1']['floating']:2} coll {row['v1']['collisions']}  v2 volent {row['v2']['floating']:2} coll {row['v2']['collisions']}  "
              f"v2 réparée {row['v2r']['floating']}/{row['v2r']['collisions']} (−{row['v2r']['removed']})", flush=True)
    summ = {}
    for k in ("officiel", "v1", "v2", "v2r"):
        summ[k] = {"sans_defaut": sum(r[k]["floating"] == 0 and r[k]["collisions"] == 0 for r in rows),
                   "volent_total": sum(r[k]["floating"] for r in rows),
                   "avec_collision": sum(r[k]["collisions"] > 0 for r in rows)}
        for m in ("iou3d", "sil_side", "front_acc", "parts"):
            if m in rows[0].get(k, {}):
                summ[k][m] = float(np.median([r[k][m] for r in rows]))
    (OUT / "buildcheck_eval.json").write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1))
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if "--audit" in sys.argv:
        audit()
    elif len(sys.argv) >= 3:
        build_one(sys.argv[1], sys.argv[2])
    else:
        evaluate()
