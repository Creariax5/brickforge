"""Remplissage optimisé d'une forme 3D avec de vraies pièces (sans couleur pour l'instant).

Cible : un volume (maillage image → 3D, ou un modèle officiel) en cases fines : 10 LDU (½ tenon) × 4 LDU (½ plate) × 10 LDU.
Catalogue : toutes les pièces des BrickHeadz officielles + les plaques, briques, tuiles, pentes, pentes courbes et rondes
courantes, chacune dans ses 4 orientations, avec son volume (dessous fermé) et ses accroches verticales
(tenons dessus, creux dessous) lues dans la shadow library de LDCad.

Construction de bas en haut, plate par plate :
  - toutes les positions de toutes les pièces sont notées d'un coup (corrélation par FFT) :
      gain = cases de la cible remplies − λ × cases hors cible ; aucune case déjà prise ;
      au moins un creux de la pièce posé sur un tenon libre de la couche du dessous (rien ne vole) ;
  - on accepte les meilleures sans chevauchement, puis on passe à la plate suivante ;
  - recherche : plusieurs λ et décalages d'un demi-tenon ; on garde le meilleur score de silhouette.
Les blocs non reliés au sol sont retirés ; le moteur de constructibilité vérifie le résultat.

    python -m brickforge.fill <maillage.glb> [--plates 27] [--ref 40377-1:0] [--out dossier]
"""

import argparse
import json
import re
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.signal import fftconvolve

from brickforge.brickheadz import OUT
from brickforge.buildcheck import part_snaps
from brickforge.buildcheck import solid as part_solid
from brickforge.ldlib import part_triangles

CX, CY = 10.0, 4.0                     # case : ½ tenon × ½ plate
N, NY = 52, 90                         # 26 × 26 tenons, 45 plates
C0 = N // 2                            # case/point d'indice C0 ↔ x = 0
EXTRA = """3024 3023 3623 3710 3666 3460 3022 3021 3020 3795 3034 3031 3032 3958 3005 3004 3622 3010 3009 3008 3003 3002 3001
2456 3070b 3069b 63864 2431 6636 3068b 87079 26603 3040 3039 3038 3665 3660 3298 3044 54200 85984 11477 15068 93273 4286
24299 24307 15070 98138 4073 3062b 6143 3941 4032 87087 22885 99780 15573 87580 3794b 2420 2450 3045 4287 60481 3676
6091 32028 4740 14769 1745 24246 35480 33909 92946 37352 22388 35464""".split()
# v2 : pièces des BrickHeadz officielles posables sur tenons, utilisées au moins 5 fois dans les 101 figurines
EXTRA2 = """25269 4032a 92593 4070 99206 26604 50746 50950 11211 88930 14719 24866 30565 11212 15712 61678 30414 27925
36840 59900 49668 60478 26601 4477 41740 60897 85861 2412b 43722 3040b 34103 63325 2357 43723 15571 49673
99207 3700 30357 4733 18674 22385 20482 41769 3937 60849 32474 30367b 2423 3626c 32607 96910 10187 35787
49307 15208 26047 572c 53451 4865b 92280 3176 15470 39739 2429 2430 47458""".split()
ROTS = [np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], float), np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float),
        np.array([[-1, 0, 0], [0, 1, 0], [0, 0, -1]], float), np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], float)]
LIB_CACHE = OUT / "fill_lib_v2.npz"


# ---------------------------------------------------------------- catalogue

def candidate_parts():
    figs = json.loads((OUT / "figures.json").read_text())
    cnt = Counter()
    for f in figs:
        for p, n in f["part_list"]:
            base = re.sub(r"(p[a-z]*\d.*|pat.*)$", "", p) if re.match(r"^\d+[a-z]?p", p) else p
            cnt[base] += n
    # v1 : vocabulaire de construction courant ; v2 : + pièces spéciales des BrickHeadz (arrondis, bec, ailes…)
    return list(dict.fromkeys(EXTRA + EXTRA2))


