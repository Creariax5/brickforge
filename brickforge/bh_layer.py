"""Étape 4 du focus BrickHeadz : construire une figurine couche par couche, à partir de rien.

Cible = un volume en cases LEGO (1 tenon × 1 plate × 1 tenon) avec une couleur par case de surface.
  - cible « 3D »   : volume du vrai modèle (borne haute : sait-on construire une forme donnée ?)
  - cible « fiche » : volume déduit des 5 vues (comparable à v1 / v2, qui ne voient que la fiche)

Construction, de bas en haut :
  1. à chaque couche, on couvre les cases cibles avec des plaques et des briques réelles ;
     une pièce doit poser sur au moins un tenon de la couche du dessous (rien ne vole, par construction) ;
     on préfère les grandes pièces et celles qui chevauchent plusieurs pièces du dessous (joints décalés) ;
  2. les cases en surplomb restées vides sont reprises en passe descendante (pièce accrochée sous une pièce) ;
  3. couleur : celle des cases visibles couvertes (une seule par pièce) ; les pièces cachées prennent la couleur
     visible la plus proche ; chaque (pièce, couleur) doit exister dans un vrai set ;
  4. vérification finale par le moteur de constructibilité (brickforge/buildcheck.py).

    python -m brickforge.bh_layer                 # évaluation sur les 101 figurines + image de la note
    python -m brickforge.bh_layer 40377-1 0       # construit Donald, l'exporte en sujet de l'app
"""

import json
import sys
from collections import Counter
from functools import lru_cache

import numpy as np
from scipy import ndimage

from brickforge.bh_build import RealCombos, fiche_of, first_hit, front_rgb, id_grid, to_mpd
from brickforge.bh_build2 import hull, shape_metrics, side_rgb, solid
from brickforge.brickheadz import ASSETS, OUT
from brickforge.brickheadz_zones import NX, NY, NZ, V
from brickforge.ldlib import part_triangles

CW, CH = 20.0, 8.0                 # case : un tenon de large, une plate de haut
GX, GZ = 16, 16                    # 16 × 16 tenons
GY = int(NY * V / CH)              # même hauteur que la grille 10 LDU
NEED = 3                           # échantillons pleins (sur 4) pour qu'une case soit pleine

PLATES = ["3958", "3032", "3031", "3034", "3795", "3020", "3021", "3022", "3460", "3666", "3710", "3623", "3023", "3024"]
BRICKS = ["3007", "2456", "3001", "3002", "3003", "3008", "3009", "3010", "3622", "3004", "3005"]
ROT90 = [0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0]
IDENT = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]


@lru_cache(maxsize=None)
def footprint(part):
    t = part_triangles(part).reshape(-1, 3)
    sx, sz = (t[:, 0].max() - t[:, 0].min()) / CW, (t[:, 2].max() - t[:, 2].min()) / CW
    return int(round(sx)), int(round(sz))


def shapes():
    """(pièce, hauteur en plates, largeur X, profondeur Z, rotation) — chaque orientation distincte."""
    out = []
    for parts, h in ((BRICKS, 3), (PLATES, 1)):
        for p in parts:
            w, d = footprint(p)
            out.append((p, h, w, d, IDENT))
            if w != d:
                out.append((p, h, d, w, ROT90))
    return out


# ---------------------------------------------------------------- cibles

def colored10_from_model(placed):
    """Grille 10 LDU : code couleur sur la surface, -2 à l'intérieur, -1 vide."""
    g = id_grid(placed)
    occ = solid(g >= 0)
    col = np.full(g.shape, -1, np.int32)
    col[occ] = -2
    m = g >= 0
    col[m] = np.array([p["color"] for p in placed])[g[m]]
    return col


