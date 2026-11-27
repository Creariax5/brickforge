"""Étape 3 du focus BrickHeadz : construire une figurine à partir d'une fiche.

Fiche = 5 vues orthographiques en cases de 10 LDU (face, dos, gauche, droite, dessus), dans le repère du gabarit
(face vers -Z, origine = axe de la tête, dessous du socle), avec les options déduites (au-dessus de la tête, oreilles…).

Construction (v1, « greffe ») :
  1. gabarit = un vrai BrickHeadz dont la silhouette (face + profil) est la plus proche de la fiche → constructible par construction ;
  2. chaque pièce visible est recolorée par vote : ses cases visibles depuis chaque direction lisent la vue correspondante de la fiche ;
  3. les pièces cachées gardent leur couleur ;
  4. on vérifie que chaque (pièce, couleur) existe dans au moins un vrai set (inventaires Rebrickable).

Test : chaque figurine officielle est reconstruite depuis sa propre fiche avec le gabarit d'une AUTRE figurine (validation croisée).

    python -m brickforge.bh_build                 # validation croisée sur les 101 figurines + note
    python -m brickforge.bh_build 40377-1 0       # reconstruit Donald, l'exporte en .mpd et en sujet de l'app
"""

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import ndimage

from brickforge.brickheadz import ASSETS, COLS, OUT, title
from brickforge.brickheadz_zones import NX, NY, NZ, sample, to_idx, tris

ROOT = Path(__file__).resolve().parent.parent
DIRS = ("front", "back", "left", "right", "top")


# ---------------------------------------------------------------- voxels avec identité de pièce

def id_grid(placed, rng=None):
    rng = rng or np.random.default_rng(0)
    g = np.full((NX, NY, NZ), -1, np.int32)
    for i, p in enumerate(placed):
        t = tris(p)
        if not len(t):
            continue
        ix, iy, iz = to_idx(sample(t, rng))
        ok = (ix >= 0) & (ix < NX) & (iy >= 0) & (iy < NY) & (iz >= 0) & (iz < NZ)
        g[ix[ok], iy[ok], iz[ok]] = i
    return g


def first_hit(g, axis, rev):
    """Pour chaque rayon le long de `axis` : indice (dans la grille) de la première case pleine, ou -1."""
    occ = g >= 0
    if rev:
        occ = np.flip(occ, axis)
    has = occ.any(axis)
    k = np.argmax(occ, axis)
    if rev:
        k = g.shape[axis] - 1 - k
    return np.where(has, k, -1)


def views(g, placed):
    """5 vues : image [lignes, colonnes] de codes couleur LDraw (-1 = vide) + l'indice de profondeur de chaque pixel."""
    col = np.vectorize(lambda i: placed[i]["color"] if i >= 0 else -1, otypes=[np.int32])
    out = {}
    spec = {"front": (2, False), "back": (2, True), "left": (0, False), "right": (0, True), "top": (1, True)}
    for d, (ax, rev) in spec.items():
        k = first_hit(g, ax, rev)
        idx = np.full(k.shape, -1, np.int32)
        m = k >= 0
        ii = np.nonzero(m)
        if ax == 2:
            idx[ii] = g[ii[0], ii[1], k[ii]]
        elif ax == 0:
            idx[ii] = g[k[ii], ii[0], ii[1]]
        else:
            idx[ii] = g[ii[0], k[ii], ii[1]]
        out[d] = col(idx)                            # front/back : [x, y] ; left/right : [y, z] ; top : [x, z]
    return out


# ---------------------------------------------------------------- fiche