def entry(part, rot):
    """Volume (cases) et accroches d'une pièce dans une orientation, ou None si elle ne se pose pas sur des tenons."""
    t = part_triangles(part).reshape(-1, 3)
    if not len(t):
        return None
    ymax = t[:, 1].max()
    sn = part_snaps(part)
    R = ROTS[rot]
    fem, studs = [], []
    for s in sn:
        a = R @ s["axis"]
        if abs(a[1]) < 0.9:
            continue
        p = R @ s["pos"]
        if s["g"] == "F" and p[1] >= ymax - 1.0:
            fem.append((p[0], p[2]))
        elif s["g"] == "M" and a[1] > 0.9 and p[1] < ymax - 3:
            studs.append((p[0], ymax - p[1], p[2]))
    if not fem:
        return None
    for (x, z) in fem + [(s[0], s[2]) for s in studs]:
        if abs(x / CX - round(x / CX)) > 0.15 or abs(z / CX - round(z / CX)) > 0.15:
            return None                                         # accroches hors du réseau du ½ tenon
    hts = [round(h / CY) for _, h, _ in studs]
    if any(abs(h * CY - s[1]) > 1.0 or h % 2 for h, s in zip(hts, studs)):
        return None
    sl = part_solid(part)
    if sl is None:
        return None
    g, lo, _ = sl
    pts = np.argwhere(g) + lo + 0.5
    # dessous fermé : chaque colonne est pleine de sa surface jusqu'au plan du dessous (creux, tubes)
    key = np.floor(pts[:, [0, 2]]).astype(int)
    order = np.lexsort((pts[:, 1], key[:, 1], key[:, 0]))
    pts, key = pts[order], key[order]
    _, first = np.unique(key, axis=0, return_index=True)
    fill = []
    for i in first:
        y0 = pts[i, 1]
        ys = np.arange(np.floor(y0) + 0.5, ymax, 1.0)
        fill.append(np.column_stack([np.full(len(ys), pts[i, 0]), ys, np.full(len(ys), pts[i, 2])]))
    pts = np.vstack([pts] + fill) if fill else pts
    w = pts @ R.T
    cx = np.floor(w[:, 0] / CX).astype(int)
    cz = np.floor(w[:, 2] / CX).astype(int)
    cy = np.floor((ymax - w[:, 1]) / CY).astype(int)
    keep = cy >= 0
    cx, cy, cz = cx[keep], cy[keep], cz[keep]
    if not len(cx):
        return None
    ox, oz = cx.min(), cz.min()
    shape = (cx.max() - ox + 1, cy.max() + 1, cz.max() - oz + 1)
    cnt = np.zeros(shape, np.int32)
    np.add.at(cnt, (cx - ox, cy, cz - oz), 1)
    mask = cnt >= 0.5 * CX * CY * CX
    if mask.sum() == 0:
        return None
    ys = np.nonzero(mask.any((0, 2)))[0]
    mask = mask[:, :ys.max() + 1, :]                           # pas de rangée vide au-dessus
    if studs:                                                  # les tenons ne font pas partie du volume
        mask = mask[:, :max(1, max(int(round(h / CY)) for _, h, _ in studs)), :]
    xs = np.nonzero(mask.any((1, 2)))[0]
    zs = np.nonzero(mask.any((0, 1)))[0]
    mask = mask[xs.min():xs.max() + 1, :, zs.min():zs.max() + 1]
    ox, oz = ox + xs.min(), oz + zs.min()
    hcell = int(round(ymax - t[:, 1].min() if False else 0))  # (non utilisé)
    height = mask.shape[1]
    if height % 2:                                             # hauteur arrondie à la plate
        mask = np.concatenate([mask, np.zeros((mask.shape[0], 1, mask.shape[2]), bool)], 1)
    keep = []                                                  # cases devant les tenons latéraux (réservées aux pièces fixées dessus)
    for s in sn:
        a = R @ s["axis"]
        if s["g"] != "M" or abs(a[1]) > 0.1:
            continue
        pos = R @ s["pos"]
        out = -a
        side = np.cross(out, [0.0, 1.0, 0.0])
        for d in np.arange(1.0, 8.0, 2.0):
            for l in np.arange(-9.0, 10.0, 2.0):
                for v in np.arange(-9.0, 10.0, 2.0):
                    q = pos + out * d + side * l + np.array([0.0, v, 0.0])
                    keep.append((int(np.floor(q[0] / CX)) - ox, int(np.floor((ymax - q[1]) / CY)), int(np.floor(q[2] / CX)) - oz))
    if keep:
        kc = Counter(keep)
        keep = sorted({k for k, c in kc.items() if c >= 25})      # case couverte à moitié au moins (100 points sur 4×10×10)
    return {"part": part, "rot": rot, "mask": mask, "ox": int(ox), "oz": int(oz), "ymax": float(ymax), "keep": keep,
            "fem": [(int(round(x / CX)), int(round(z / CX))) for x, z in fem],
            "studs": [(int(round(x / CX)), int(round(h / CY)), int(round(z / CX))) for x, h, z in studs]}


@lru_cache(maxsize=1)
def library(limit=None):
    """Catalogue d'entrées (pièce × orientation), mis en cache sur disque."""
    if LIB_CACHE.exists():
        d = np.load(LIB_CACHE, allow_pickle=True)
        lib = list(d["lib"])
    else:
        lib = []
        for p in candidate_parts():
            seen = set()
            for r in range(4):
                try:
                    e = entry(p, r)
                except Exception:
                    e = None
                if e is None:
                    continue
                sig = (e["mask"].tobytes(), e["mask"].shape, e["ox"], e["oz"], tuple(sorted(e["fem"])))
                if sig in seen:                                 # orientation identique (pièce symétrique)
                    continue
                seen.add(sig)
                lib.append(e)
        np.savez_compressed(LIB_CACHE, lib=np.array(lib, dtype=object))
    lib = [e for e in lib if usable(e)]
    return lib[:limit] if limit else lib


SIDE_STUD_PARTS = {"22885", "87087", "11211", "30414", "4733", "32952", "99780", "99781"}   # tenons latéraux : seulement via snot_swap