def colored10_from_fiche(fiche):
    """Grille 10 LDU : volume déduit des vues ; chaque case de surface prend la couleur de la vue qui la voit."""
    H = hull(fiche)
    col = np.full(H.shape, -1, np.int32)
    col[H] = -2
    v = fiche["views"]
    g = np.where(H, 0, -1)
    for d, ax, rev in (("back", 2, True), ("right", 0, True), ("left", 0, False), ("top", 1, True), ("front", 2, False)):
        k = first_hit(g, ax, rev)
        ii = np.nonzero(k >= 0)
        img = v[d]
        if ax == 2:
            col[ii[0], ii[1], k[ii]] = img[ii[0], ii[1]]
        elif ax == 0:
            col[k[ii], ii[0], ii[1]] = img[ii[0], ii[1]]
        else:
            col[ii[0], k[ii], ii[1]] = img[ii[0], ii[1]]
    return col


def to_cells(col10, ox, oz, need=2):
    """Rééchantillonne en cases LEGO. Retour : occ [GX,GY,GZ], couleur (-1 = cachée / libre)."""
    xs = (np.arange(GX) - GX / 2) * CW + ox
    zs = (np.arange(GZ) - GZ / 2) * CW + oz
    occ = np.zeros((GX, GY, GZ), bool)
    col = np.full((GX, GY, GZ), -1, np.int32)
    for j in range(GY):
        iy = int(np.floor((j + 0.5) * CH / V))
        if iy >= NY:
            break
        for a, x in enumerate(xs):
            for b, z in enumerate(zs):
                samp = []
                for dx in (5, 15):
                    for dz in (5, 15):
                        ix, iz = int(np.floor((x + dx) / V + NX / 2)), int(np.floor((z + dz) / V + NZ / 2))
                        if 0 <= ix < NX and 0 <= iz < NZ:
                            samp.append(col10[ix, iy, iz])
                full = [s for s in samp if s != -1]
                if len(full) >= need:
                    occ[a, j, b] = True
                    vis = [s for s in full if s >= 0]
                    if vis:
                        col[a, j, b] = Counter(vis).most_common(1)[0][0]
    surf = occ & ~ndimage.binary_erosion(occ, border_value=0)
    col[~surf] = -1                                     # intérieur : couleur libre
    return occ, col


def target(col10, need=NEED):
    """Choisit le décalage de la grille des tenons (0 ou 10 LDU) qui colle le mieux au volume."""
    best = None
    for ox in (0.0, 10.0):
        for oz in (0.0, 10.0):
            occ, col = to_cells(col10, ox, oz, need)
            s = (col10 != -1).sum() * (V ** 3) / (CW * CW * CH)
            score = -abs(occ.sum() - s)
            if best is None or score > best[0]:
                best = (score, occ, col, ox, oz)
    return best[1:]


# ---------------------------------------------------------------- construction