def fiche_of(fig):
    g = id_grid(fig["placed"])
    v = views(g, fig["placed"])
    up = (g >= 0)[:, int(np.ceil(27.5 * 8 / 10)):, :]
    return {"key": f"{fig['num']}#{fig['fig']}", "set": fig["set"], "views": v,
            "options": {"above_head": bool(up.any()),
                        "ears_or_horns": bool(up[:NX // 2 - 2].any() and up[NX // 2 + 2:].any() and not up[NX // 2 - 1:NX // 2 + 1].any())}}


def silhouette_score(fa, fb):
    """IoU moyen des masques de face et de profil."""
    s = []
    for d in ("front", "left"):
        a, b = fa["views"][d] >= 0, fb["views"][d] >= 0
        s.append((a & b).sum() / max(1, (a | b).sum()))
    return float(np.mean(s))


# ---------------------------------------------------------------- existence (pièce, couleur) dans de vrais sets

class RealCombos:
    def __init__(self):
        db = sqlite3.connect(ROOT / "data" / "rebrickable" / "rb.sqlite")
        norm = lambda n: n.lower().replace("_", "").replace(" ", "").replace("-", "").replace("grey", "gray").replace("trans", "trans")
        by_name = {norm(r[1]): r[0] for r in db.execute("SELECT id, name FROM colors")}
        rb = {r[0]: r[1].upper() for r in db.execute("SELECT id, rgb FROM colors")}
        by_hex = {}
        for k, hx in rb.items():
            by_hex.setdefault(hx, k)
        rgb = lambda h: np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)])
        keys, arr = list(rb), np.stack([rgb(h) for h in rb.values()])
        self.ld2rb = {}
        for code, (name, hx) in COLS.items():
            hx = hx.upper()
            c = by_name.get(norm(name))                 # attention : l'id Rebrickable du noir est 0
            if c is None:
                c = by_hex.get(hx)
            if c is None:
                c = keys[int(np.argmin(((arr - rgb(hx)) ** 2).sum(1)))]
            self.ld2rb[code] = c
        self.combos = set(db.execute("SELECT DISTINCT part, color FROM inv").fetchall())
        self.parts = {p for p, _ in self.combos}

    def exists(self, part, color):
        rc = self.ld2rb.get(color)
        cands = [part, part.split("p")[0] if "p" in part[1:] else part, part.rstrip("abc")]
        known = [c for c in cands if c in self.parts]
        if not known:
            return None                               # pièce inconnue de Rebrickable (nom LDraw différent) : on ne juge pas
        return any((c, rc) in self.combos for c in known)


# ---------------------------------------------------------------- construction

def recolor(template, fiche, keep_hidden=True, real=None):
    """Recolore les pièces visibles du gabarit d'après les 5 vues de la fiche (vote par case visible)."""
    placed = template["placed"]
    g = id_grid(placed)
    occ = g >= 0
    # pour chaque direction : la vue de la fiche, complétée par la couleur pleine la plus proche (silhouettes différentes)
    filled = {}
    for d in DIRS:
        v = fiche["views"][d]
        if (v >= 0).any():
            _, (ia, ib) = ndimage.distance_transform_edt(v < 0, return_indices=True)
            filled[d] = v[ia, ib]
        else:
            filled[d] = v
    votes = [Counter() for _ in placed]
    spec = {"front": (2, False), "back": (2, True), "left": (0, False), "right": (0, True), "top": (1, True)}
    w = {"front": 3.0, "back": 1.0, "left": 1.5, "right": 1.5, "top": 1.0}
    for d, (ax, rev) in spec.items():
        k = first_hit(g, ax, rev)
        ii = np.nonzero(k >= 0)
        if ax == 2:
            pid = g[ii[0], ii[1], k[ii]]
        elif ax == 0:
            pid = g[k[ii], ii[0], ii[1]]
        else:
            pid = g[ii[0], k[ii], ii[1]]
        cols = filled[d][ii]
        for p, c in zip(pid.tolist(), cols.tolist()):
            if c >= 0:
                votes[p][c] += w[d]
    # pièces du gabarit hors de la silhouette de la fiche (oreilles de Batman sur Donald…) : retirées si elles ne portent rien
    fm = ndimage.binary_dilation(fiche["views"]["front"] >= 0, iterations=1)       # [x, y]
    sm = ndimage.binary_dilation(fiche["views"]["left"] >= 0, iterations=1)        # [y, z]
    drop = set()
    for i, p in enumerate(placed):
        vx = np.argwhere(g == i)
        if not len(vx):
            continue
        h_pl = vx[:, 1].mean() * 10 / 8                    # hauteur moyenne en plates
        x_st = np.abs(vx[:, 0] - NX / 2 + 0.5).mean() / 2  # écart à l'axe en tenons
        if not (h_pl >= 26 or x_st > 3.5):                 # seulement au-dessus de la tête ou hors gabarit
            continue
        inside = (fm[vx[:, 0], vx[:, 1]] & sm[vx[:, 1], vx[:, 2]]).mean()
        if inside < 0.15:
            drop.add(i)
    out = []
    for i, p in enumerate(placed):
        if i in drop:
            continue
        if votes[i]:
            ranked = [c for c, _ in votes[i].most_common()]
            c = ranked[0]
            if real is not None:                          # couleur suivante du vote si la pièce n'existe pas dans cette couleur
                c = next((x for x in ranked if real.exists(p["part"], x) is not False), c)
        else:
            c = p["color"] if keep_hidden else 16
        out.append({**p, "color": int(c)})
    return out


def front_accuracy(fiche, placed):
    """Part des pixels de la vue de face (union des silhouettes) qui ont la bonne couleur ; IoU de la silhouette."""
    v = views(id_grid(placed), placed)["front"]
    t = fiche["views"]["front"]
    a, b = t >= 0, v >= 0
    u = a | b
    return float(((t == v) & a).sum() / max(1, u.sum())), float((a & b).sum() / max(1, u.sum()))


STOP = {"the", "and", "mr.", "mrs.", "dr.", "&", "of", "in", "with", "lego", "new", "year", "chinese", "captain"}


def names(fig):
    return {w for w in fig["set"].lower().replace(",", " ").split() if len(w) > 2 and w not in STOP} | {fig["num"]}


def rebuild(fiches, figures, target, exclude_self=True, real=None):
    """Gabarit le plus proche, hors la cible et hors tout set qui partage un nom de personnage avec elle (pas de triche)."""
    ft = fiches[target]
    ban = names(figures[target]) if exclude_self else set()
    scores = sorted(((silhouette_score(ft, fiches[j]), j) for j in range(len(figures))
                     if not (exclude_self and (j == target or names(figures[j]) & ban))), reverse=True)
    s, j = scores[0]
    return recolor(figures[j], ft, real=real), j, s


def to_mpd(placed, name, path, author="Brick Forge (greffe sur gabarit)"):
    lines = [f"0 FILE {name}.ldr", f"0 {name}", f"0 Name: {name}.ldr", f"0 Author: {author}", "0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt", ""]
    for p in placed:
        x, y, z, *m = p["m"]
        lines.append("1 %d %s %s %s %s %s.dat" % (p["color"], *(f"{v:g}" for v in (x, y, z)), " ".join(f"{v:g}" for v in m), p["part"]))
    lines.append("0 NOFILE")
    Path(path).write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------- validation croisée

def front_rgb(v, scale=4):
    img = np.full(v.T.shape + (3,), 200, np.uint8)        # v : [x, y] → image [y, x]
    vt = v.T[::-1]
    for (r, c), code in np.ndenumerate(vt):
        if code >= 0:
            hx = COLS.get(int(code), ("", "999999"))[1]
            img[r, c] = [int(hx[i:i + 2], 16) for i in (4, 2, 0)]
    import cv2
    return cv2.resize(img, (img.shape[1] * scale, img.shape[0] * scale), interpolation=cv2.INTER_NEAREST)


def evaluate():
    import cv2
    figures = json.loads((OUT / "figures.json").read_text())
    print("fiches…", flush=True)
    fiches = [fiche_of(f) for f in figures]
    real = RealCombos()
    rows, tiles = [], []
    for t, f in enumerate(figures):
        built, j, s = rebuild(fiches, figures, t, real=real)
        acc, iou = front_accuracy(fiches[t], built)
        base_acc, _ = front_accuracy(fiches[t], figures[j]["placed"])            # gabarit sans recoloration
        ex = [real.exists(p["part"], p["color"]) for p in built]
        judged = [e for e in ex if e is not None]
        bad = Counter((p["part"], p["color"]) for p, e in zip(built, ex) if e is False)
        rows.append({"key": fiches[t]["key"], "set": f["set"], "template": fiches[j]["key"], "template_set": figures[j]["set"],
                     "silhouette": round(s, 3), "front_acc": round(acc, 3), "front_iou": round(iou, 3), "baseline_acc": round(base_acc, 3),
                     "real_combo": round(sum(judged) / max(1, len(judged)), 3),
                     "unreal": [(p, title(p), COLS.get(c, (str(c),))[0], n) for (p, c), n in bad.most_common(6)]})
        if len(tiles) < 60:
            a = front_rgb(fiches[t]["views"]["front"])
            b = front_rgb(views(id_grid(built), built)["front"])
            tiles.append(np.hstack([a, np.full((a.shape[0], 4, 3), 255, np.uint8), b]))
        print(f"{rows[-1]['key']:10} {f['set'][:26]:26} ← gabarit {figures[j]['set'][:22]:22} silh {s:.2f}  face {acc:.2f} (sans recolorer {base_acc:.2f})  combos réels {rows[-1]['real_combo']:.0%}", flush=True)
    # planche : officielle | reconstruite
    crop = lambda im: im[im.shape[0] - 40 * 4 * 8 // 10:]                       # 40 plates du bas
    tiles = [np.pad(crop(x), ((6, 6), (6, 6), (0, 0)), constant_values=255) for x in tiles]
    cols = 10
    sheet = [np.hstack(tiles[i:i + cols] + [np.full_like(tiles[0], 255)] * (cols - len(tiles[i:i + cols]))) for i in range(0, len(tiles), cols)]
    cv2.imwrite(str(ASSETS / "09c-reconstructions.png"), np.vstack(sheet))
    summ = {k: float(np.median([r[k] for r in rows])) for k in ("silhouette", "front_acc", "front_iou", "baseline_acc", "real_combo")}
    allbad = Counter()
    for r in rows:
        for p, t_, c, n in r["unreal"]:
            allbad[(p, t_, c)] += n
    summ["unreal_top"] = [(*k, n) for k, n in allbad.most_common(15)]
    (OUT / "rebuild_eval.json").write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1))
    print(json.dumps(summ, ensure_ascii=False, indent=1))