def usable(e):
    """Pièces de construction : au plus 3 plates de haut (sauf la brique à tenons sur le côté), pleines (pas de panneau)."""
    M = e["mask"]
    h = M.shape[1]
    if h > 6 and e["part"] not in ("22885",):
        return False
    foot = M.any(1)
    vol = M.sum()
    if vol < 0.55 * foot.sum() * (h - (1 if not M[:, -1, :].any() else 0)):
        return False                                         # trop creux / trop mince pour remplir
    return True


# ---------------------------------------------------------------- cible

def target_from_mesh(mesh, yaw=0, plates=27.0, shift=(0, 0), n=800_000):
    import trimesh
    from brickforge.from_mesh import to_frame
    v = to_frame(mesh, yaw, plates)
    v[:, 0] += shift[0]
    v[:, 2] += shift[1]
    m = trimesh.Trimesh(v, mesh.faces, process=False)
    pts, _ = trimesh.sample.sample_surface(m, n, seed=0)
    return _vox(pts)


def target_from_placed(placed, shift=(0, 0)):
    from brickforge.brickheadz_zones import tris
    pts = []
    rng = np.random.default_rng(0)
    for p in placed:
        t = tris(p)
        if not len(t):
            continue
        t = t.reshape(-1, 3, 3)
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
        k = np.clip((area / 2).astype(int), 2, 400)
        rep = np.repeat(np.arange(len(t)), k)
        u, w = rng.random((2, len(rep)))
        f = u + w > 1
        u[f], w[f] = 1 - u[f], 1 - w[f]
        pts.append(a[rep] + (b[rep] - a[rep]) * u[:, None] + (c[rep] - a[rep]) * w[:, None])
    pts = np.vstack(pts)
    pts[:, 0] += shift[0]
    pts[:, 2] += shift[1]
    return _vox(pts)


def _vox(pts):
    ix = np.floor(pts[:, 0] / CX).astype(int) + C0
    iy = np.floor(-pts[:, 1] / CY).astype(int)
    iz = np.floor(pts[:, 2] / CX).astype(int) + C0
    ok = (ix >= 0) & (ix < N) & (iy >= 0) & (iy < NY) & (iz >= 0) & (iz < N)
    g = np.zeros((N, NY, N), bool)
    g[ix[ok], iy[ok], iz[ok]] = True
    g = ndimage.binary_closing(g, iterations=1)
    return ndimage.binary_fill_holes(g)


# ---------------------------------------------------------------- remplissage

def _corr(a, m):
    """Pour chaque position (i, k) : somme de a[i:i+mx, :, k:k+mz] * m  (a et m ont la même hauteur)."""
    return np.rint(fftconvolve(a.astype(np.float32), m[::-1, ::-1, ::-1].astype(np.float32), mode="valid")[:, 0, :]).astype(np.int32)


def _bounds(T):
    xi = np.nonzero(T.any((1, 2)))[0]
    zi = np.nonzero(T.any((0, 1)))[0]
    top = int(np.nonzero(T.any((0, 2)))[0].max()) + 1 if T.any() else 0
    return (max(0, xi.min() - 6), min(N, xi.max() + 7), max(0, zi.min() - 6), min(N, zi.max() + 7), top)


def _new_state(T):
    return {"occ": np.zeros_like(T), "res": np.zeros_like(T),
            "studs": np.zeros((NY + 1, N + 1, N + 1), bool),     # tenons libres : [niveau (cases), point x, point z]
            "anti": np.zeros((NY + 1, N + 1, N + 1), bool),      # creux libres sous les pièces (accrocher par-dessous)
            "pieces": []}


def _copy(st):
    return {k: (v.copy() if isinstance(v, np.ndarray) else list(v)) for k, v in st.items()}


def _keep_cells(e, i, j, k):
    kc = np.array(e["keep"], int).reshape(-1, 3) + np.array([i, j, k])
    ok = (kc >= 0).all(1) & (kc[:, 0] < N) & (kc[:, 1] < NY) & (kc[:, 2] < N)
    return kc[ok]