class Builder:
    def __init__(self, occ, col, real=None):
        self.T, self.C, self.real = occ, col, real
        self.free = occ.copy()                                  # cases cibles pas encore couvertes
        self.top = np.full(occ.shape, -1, np.int32)            # pièce dont le dessus est dans cette case
        self.bot = np.full(occ.shape, -1, np.int32)            # pièce dont le dessous est dans cette case
        self.pieces = []
        self.shapes = shapes()
        self.fillcol = self._fill_colors()

    def _fill_colors(self):
        """Pour chaque case : couleur visible la plus proche dans la même couche (pour les pièces cachées)."""
        out = np.full(self.C.shape, 15, np.int32)
        for j in range(GY):
            lay = self.C[:, j, :]
            vis = lay >= 0
            if not vis.any():
                continue
            _, (ia, ib) = ndimage.distance_transform_edt(~vis, return_indices=True)
            out[:, j, :] = lay[ia, ib]
        return out

    def _color(self, part, cells):
        c = self.C[cells]
        vis = set(c[c >= 0].tolist())
        if len(vis) > 1:
            return None
        if vis:
            colr = vis.pop()
        else:
            colr = Counter(self.fillcol[cells].ravel().tolist()).most_common(1)[0][0]
        if self.real is not None and self.real.exists(part, colr) is False:
            return None
        return colr

    def layer(self, j, down=False):
        """Couvre la couche j. Montée : appui sur un dessus en j-1. Descente : accroche sous un dessous en j+1."""
        cands = []
        for (part, h, w, d, rot) in self.shapes:
            if down and h > 1:
                continue
            j1 = j + h
            if j1 > GY:
                continue
            for a in range(GX - w + 1):
                for b in range(GZ - d + 1):
                    sl = (slice(a, a + w), slice(j, j1), slice(b, b + d))
                    if not self.free[sl].all():
                        continue
                    if down:
                        if j1 >= GY:
                            continue
                        hold = self.bot[a:a + w, j1, b:b + d]
                    elif j == 0:
                        hold = np.zeros((w, d), np.int32)       # posé sur le socle (sol)
                    else:
                        hold = self.top[a:a + w, j - 1, b:b + d]
                    under = set(hold[hold >= 0].tolist())
                    if j > 0 and not down and not under:
                        continue
                    if down and not under:
                        continue
                    colr = self._color(part, sl)
                    if colr is None:
                        continue
                    vol = w * d * h
                    bridge = int((hold < 0).sum()) if j > 0 else 0       # cases en surplomb portées par cette pièce
                    score = vol + 1.5 * min(len(under), 4) - (0.8 if len(under) == 1 and j > 0 else 0) + 2.0 * bridge
                    cands.append((score, part, h, a, b, w, d, rot, colr))
        cands.sort(key=lambda c: -c[0])
        n = 0
        for score, part, h, a, b, w, d, rot, colr in cands:
            sl = (slice(a, a + w), slice(j, j + h), slice(b, b + d))
            if not self.free[sl].all():
                continue
            i = len(self.pieces)
            self.pieces.append({"part": part, "color": int(colr), "cell": (a, j, b, w, h, d), "rot": rot})
            self.free[sl] = False
            self.top[a:a + w, j + h - 1, b:b + d] = i
            self.bot[a:a + w, j, b:b + d] = i
            n += 1
        return n

    def run(self):
        for j in range(GY):
            if self.free[:, j, :].any():
                self.layer(j)
        for _ in range(2):                                      # surplombs : accrochés sous la couche du dessus
            for j in range(GY - 2, -1, -1):
                if self.free[:, j, :].any():
                    self.layer(j, down=True)
        self.prune()
        return self

    def prune(self):
        """Ne garde que le plus gros bloc posé au sol ; le reste ne tient à rien."""
        n = len(self.pieces)
        if not n:
            return
        par = list(range(n))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i
        for j in range(GY - 1):
            a, b = self.top[:, j, :], self.bot[:, j + 1, :]
            m = (a >= 0) & (b >= 0)
            for i, k in set(zip(a[m].tolist(), b[m].tolist())):
                par[find(i)] = find(k)
        vol = Counter()
        for i, p in enumerate(self.pieces):
            vol[find(i)] += p["cell"][3] * p["cell"][4] * p["cell"][5]
        grounded = {find(i) for i, p in enumerate(self.pieces) if p["cell"][1] == 0}
        g = max(grounded or vol, key=lambda r: vol[r])            # le plus gros bloc posé au sol
        keep = [find(i) == g for i in range(n)]
        for i, p in enumerate(self.pieces):
            if not keep[i]:
                a, j, b, w, h, d = p["cell"]
                self.free[a:a + w, j:j + h, b:b + d] = True
        self.pieces = [p for i, p in enumerate(self.pieces) if keep[i]]

    def placed(self, ox, oz):
        out = []
        for p in self.pieces:
            a, j, b, w, h, d = p["cell"]
            x = (a + w / 2 - GX / 2) * CW + ox
            z = (b + d / 2 - GZ / 2) * CW + oz
            y = -(j + h) * CH
            out.append({"part": p["part"], "color": p["color"], "m": [x, y, z] + list(p["rot"])})
        return out


def build(col10, real=None):
    occ, col, ox, oz = target(col10)
    B = Builder(occ, col, real).run()
    pl = B.placed(ox, oz)
    return pl, {"cells": int(occ.sum()), "missed": int(B.free.sum()), "ox": ox, "oz": oz}


# ---------------------------------------------------------------- évaluation