def build_one(num, fig):
    from brickforge import omr
    figures = json.loads((OUT / "figures.json").read_text())
    t = next(i for i, f in enumerate(figures) if f["num"] == num and f["fig"] == int(fig))
    fiches = [fiche_of(f) for f in figures]
    built, j, s = rebuild(fiches, figures, t, real=RealCombos())
    acc, iou = front_accuracy(fiches[t], built)
    name = "lego_bh_" + "".join(ch if ch.isalnum() else "_" for ch in figures[t]["set"].lower()).strip("_")[:30] + "_v1"
    d = OUT / "builds"
    d.mkdir(exist_ok=True)
    mpd = d / f"{name}.mpd"
    to_mpd(built, name, mpd)
    omr.import_set(mpd, name, f"https://cdn.rebrickable.com/media/sets/{num}.jpg")
    off = d / f"{name}_officiel.mpd"
    to_mpd(figures[t]["placed"], name + "_officiel", off, author="LDraw OMR")
    omr.import_set(off, name.replace("_v1", "_officiel"), f"https://cdn.rebrickable.com/media/sets/{num}.jpg")
    print(f"{figures[t]['set']} ← gabarit {figures[j]['set']} (silhouette {s:.2f}) · face {acc:.0%} · sujets {name} et {name.replace('_v1', '_officiel')}")


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        build_one(sys.argv[1], sys.argv[2])
    else:
        evaluate()