def _candidates(st, j, T, notT, lib, lam_p, min_ratio, bnd, beta, Tk=None):
    """Toutes les poses possibles à la plate j (notées) pour l'état st."""
    occ, res, studs, anti = st["occ"], st["res"], st["studs"], st["anti"]
    x0, x1, z0, z1, _ = bnd
    blocked = occ | res
    cands = []
    for ei, e in enumerate(lib):
        M = e["mask"]
        mx, h, mz = M.shape
        if j + h > NY or mx > x1 - x0 or mz > z1 - z0:
            continue
        free = T[x0:x1, j:j + h, z0:z1] & ~occ[x0:x1, j:j + h, z0:z1]
        if free.sum() < 0.5 * M.sum():
            continue
        inside = _corr(free, M)
        outside = _corr(notT[x0:x1, j:j + h, z0:z1], M)
        over = _corr(blocked[x0:x1, j:j + h, z0:z1], M)
        gain = inside - lam_p * outside
        ok = (over == 0) & (gain > 0) & (inside >= min_ratio * M.sum())
        if not e["studs"] and j + h < NY:                        # pièce lisse : seulement là où la forme s'arrête au-dessus
            foot = M.any(1)[:, None, :]
            ok &= _corr(T[x0:x1, j + h:j + h + 1, z0:z1], foot) <= 0.2 * foot.sum()
        if not ok.any():
            continue
        ii, kk = np.nonzero(ok)
        ii, kk = ii + x0, kk + z0
        px, pz = ii - e["ox"], kk - e["oz"]                     # point d'origine de la pièce
        if j > 0 or st["pieces"]:                                # accroche : creux sur un tenon libre, ou tenon dans un creux libre
            conn = np.zeros(len(ii), np.int32)
            for fx, fz in e["fem"]:
                qx, qz = px + fx, pz + fz
                good = (qx >= 0) & (qx <= N) & (qz >= 0) & (qz <= N)
                conn[good] += studs[j, qx[good], qz[good]]
            for sx, sh, sz in e["studs"]:
                if j + sh > NY:
                    continue
                qx, qz = px + sx, pz + sz
                good = (qx >= 0) & (qx <= N) & (qz >= 0) & (qz <= N)
                conn[good] += anti[j + sh, qx[good], qz[good]]
            sel = conn > 0
            ii, kk, px, pz = ii[sel], kk[sel], px[sel], pz[sel]
            if not len(ii):
                continue
        g = gain[ii - x0, kk - z0].astype(float)
        for a in np.argsort(-g)[:200 if e["keep"] else 60]:
            if e["keep"]:
                kc = _keep_cells(e, int(ii[a]), j, int(kk[a]))
                ci = tuple(kc.T)
                if len(kc) and (occ[ci] | res[ci]).any():
                    continue
                g[a] += beta * ((T if Tk is None else Tk)[ci].sum() if len(kc) else 0)
            cands.append((float(g[a]), ei, int(ii[a]), int(kk[a]), int(px[a]), int(pz[a])))
    return cands


def _accept(st, cands, j, lib, ps=0, rng=None, sigma=0.0, on_event=None):
    """Pose gloutonne des candidates (ordre bruité si sigma > 0). Modifie st ; renvoie le nombre de pièces posées."""
    occ, res, studs, anti, pieces = st["occ"], st["res"], st["studs"], st["anti"], st["pieces"]
    if sigma and rng is not None and cands:
        noisy = [(c[0] * (1 + sigma * rng.standard_normal()), c) for c in cands]
        order = [c for _, c in sorted(noisy, key=lambda t: -t[0])]
    else:
        order = sorted(cands, key=lambda c: -c[0])
    inb = lambda x, z: 0 <= x <= N and 0 <= z <= N
    n = 0
    for g, ei, i, k, px, pz in order:
        e = lib[ei]
        M = e["mask"]
        mx, h, mz = M.shape
        sl = (slice(i, i + mx), slice(j, j + h), slice(k, k + mz))
        if ((occ[sl] | res[sl]) & M).any():
            continue
        kc = _keep_cells(e, i, j, k) if e["keep"] else np.zeros((0, 3), int)
        if len(kc) and (occ[tuple(kc.T)] | res[tuple(kc.T)]).any():
            continue
        up = any(inb(px + fx, pz + fz) and studs[j, px + fx, pz + fz] for fx, fz in e["fem"])
        down = any(j + sh <= NY and inb(px + sx, pz + sz) and anti[j + sh, px + sx, pz + sz] for sx, sh, sz in e["studs"])
        if (j > 0 or pieces) and not (up or down):
            continue
        occ[sl] |= M
        if len(kc):
            res[tuple(kc.T)] = True
        for fx, fz in e["fem"]:                                 # creux du dessous : sur un tenon, ou libre
            if inb(px + fx, pz + fz):
                if studs[j, px + fx, pz + fz]:
                    studs[j, px + fx, pz + fz] = False
                elif j > 0:
                    anti[j, px + fx, pz + fz] = True
        for sx, sh, sz in e["studs"]:                           # tenons du dessus : dans un creux, ou libres
            if inb(px + sx, pz + sz) and j + sh <= NY:
                if anti[j + sh, px + sx, pz + sz]:
                    anti[j + sh, px + sx, pz + sz] = False
                else:
                    studs[j + sh, px + sx, pz + sz] = True
        pieces.append({"e": ei, "i": i, "j": j, "k": k, "px": px, "pz": pz})
        n += 1
        if on_event:
            on_event({"t": "place", "piece": pieces[-1], "pass": ps, "level": j, "gain": g})
    return n


