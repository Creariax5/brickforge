"""Moteur de constructibilité : un modèle LDraw se monte-t-il vraiment ?

Deux contrôles, dans n'importe quelle orientation (SNOT compris) :
  1. connexions : points d'accroche de chaque pièce (LDCad Shadow Library, data/ldraw/shadow, CC BY-SA 4.0) :
     tenons mâles, creux femelles, clips, barres. Deux pièces sont reliées quand un mâle et une femelle coïncident
     (même position, axes alignés ; ou glissement le long de l'axe pour une barre dans un clip).
     → pièces qui volent = pièces non reliées au socle par une chaîne de connexions ;
  2. collisions : volume plein de chaque pièce (voxels de 1 LDU) ; collision quand une pièce entre de plus de 1 LDU
     dans la matière d'une autre (le contact est permis, et un tenon dans un creux ne touche pas de matière).

    python -m brickforge.buildcheck fichier.mpd          # rapport d'un modèle
    python -m brickforge.buildcheck --brickheadz         # calibrage sur les 101 BrickHeadz officiels
"""

from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from brickforge.ldlib import LDRAW, _find, part_triangles

SHADOW = LDRAW / "shadow"
POS_TOL = 1.6          # LDU : deux points d'accroche « au même endroit »
AXIS_TOL = 0.9         # |cos| minimal entre axes
PEN_LDU = 1.0          # pénétration tolérée
TUBE_RX = re.compile(r"^stud4(a|o|od|oda|s|s2|h|f\d[nsw])?\.dat$")
COLL_MIN = 30          # nb minimal de voxels en pénétration pour signaler une collision (1 voxel = 1 LDU³)


# ---------------------------------------------------------------- points d'accroche (shadow library)

def _shadow(name: str) -> Path | None:
    name = name.replace("\\", "/").lower()
    for d in (SHADOW / "parts", SHADOW / "p", SHADOW / "parts" / "s"):
        p = d / name
        if p.exists():
            return p
    return None


def _params(line: str) -> dict:
    return {k.lower(): v.strip() for k, v in re.findall(r"\[(\w+)=([^\]]*)\]", line)}


def _grid(spec: str):
    """« C 3 1 10 0 » / « C 6 C 6 20 20 » → décalages (dx, dz) dans le plan XZ local du point d'accroche."""
    t = spec.split()
    cx = t[0].upper() == "C"
    if cx:
        t = t[1:]
    nx = int(t[0]); t = t[1:]
    cz = t[0].upper() == "C"
    if cz:
        t = t[1:]
    nz = int(t[0]); sx, sz = float(t[1]), float(t[2])
    xs = [(i - (nx - 1) / 2) * sx if cx else i * sx for i in range(nx)]
    zs = [(k - (nz - 1) / 2) * sz if cz else k * sz for k in range(nz)]
    return [(x, z) for x in xs for z in zs]


def _secs_len(secs: str) -> tuple[float, float]:
    """Longueur totale et rayon du premier tronçon (« R 6 4 » = rond, rayon 6, longueur 4)."""
    t = secs.split()
    L, r0 = 0.0, None
    for i in range(0, len(t) - 2, 3):
        try:
            r, l = float(t[i + 1]), float(t[i + 2])
        except ValueError:
            continue
        L += l
        r0 = r if r0 is None else r0
    return L, (r0 or 0.0)


def _snap_entries(p: dict, kind: str):
    pos = np.array([float(v) for v in p.get("pos", "0 0 0").split()])
    ori = np.array([float(v) for v in p.get("ori", "1 0 0 0 1 0 0 0 1").split()]).reshape(3, 3)
    if kind == "clp":
        L, r = float(p.get("length", 8)), float(p.get("radius", 4))
        gender = "F"
    else:
        L, r = _secs_len(p.get("secs", "R 6 4"))
        gender = p.get("gender", "M").upper()[:1]
    slide = p.get("slide", "false").lower() == "true" or kind == "clp"
    offs = _grid(p["grid"]) if "grid" in p else [(0.0, 0.0)]
    axis = ori[:, 1]
    for dx, dz in offs:
        yield {"pos": pos + ori @ np.array([dx, 0.0, dz]), "axis": axis, "g": gender, "len": L, "r": r,
               "slide": slide, "id": p.get("id", ""), "kind": kind, "center": p.get("center", "false").lower() == "true"}