def evaluate(limit=None):
    import cv2
    from brickforge import buildcheck
    figures = json.loads((OUT / "figures.json").read_text())
    real = RealCombos()
    rows, tiles = [], []
    show = {"40377-1#0", "41624-1#0", "40350-1#0", "40271-1#0", "41617-1#0", "41609-1#0", "40436-1#0", "41592-1#0"}
    for t, f in enumerate(figures[:limit]):
        fiche = fiche_of(f)
        r = {"key": fiche["key"], "set": f["set"], "official_parts": len(f["placed"])}
        imgs = []
        for kind, c10 in (("3d", colored10_from_model(f["placed"])), ("fiche", colored10_from_fiche(fiche))):
            pl, info = build(c10, real)
            chk = buildcheck.check(pl)
            m = shape_metrics(f["placed"], pl, fiche)
            r[kind] = {**info, **m, "parts": len(pl), "floating": len(chk["floating"]), "collisions": len(chk["collisions"])}
            if fiche["key"] in show:
                v = fiche_of({**f, "placed": pl})["views"]
                imgs.append((front_rgb(v["front"]), side_rgb(v["left"])))
        rows.append(r)
        print(f"{r['key']:10s} {f['set'][:22]:22s} " + "  ".join(
            f"{k}: {r[k]['parts']}p vol {r[k]['floating']} coll {r[k]['collisions']} rate {r[k]['missed']} iou {r[k]['iou3d']} face {r[k]['front_acc']}"
            for k in ("3d", "fiche")), flush=True)
        if imgs:
            v = fiche["views"]
            tiles.append([(front_rgb(v["front"]), side_rgb(v["left"]))] + imgs)
    med = lambda k, q: float(np.median([r[k][q] for r in rows]))
    summ = {k: {"sans_defaut": sum(r[k]["floating"] == 0 and r[k]["collisions"] == 0 for r in rows),
                "volent_total": sum(r[k]["floating"] for r in rows),
                "avec_collision": sum(r[k]["collisions"] > 0 for r in rows),
                **{q: round(med(k, q), 3) for q in ("iou3d", "sil_front", "sil_side", "sil_top", "front_acc", "parts", "missed")}}
            for k in ("3d", "fiche")}
    summ["official_parts"] = float(np.median([r["official_parts"] for r in rows]))
    (OUT / "layer_eval.json").write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1))
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    if tiles:
        def strip(row):
            cols = []
            for fr, sd in row:
                h = max(fr.shape[0], sd.shape[0])
                pad = lambda a: np.pad(a, ((h - a.shape[0], 0), (0, 6), (0, 0)), constant_values=255)
                cols.append(np.hstack([pad(fr), pad(sd), np.full((h, 14, 3), 255, np.uint8)]))
            return np.hstack(cols)
        ss = [strip(r) for r in tiles]
        W = max(s.shape[1] for s in ss)
        H = max(s.shape[0] for s in ss)
        img = np.vstack([np.pad(s, ((H - s.shape[0], 8), (0, W - s.shape[1]), (0, 0)), constant_values=255) for s in ss])
        cv2.imwrite(str(ASSETS / "09f-couches.png"), img)


def build_one(num, fig):
    from brickforge import buildcheck, omr
    figures = json.loads((OUT / "figures.json").read_text())
    f = next(f for f in figures if f["num"] == num and f["fig"] == int(fig))
    fiche = fiche_of(f)
    real = RealCombos()
    base = "lego_bh_" + "".join(ch if ch.isalnum() else "_" for ch in f["set"].lower()).strip("_")[:30]
    d = OUT / "builds"
    d.mkdir(exist_ok=True)
    for kind, c10 in (("couches3d", colored10_from_model(f["placed"])), ("couches", colored10_from_fiche(fiche))):
        pl, info = build(c10, real)
        chk = buildcheck.check(pl)
        name = f"{base}_{kind}"
        to_mpd(pl, name, d / f"{name}.mpd", author="Brick Forge (couche par couche)")
        omr.import_set(d / f"{name}.mpd", name, f"https://cdn.rebrickable.com/media/sets/{num}.jpg")
        print(kind, len(pl), info, "volent", len(chk["floating"]), "collisions", len(chk["collisions"]),
              shape_metrics(f["placed"], pl, fiche))