def fill(T, lib, lam=1.0, min_ratio=0.6, verbose=False, passes=3, relax=1.0, on_event=None, beta=0.8, st=None, start_pass=0, Tk=None):
    """Remplissage glouton, plate par plate, en plusieurs passes (λ relâché à chaque passe)."""
    st = st or _new_state(T)
    bnd = _bounds(T)
    notT = ~T
    for ps in range(start_pass, passes):
        lam_p = lam * (relax ** ps)
        for j in range(0, bnd[4], 2):
            cands = _candidates(st, j, T, notT, lib, lam_p, min_ratio, bnd, beta, Tk)
            n = _accept(st, cands, j, lib, ps, on_event=on_event)
            if verbose:
                print(f"  passe {ps} plate {j // 2:2d} : {n} pièces", flush=True)
            if on_event:
                on_event({"t": "level", "pass": ps, "level": j, "cands": len(cands), "placed": n,
                          "pieces": len(st["pieces"]), "sil": silhouettes(T, st["occ"])})
    return st["pieces"], st["occ"]


def _partial_score(st, T, j, lam):
    """Note d'un état construit jusqu'à la plate j : cases justes − λ × débord − cases de la forme laissées vides en dessous."""
    occ = st["occ"]
    good = (occ & T).sum()
    bad = (occ & ~T).sum()
    miss = (T[:, :j + 2, :] & ~occ[:, :j + 2, :]).sum()
    return float(good - lam * bad - 1.5 * miss)


def beam_fill(T, lib, lam=2.0, min_ratio=0.5, relax=0.5, beta=0.8, width=6, branch=4, sigma=0.35, passes=3, seed=0, on_event=None):
    """Recherche en faisceau sur la première passe : à chaque plate, chaque état garde `branch` variantes (ordre de pose bruité) ;
    on ne garde que les `width` meilleures. Les passes suivantes (bouchage) sont gloutonnes sur chaque état final."""
    rng = np.random.default_rng(seed)
    bnd = _bounds(T)
    notT = ~T
    beam = [_new_state(T)]
    for j in range(0, bnd[4], 2):
        children = []
        for st in beam:
            cands = _candidates(st, j, T, notT, lib, lam, min_ratio, bnd, beta)
            for b in range(branch):
                c = _copy(st)
                _accept(c, cands, j, lib, 0, rng=rng, sigma=0.0 if b == 0 else sigma)
                children.append((_partial_score(c, T, j, lam), c))
        children.sort(key=lambda t: -t[0])
        seen, beam = set(), []
        for sc, c in children:                                   # pas deux fois le même état
            key = c["occ"].tobytes().__hash__()
            if key in seen:
                continue
            seen.add(key)
            beam.append(c)
            if len(beam) >= width:
                break
        if on_event:
            on_event({"t": "level", "pass": 0, "level": j, "cands": len(children), "placed": 0,
                      "pieces": len(beam[0]["pieces"]), "sil": silhouettes(T, beam[0]["occ"])})
    finals = []
    for st in beam:
        fill(T, lib, lam, min_ratio, passes=passes, relax=relax, beta=beta, st=st, start_pass=1)
        finals.append(st)
    return finals


def to_placed(pieces, lib):
    out = []
    for p in pieces:
        e = lib[p["e"]]
        x = (p["px"] - C0) * CX
        z = (p["pz"] - C0) * CX
        y = -(p["j"] * CY) - e["ymax"]
        R = ROTS[e["rot"]]
        out.append({"part": e["part"], "color": 71, "m": [x, y, z] + R.flatten().tolist()})
    return out


def prune(placed):
    """Ne garde que le bloc relié à la pièce au sol la plus grande (points d'accroche réels)."""
    from brickforge import buildcheck
    if not placed:
        return placed, {}
    chk = buildcheck.check(placed)
    keep = [i for i in range(len(placed)) if i not in set(chk["floating"])]
    return [placed[i] for i in keep], chk


def silhouettes(A, B):
    out = {}
    for name, ax in (("face", 2), ("profil", 0), ("dessus", 1)):
        a, b = A.any(ax), B.any(ax)
        out[name] = round(float((a & b).sum() / max(1, (a | b).sum())), 3)
    out["volume"] = round(float((A & B).sum() / max(1, (A | B).sum())), 3)
    return out


def occ_of(placed, lib_index):
    """Grille d'occupation reconstruite depuis les pièces gardées."""
    occ = np.zeros((N, NY, N), bool)
    for p in placed:
        e, i, j, k = lib_index[id(p)]
        M = e["mask"]
        occ[i:i + M.shape[0], j:j + M.shape[1], k:k + M.shape[2]] |= M
    return occ


def _job(args):
    T, lam, r = args
    t0 = time.time()
    placed, occ, info = solve(T, lam, r, relax=0.5, snot=True)
    s = silhouettes(T, occ)
    score = (s["face"] + s["profil"] + s["dessus"]) / 3 + 0.5 * s["volume"]
    return score, lam, r, placed, occ, s, time.time() - t0


def search_all(targets, lams=(1.0, 2.0, 3.0, 4.0), ratios=(0.5, 0.65), workers=None):
    """Toutes les combinaisons (décalage × λ × ratio) en parallèle ; retourne la meilleure."""
    import os
    from multiprocessing import get_context
    jobs, keys = [], []
    for sh, T in targets.items():
        for lam in lams:
            for r in ratios:
                jobs.append((T, lam, r))
                keys.append(sh)
    library()
    with get_context("fork").Pool(workers or max(1, min(len(jobs), (os.cpu_count() or 2) - 2))) as pool:
        res = pool.map(_job, jobs)
    best = None
    for sh, rr in zip(keys, res):
        score, lam, r, placed, occ, s, dt = rr
        print(f"λ={lam} ratio={r}: {len(placed)} pièces, {s}, {dt:.0f}s", flush=True)
        if best is None or score > best[0]:
            best = (score, lam, r, placed, occ, s, sh, targets[sh])
    return best