@lru_cache(maxsize=None)
def local_snaps(name: str, depth: int = 0) -> tuple:
    """Points d'accroche d'une pièce dans son repère, sous-fichiers et inclusions compris."""
    name = name.replace("\\", "/").lower()
    if not name.endswith(".dat"):
        name += ".dat"
    own, clear = [], set()
    sh = _shadow(name)
    if sh is not None:
        for line in sh.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line.startswith("0 !LDCAD"):
                continue
            p = _params(line)
            if "SNAP_CYL" in line:
                own += list(_snap_entries(p, "cyl"))
            elif "SNAP_CLP" in line:
                own += list(_snap_entries(p, "clp"))
            elif "SNAP_CLEAR" in line:
                clear.add(p.get("id", "*"))
            elif "SNAP_INCL" in line and depth < 10 and "ref" in p:
                pos = np.array([float(v) for v in p.get("pos", "0 0 0").split()])
                ori = np.array([float(v) for v in p.get("ori", "1 0 0 0 1 0 0 0 1").split()]).reshape(3, 3)
                offs = _grid(p["grid"]) if "grid" in p else [(0.0, 0.0)]
                for dx, dz in offs:
                    o = pos + ori @ np.array([dx, 0.0, dz])
                    for s in local_snaps(p["ref"], depth + 1):
                        own.append({**s, "pos": ori @ s["pos"] + o, "axis": ori @ s["axis"]})
    kids = []
    path = _find(name)
    if path is not None and depth < 10:
        for line in path.read_text(errors="ignore").splitlines():
            tok = line.split()
            if len(tok) < 15 or tok[0] != "1":
                continue
            m = np.array(list(map(float, tok[5:14]))).reshape(3, 3)
            v = np.array(list(map(float, tok[2:5])))
            sub = " ".join(tok[14:]).replace("\\", "/").lower().split("/")[-1]
            if TUBE_RX.match(sub):
                # tube sous une plaque / brique : un tenon (décalé d'un demi-tenon, plaque « jumper ») s'y loge.
                # LDCad l'a désactivé (stud4.dat) ; on crée la femelle au bout du tube côté dessous (y max du repère courant).
                t = part_triangles(sub).reshape(-1, 3)
                if len(t):
                    w = t @ m.T + v
                    ymax, ymin = w[:, 1].max(), w[:, 1].min()
                    kids.append({"pos": np.array([v[0], ymax, v[2]]), "axis": np.array([0.0, 1.0, 0.0]), "g": "F",
                                 "len": min(4.0, ymax - ymin), "r": 6.0, "slide": False, "id": "tube", "kind": "cyl", "center": False})
                continue
            for s in local_snaps(" ".join(tok[14:]), depth + 1):
                if "*" in clear or (s["id"] and s["id"] in clear):
                    continue
                a = m @ s["axis"]
                kids.append({**s, "pos": m @ s["pos"] + v, "axis": a / (np.linalg.norm(a) or 1)})
    return tuple(own + kids)


@lru_cache(maxsize=None)
def part_snaps(part: str) -> tuple:
    """Points d'accroche d'une pièce ; si la shadow library ne donne aucun creux, on les déduit de la face du dessous :
    une femelle par case de 20 LDU couverte par le dessous de la pièce (plan y max du repère local)."""
    snaps = list(local_snaps(part))
    if any(s["g"] == "F" for s in snaps):
        return tuple(snaps)
    t = part_triangles(part).reshape(-1, 3)
    if not len(t):
        return tuple(snaps)
    ymax = t[:, 1].max()
    bot = t[t[:, 1] > ymax - 0.5]
    if len(bot) < 3:
        return tuple(snaps)
    lo, hi = bot[:, [0, 2]].min(0), bot[:, [0, 2]].max(0)
    nx, nz = max(1, int(round((hi[0] - lo[0]) / 20))), max(1, int(round((hi[1] - lo[1]) / 20)))
    cx, cz = (lo + hi) / 2
    for i in range(nx):
        for k in range(nz):
            x = cx + (i - (nx - 1) / 2) * 20
            z = cz + (k - (nz - 1) / 2) * 20
            snaps.append({"pos": np.array([x, ymax, z]), "axis": np.array([0.0, 1.0, 0.0]), "g": "F", "len": 4.0, "r": 6.0,
                          "slide": False, "id": "auto", "kind": "cyl", "center": False})
    return tuple(snaps)


# ---------------------------------------------------------------- volume plein (collisions)