def galerie():
    """Une image par figurine (officiel / couches 3D / couches fiche, face et profil) + la note du cahier."""
    import cv2
    figures = json.loads((OUT / "figures.json").read_text())
    ev = {r["key"]: r for r in json.loads((OUT / "layer_eval.json").read_text())["rows"]}
    real = RealCombos()
    gd = ASSETS / "10-galerie"
    gd.mkdir(exist_ok=True)
    rows, saved = [], {}
    for f in figures:
        fiche = fiche_of(f)
        sets = [f["placed"]] + [build(c10, real)[0] for c10 in (colored10_from_model(f["placed"]), colored10_from_fiche(fiche))]
        saved[fiche["key"]] = {"3d": sets[1], "fiche": sets[2]}
        tiles = []
        for pl in sets:
            v = fiche_of({**f, "placed": pl})["views"]
            tiles += [front_rgb(v["front"]), side_rgb(v["left"])]
        h = max(t.shape[0] for t in tiles)
        tiles = [np.pad(t, ((h - t.shape[0], 0), (0, 0), (0, 0)), constant_values=200) for t in tiles]
        content = np.nonzero((np.hstack(tiles) != 200).any(axis=(1, 2)))[0]
        top = max(0, content.min() - 8) if len(content) else 0
        sep = lambda k: np.full((h - top, k, 3), 255, np.uint8)
        parts = []
        for i, t in enumerate(tiles):
            parts += [t[top:], sep(4 if i % 2 == 0 else 18)]
        name = fiche["key"].replace("#", "_")
        cv2.imwrite(str(gd / f"{name}.png"), np.hstack(parts[:-1]))
        r = ev.get(fiche["key"], {})
        rows.append((f, name, r))
        print(name, flush=True)
    (OUT / "layer_builds.json").write_text(json.dumps(saved))
    lines = ["---", "title: Galerie : les 101 figurines construites couche par couche", "date: 2026-11-26", "status: en cours",
             "summary: Chaque BrickHeadz officielle à côté de ses deux constructions couche par couche (depuis le volume 3D du vrai modèle, et depuis la fiche de 5 vues). Toutes sont montables d'après le moteur de constructibilité.",
             "tags: brickheadz, galerie, construction", "live: galerie-bh", "cover: /research/assets/10-galerie/40377-1_0.png",
             "metrics: 101 figurines ; 101 / 101 montables ; volume 3D 0,77 (cible 3D) et 0,71 (cible fiche)", "---", "",
             "Méthode et chiffres : note **09 · Focus BrickHeadz**, section « Étape 4 ». Ici, uniquement les images.", "",
             "**En 3D** : clique sur une image (ou choisis dans la liste) pour voir les trois modèles côte à côte ; ils tournent ensemble.", "",
             "Dans chaque image, de gauche à droite : **officiel** (face, profil) · **couches, cible 3D** (face, profil) · **couches, cible fiche** (face, profil).", "",
             "Pour chaque figurine : pièces (officiel → cible 3D → cible fiche), puis volume 3D et pixels justes de la face pour la cible 3D.", ""]
    for f, name, r in rows:
        a, b = r.get("3d", {}), r.get("fiche", {})
        lines += [f"### {f['set']}" + (f" ({f['fig'] + 1}/{f['nfigs']})" if f.get("nfigs", 1) > 1 else "") + f" · {f['num']} · {f['year']}", "",
                  f"Pièces : {len(f['placed'])} → {a.get('parts', '?')} → {b.get('parts', '?')} · volume {a.get('iou3d', '?')} · face {round(100 * a.get('front_acc', 0))} %", "",
                  f"![{f['set']}](/research/assets/10-galerie/{name}.png)", ""]
    (ASSETS.parent / "notes" / "10-galerie-couches.md").write_text("\n".join(lines))


if __name__ == "__main__":
    if sys.argv[1:] == ["--galerie"]:
        galerie()
    elif len(sys.argv) == 3:
        build_one(sys.argv[1], sys.argv[2])
    else:
        evaluate(int(sys.argv[1]) if len(sys.argv) == 2 else None)