def run(src, plates=27.0, ref=None, out=None, yaw=None):
    from brickforge import buildcheck
    from brickforge.bh_build import to_mpd
    lib = library()
    print(f"catalogue : {len(lib)} entrées (pièce × orientation), {len({e['part'] for e in lib})} pièces", flush=True)
    if src.endswith(".glb"):
        from brickforge.from_mesh import load
        mesh = load(src)
        bj = Path(src).parent / "build.json"
        yw = yaw if yaw is not None else (json.loads(bj.read_text()).get("yaw", 0) if bj.exists() else 0)
        targets = {(0, 0): target_from_mesh(mesh, yw, plates)}
    else:
        figs = json.loads((OUT / "figures.json").read_text())
        num, fig = src.split(":")
        f = next(x for x in figs if x["num"] == num and x["fig"] == int(fig))
        targets = {(0, 0): target_from_placed(f["placed"])}
        yw = 0
    score, lam, r, placed, occ2, s2, sh, T = search_all(targets)
    chk2 = buildcheck.check(placed) if placed else {"floating": [], "collisions": []}
    res = {"src": src, "plates": plates, "yaw": yw, "shift": sh, "lambda": lam, "ratio": r, "parts": len(placed),
           "silhouettes": s2, "floating": len(chk2["floating"]),
           "collisions": len(chk2["collisions"]), "part_counts": Counter(p["part"] for p in placed).most_common()}
    if ref:
        figs = json.loads((OUT / "figures.json").read_text())
        num, fig = ref.split(":")
        f = next(x for x in figs if x["num"] == num and x["fig"] == int(fig))
        R = target_from_placed(f["placed"])
        res["vs_ref"] = silhouettes(R, occ2)
    out = Path(out or (Path(src).parent if src.endswith(".glb") else OUT / "fill" / src.replace(":", "_")))
    out.mkdir(parents=True, exist_ok=True)
    to_mpd(placed, "fill", out / "fill.mpd", author="Brick Forge (remplissage optimisé)")
    (out / "fill.json").write_text(json.dumps({**res, "placed": placed}, default=int))
    print(json.dumps(res, ensure_ascii=False, default=int))
    return res


# ---------------------------------------------------------------- accroches latérales (SNOT)

SNOT_SWAP = {"3005": "87087", "3004": "11211", "3010": "30414"}
SIDE_PARTS = ["3024", "3023", "3623", "3710", "3070b", "3069b", "63864", "2431", "3022", "3068b", "3021", "3020", "87079",
              "98138", "4073", "3794b", "15573", "54200", "85984", "11477", "3666", "6636"]


def _rotations():
    import itertools
    out = []
    for perm in itertools.permutations(range(3)):
        for sg in itertools.product((1, -1), repeat=3):
            R = np.zeros((3, 3))
            for r, (c, s) in enumerate(zip(perm, sg)):
                R[r, c] = s
            if np.linalg.det(R) > 0.5:
                out.append(R)
    return out


ROT24 = _rotations()


@lru_cache(maxsize=None)
def _side_part(part):
    """Points du volume (pas de 2 LDU, dessous fermé) et creux du dessous, repère local."""
    from brickforge.ldlib import part_triangles
    sl = part_solid(part)
    t = part_triangles(part).reshape(-1, 3)
    if sl is None or not len(t):
        return None
    g, lo, _ = sl
    ymax = t[:, 1].max()
    g = g.copy()
    for a in range(g.shape[0]):                                  # dessous fermé (colonnes pleines jusqu'au plan du dessous)
        for c in range(g.shape[2]):
            ys = np.nonzero(g[a, :, c])[0]
            if len(ys):
                g[a, ys.min():int(np.ceil(ymax - lo[1])), c] = True
    pts = (np.argwhere(g[::2, ::2, ::2]) * 2 + lo + 1.0)
    pts = pts[pts[:, 1] <= ymax]
    fem = [s["pos"] for s in part_snaps(part) if s["g"] == "F" and abs(s["axis"][1]) > 0.9 and s["pos"][1] >= ymax - 1]
    studs = [(s["pos"], s["axis"]) for s in part_snaps(part) if s["g"] == "M" and abs(s["axis"][1]) > 0.9 and s["pos"][1] < ymax - 3]
    return pts, fem, studs