@lru_cache(maxsize=None)
def solid(part: str):
    """Voxels pleins de la pièce (1 LDU), repère local : (grille booléenne, origine du coin, distance intérieure)."""
    t = part_triangles(part).reshape(-1, 3, 3)
    if not len(t):
        return None
    lo = t.reshape(-1, 3).min(0) - 2
    hi = t.reshape(-1, 3).max(0) + 2
    shape = np.ceil(hi - lo).astype(int) + 1
    g = np.zeros(shape, bool)
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    n = np.clip((area * 4).astype(int) + 3, 3, 20000)
    rep = np.repeat(np.arange(len(t)), n)
    rng = np.random.default_rng(0)
    u, v = rng.random((2, len(rep)))
    f = u + v > 1
    u[f], v[f] = 1 - u[f], 1 - v[f]
    pts = a[rep] + (b[rep] - a[rep]) * u[:, None] + (c[rep] - a[rep]) * v[:, None]
    for q in (pts, a, b, c):                                     # sommets compris (petits triangles)
        ix = np.floor(q - lo).astype(int)
        g[ix[:, 0], ix[:, 1], ix[:, 2]] = True
    g = ndimage.binary_fill_holes(g)
    depth = ndimage.distance_transform_edt(g)                     # profondeur dans la matière (en LDU)
    return g, lo, depth


def _bbox_world(p):
    t = part_triangles(p["part"]).reshape(-1, 3)
    if not len(t):
        return None
    M = np.array(p["m"][3:]).reshape(3, 3)
    w = t @ M.T + np.array(p["m"][:3])
    return w.min(0), w.max(0)


def collisions(placed, boxes, linked=frozenset()):
    """Paires qui s'interpénètrent ; deux pièces reliées par un point d'accroche s'emboîtent par définition (ignorées)."""
    hits = []
    idx = [i for i, b in enumerate(boxes) if b is not None]
    for ai in range(len(idx)):
        i = idx[ai]
        lo_i, hi_i = boxes[i]
        for bj in range(ai + 1, len(idx)):
            j = idx[bj]
            lo_j, hi_j = boxes[j]
            if (min(i, j), max(i, j)) in linked:
                continue
            if ((np.minimum(hi_i, hi_j) - np.maximum(lo_i, lo_j)) <= PEN_LDU).any():
                continue
            n = _penetration(placed[i], placed[j]) + _penetration(placed[j], placed[i])
            if n >= COLL_MIN:
                hits.append((i, j, int(n)))
    return hits


def _penetration(pa, pb):
    """Nombre de voxels pleins de A situés à plus de PEN_LDU à l'intérieur de la matière de B."""
    sa, sb = solid(pa["part"]), solid(pb["part"])
    if sa is None or sb is None:
        return 0
    ga, loa, _ = sa
    gb, lob, db = sb
    va = np.argwhere(ga)[::2] + loa + 0.5                         # un voxel sur deux suffit
    Ma, oa = np.array(pa["m"][3:]).reshape(3, 3), np.array(pa["m"][:3])
    Mb, ob = np.array(pb["m"][3:]).reshape(3, 3), np.array(pb["m"][:3])
    w = va @ Ma.T + oa
    lb = (w - ob) @ np.linalg.inv(Mb).T                           # dans le repère de B
    ix = np.floor(lb - lob).astype(int)
    ok = (ix >= 0).all(1) & (ix < np.array(gb.shape)).all(1)
    ix = ix[ok]
    return int((db[ix[:, 0], ix[:, 1], ix[:, 2]] > PEN_LDU).sum()) * 2


# ---------------------------------------------------------------- connexions

def world_snaps(placed):
    out = []
    for i, p in enumerate(placed):
        M, o = np.array(p["m"][3:]).reshape(3, 3), np.array(p["m"][:3])
        for s in part_snaps(p["part"]):
            a = M @ s["axis"]
            out.append((i, M @ s["pos"] + o, a / (np.linalg.norm(a) or 1), s))
    return out


def _match(pa, xa, sa, pb, xb, sb) -> bool:
    """Un mâle et une femelle (cylindres : de `pos`, sur leur longueur, dans le sens -axe — convention LDCad)
    sont reliés s'ils sont coaxiaux et que leurs segments se recouvrent d'au moins 1 LDU."""
    if sa["g"] == sb["g"] or abs(xa @ xb) < AXIS_TOL:
        return False
    u = -xa
    d = pb - pa
    perp = np.linalg.norm(d - (d @ u) * u)
    slide = sa["slide"] or sb["slide"]
    if perp > (POS_TOL * 1.6 if slide else POS_TOL):
        return False
    a0, a1 = (-sa["len"] / 2, sa["len"] / 2) if sa["center"] else (0.0, sa["len"])
    sgn = 1.0 if (-xb) @ u > 0 else -1.0
    b0 = d @ u
    if sb["center"]:
        b0, b1 = b0 - sb["len"] / 2, b0 + sb["len"] / 2
    else:
        b1 = b0 + sgn * sb["len"]
    if slide and not sa["center"]:                         # barre / clip : le sens importe peu
        a0, a1 = -a1, a1
    lo, hi = max(min(a0, a1), min(b0, b1)), min(max(a0, a1), max(b0, b1))
    return hi - lo >= 1.0 or (min(sa["len"], sb["len"]) < 1 and abs(b0) <= POS_TOL)