def _cells(wpts):
    """Points monde (pas de 2 LDU) → cases pleines (≥ 50 % de la case)."""
    ix = np.floor(wpts[:, 0] / CX).astype(int) + C0
    iy = np.floor(-wpts[:, 1] / CY).astype(int)
    iz = np.floor(wpts[:, 2] / CX).astype(int) + C0
    ok = (ix >= 0) & (ix < N) & (iy >= 0) & (iy < NY) & (iz >= 0) & (iz < N)
    key, cnt = np.unique(np.stack([ix[ok], iy[ok], iz[ok]], 1), axis=0, return_counts=True)
    full = key[cnt * 8 >= 0.5 * CX * CY * CX]
    return full


def _side_studs(placed):
    """Tenons non verticaux de chaque pièce posée : (position monde, axe monde)."""
    out = []
    for p in placed:
        R = np.array(p["m"][3:]).reshape(3, 3)
        o = np.array(p["m"][:3])
        for s in part_snaps(p["part"]):
            if s["g"] == "M":
                a = R @ s["axis"]
                if abs(a[1]) < 0.1:
                    out.append((R @ s["pos"] + o, a))
    return out


def _female_world(placed):
    pts = []
    for p in placed:
        R = np.array(p["m"][3:]).reshape(3, 3)
        o = np.array(p["m"][:3])
        for s in part_snaps(p["part"]):
            if s["g"] == "F":
                pts.append(R @ s["pos"] + o)
    return np.array(pts) if pts else np.zeros((0, 3))


def snot_swap(T, occ, placed, min_cells=2):
    """Briques de surface → version à tenons latéraux tournée vers l'extérieur, là où la forme continue."""
    out, n = [], 0
    for p in placed:
        new = SNOT_SWAP.get(p["part"])
        if not new:
            out.append(p)
            continue
        R = np.array(p["m"][3:]).reshape(3, 3)
        o = np.array(p["m"][:3])
        best = None
        for flip in (np.eye(3), np.diag([-1.0, 1.0, -1.0])):     # même encombrement : orientation d'origine ou demi-tour
            R2 = R @ flip
            studs = [(R2 @ s["pos"] + o, R2 @ s["axis"]) for s in part_snaps(new) if s["g"] == "M" and abs(s["axis"][1]) < 0.1]
            score = 0
            for pos, a in studs:
                out_dir = -a
                c = pos + out_dir * 12                           # une demi-case devant la face
                ix, iy, iz = int(np.floor(c[0] / CX)) + C0, int(np.floor(-c[1] / CY)), int(np.floor(c[2] / CX)) + C0
                for dy in (-2, -1, 0, 1):
                    jj = iy + dy
                    if 0 <= ix < N and 0 <= jj < NY and 0 <= iz < N and T[ix, jj, iz] and not occ[ix, jj, iz]:
                        score += 1
            if best is None or score > best[0]:
                best = (score, R2)
        if best[0] >= min_cells:
            out.append({**p, "part": new, "m": list(o) + best[1].flatten().tolist()})
            n += 1
        else:
            out.append(p)
    return out, n


def side_pass(T, occ, placed, lam=2.0, min_ratio=0.5, rounds=2, on_event=None):
    """Pose des plaques, tuiles et pentes sur les tenons latéraux libres (tournées de 90°)."""
    occ = occ.copy()
    placed = list(placed)
    added = 0
    for rd in range(rounds):
        studs = _side_studs(placed)
        fw = _female_world(placed)
        free = [(pos, a) for pos, a in studs if not len(fw) or np.min(np.linalg.norm(fw - pos, axis=1)) > 1.6]
        cands = []
        for pos, a in free:
            Rs = [R for R in ROT24 if np.allclose(R @ np.array([0.0, 1.0, 0.0]), a, atol=1e-6)]
            for part in SIDE_PARTS:
                sp = _side_part(part)
                if sp is None:
                    continue
                pts, fem, _ = sp
                for R in Rs:
                    for f in fem:
                        t = pos - R @ f
                        cells = _cells(pts @ R.T + t)
                        if not len(cells):
                            continue
                        ci = tuple(cells.T)
                        if occ[ci].any():
                            continue
                        inside = int(T[ci].sum())
                        outside = len(cells) - inside
                        g = inside - lam * outside
                        if g <= 0 or inside < min_ratio * len(cells):
                            continue
                        cands.append((g, part, R, t, cells))
        cands.sort(key=lambda c: -c[0])
        n = 0
        for g, part, R, t, cells in cands:
            ci = tuple(cells.T)
            if occ[ci].any():
                continue
            occ[ci] = True
            p = {"part": part, "color": 71, "m": list(t) + R.flatten().tolist()}
            placed.append(p)
            n += 1
            if on_event:
                on_event({"t": "place_raw", "part": part, "m": p["m"], "pass": 10 + rd, "level": int(cells[:, 1].min()), "gain": float(g)})
        added += n
        if not n:
            break
    return placed, occ, added


def shrink(T):
    """Forme rétrécie d'un demi-tenon sur les côtés (place laissée aux pièces fixées latéralement)."""
    st = np.zeros((3, 1, 3), bool)
    st[1, 0, :] = st[:, 0, 1] = True
    return T & ndimage.binary_erosion(T, structure=st, border_value=0)


def min_sil(T, occ):
    s = silhouettes(T, occ)
    return min(s["face"], s["profil"], s["dessus"]) + 0.01 * s["volume"]


def solve(T, lam=2.0, ratio=0.6, relax=0.5, snot=True, on_event=None, beta=0.8, beam=0, seed=0):
    """Remplissage complet : vertical (glouton, ou en faisceau si beam > 0) → pose latérale. Critère : la pire des 3 silhouettes."""
    lib = library()
    if beam:
        states = beam_fill(T, lib, lam, ratio, relax, beta, width=beam, seed=seed)
    else:
        st = _new_state(T)
        fill(T, lib, lam, ratio, relax=relax, on_event=on_event, beta=beta, st=st)
        states = [st]
    best = None
    for st in states:
        placed = to_placed(st["pieces"], lib)
        occ = st["occ"]
        info = {"vertical": len(placed), "swaps": 0, "side": 0}
        if snot:
            placed, occ, info["side"] = side_pass(T, occ, placed, lam=lam, on_event=None if beam else on_event)
        sc = min_sil(T, occ)
        if best is None or sc > best[0]:
            best = (sc, placed, occ, info)
    _, placed, occ, info = best
    if beam and on_event:                                        # faisceau : on rejoue le meilleur résultat pièce par pièce
        for p in placed:
            on_event({"t": "place_raw", "part": p["part"], "m": p["m"], "pass": 0, "level": int(-p["m"][1] // CY), "gain": 0.0})
    return placed, occ, info



def shrink_side(T, s=1, thick=4):
    """Forme rétrécie de s cases sur les 4 côtés (x et z), pas en hauteur : la place des faces en plaques posées de côté.
    Seulement là où la forme est épaisse (au moins `thick` cases, 2 tenons) : les parties fines (jambes, cou) restent entières,
    sinon le haut n'a plus d'appui."""
    if not s:
        return T.copy()
    st = np.zeros((3, 1, 3), bool)
    st[1, 0, :] = st[:, 0, 1] = True
    er = ndimage.binary_erosion(T, structure=st, iterations=s, border_value=0)
    r = thick // 2
    wide = ndimage.binary_dilation(ndimage.binary_erosion(T, structure=st, iterations=r, border_value=0), structure=st, iterations=r) & T
    return er | (T & ~ndimage.binary_dilation(wide, structure=st, iterations=1))


def solve_shell(T, lam=2.0, ratio=0.5, relax=0.5, s=1, rounds=5, beta=3.0, on_event=None):
    """Méthode « cœur + faces » (comme les vraies BrickHeadz) :
    1. cœur monté plate par plate dans la forme rétrécie de s cases sur les côtés ;
    2. briques de surface → version à tenons latéraux tournés vers l'extérieur ;
    3. faces : plaques, tuiles et pentes empilées sur ces tenons, sur plusieurs couches (résolution d'une plaque, 8 LDU)."""
    lib = library()
    Tc = shrink_side(T, s) if s else T
    st = _new_state(Tc)
    fill(Tc, lib, lam, ratio, relax=relax, beta=beta, st=st, on_event=on_event, Tk=T)
    placed = to_placed(st["pieces"], lib)
    occ = st["occ"].copy()
    placed, nsw = snot_swap(T, occ, placed, min_cells=2) if s else (placed, 0)
    placed, occ, nside = side_pass(T, occ, placed, lam=lam, rounds=rounds, on_event=on_event)
    return placed, occ, {"core": len(st["pieces"]), "swaps": nsw, "side": nside}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="maillage .glb, ou num:fig d'une BrickHeadz officielle")
    ap.add_argument("--plates", type=float, default=27.0)
    ap.add_argument("--ref", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--yaw", type=int, default=None)
    a = ap.parse_args()
    run(a.src, a.plates, a.ref, a.out, a.yaw)


def clean_target(T, sym=True):
    """Cible « propre » : arrondie au tenon (2 × 2 cases) et à la plate (2 cases), symétrique gauche/droite, sans bosses isolées."""
    nx, ny, nz = T.shape
    off = C0 % 2                                                 # les tenons commencent sur une case paire autour de l'axe
    B = np.zeros_like(T)
    for i in range(off, nx - 1, 2):
        for k in range(off, nz - 1, 2):
            col = T[i:i + 2, :, k:k + 2]
            for j in range(0, ny - 1, 2):
                if col[:, j:j + 2, :].sum() >= 4:                # au moins la moitié du bloc tenon × plate
                    B[i:i + 2, j:j + 2, k:k + 2] = True
    if sym:
        M = B[::-1, :, :]                                        # miroir autour de x = 0 (axe de la tête, case C0)
        shift = 2 * C0 - nx
        M2 = np.zeros_like(B)
        if shift >= 0:
            M2[shift:] = M[:nx - shift]
        else:
            M2[:nx + shift] = M[-shift:]
        B = B | M2
    st = np.ones((1, 3, 1), bool)                                # pas de fine lamelle verticale isolée
    B = ndimage.binary_opening(B, structure=np.ones((2, 1, 2), bool)) | (B & ndimage.binary_erosion(B, st))
    return ndimage.binary_fill_holes(B)