def connections(placed):
    ws = world_snaps(placed)
    if not ws:
        return set(), ws
    P = np.array([w[1] for w in ws])
    tree = cKDTree(P)
    edges = set()
    reach = max(w[3]["len"] for w in ws) * 2 + POS_TOL
    for a, b in tree.query_pairs(reach):
        ia, pa, xa, sa = ws[a]
        ib, pb, xb, sb = ws[b]
        if ia != ib and _match(pa, xa, sa, pb, xb, sb):
            edges.add((min(ia, ib), max(ia, ib)))
    return edges, ws


def links_between(ws_a, ws_b, offset=(0.0, 0.0, 0.0)):
    """Liaisons entre deux ensembles de points d'accroche (le second décalé de `offset`) : [(i_a, i_b)]."""
    if not ws_a or not ws_b:
        return []
    off = np.asarray(offset, float)
    A = np.array([w[1] for w in ws_a])
    B = np.array([w[1] for w in ws_b]) + off
    reach = max(w[3]["len"] for w in ws_a + ws_b) * 2 + POS_TOL
    out = []
    for ia, nb in enumerate(cKDTree(B).query_ball_point(A, reach)):
        pa, xa, sa = ws_a[ia][1], ws_a[ia][2], ws_a[ia][3]
        for ib in nb:
            if _match(pa, xa, sa, B[ib], ws_b[ib][2], ws_b[ib][3]):
                out.append((ws_a[ia][0], ws_b[ib][0]))
    return out


def check(placed):
    """Rapport : pièces reliées au socle, pièces qui volent, collisions, pièces sans point d'accroche connu."""
    n = len(placed)
    boxes = [_bbox_world(p) for p in placed]
    edges, ws = connections(placed)
    par = list(range(n))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for a, b in edges:
        par[find(a)] = find(b)
    # socle : la pièce la plus basse (y LDraw max) et la plus large
    cand = [i for i in range(n) if boxes[i] is not None]
    ground = max(cand, key=lambda i: (round(boxes[i][1][1]), (boxes[i][1] - boxes[i][0])[[0, 2]].prod()))
    g = find(ground)
    floating = [i for i in cand if find(i) != g]
    no_snap = sorted({placed[i]["part"] for i in range(n) if not any(w[0] == i for w in ws)})
    coll = collisions(placed, boxes, frozenset(edges))
    return {"parts": n, "connections": len(edges), "ground": ground,
            "floating": floating, "floating_parts": [placed[i]["part"] for i in floating],
            "collisions": coll, "no_snap": no_snap,
            "ok": not floating and not coll}


# ---------------------------------------------------------------- calibrage

def calibrate():
    import json
    from collections import Counter
    from brickforge.brickheadz import OUT, title
    figures = json.loads((OUT / "figures.json").read_text())
    res, fl, co, ns = [], Counter(), Counter(), Counter()
    for f in figures:
        r = check(f["placed"])
        res.append(r)
        for p in r["floating_parts"]:
            fl[p] += 1
        for i, j, k in r["collisions"]:
            co[tuple(sorted((f["placed"][i]["part"], f["placed"][j]["part"])))] += 1
        for p in r["no_snap"]:
            ns[p] += 1
        print(f"{f['num']}#{f['fig']} {f['set'][:28]:28} {r['parts']:3} pièces  {r['connections']:4} liaisons  "
              f"volent {len(r['floating']):2}  collisions {len(r['collisions']):2}", flush=True)
    ok = sum(r["ok"] for r in res)
    nfl = sum(len(r["floating"]) for r in res)
    npt = sum(r["parts"] for r in res)
    print(f"\n{ok}/{len(res)} figurines officielles sans défaut ; pièces qui volent : {nfl}/{npt} ({nfl / npt:.1%}), "
          f"figurines avec collision : {sum(bool(r['collisions']) for r in res)}")
    print("pièces signalées « volent » :", [(p, title(p)[:30], n) for p, n in fl.most_common(15)])
    print("collisions :", [(a, b, n) for (a, b), n in co.most_common(12)])
    print("sans point d'accroche :", [(p, title(p)[:30], n) for p, n in ns.most_common(15)])


if __name__ == "__main__":
    if "--brickheadz" in sys.argv:
        calibrate()
    else:
        from brickforge import omr
        main, files = omr.parse_mpd(Path(sys.argv[1]))
        parts = omr.flatten(main, files)
        r = check([{"part": p["part"], "color": p["color"], "m": p["m"]} for p in parts])
        print({k: v for k, v in r.items()})
