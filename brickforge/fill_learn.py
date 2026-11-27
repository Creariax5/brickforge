"""Réseau qui apprend à remplir une forme (itération d'expert, façon AlphaZero simplifié).

Le remplisseur (brickforge.fill) pose, plate par plate, toutes les pièces possibles qui ne se chevauchent pas :
la seule vraie décision est **l'ordre** dans lequel il les essaie (une pièce posée en bloque d'autres).
L'heuristique trie par « gain » (cases justes − λ × débord). Ici un petit réseau 3D apprend un meilleur ordre :

    0. plafond   : recherche en faisceau très large sur Donald (Hunyuan) → ce qu'on peut espérer avec ces pièces
    1. experts   : faisceau (heuristique) sur les BrickHeadz officielles → meilleures constructions trouvées
    2. imitation : le réseau apprend à classer les pièces choisies par l'expert devant celles qu'elles ont bloquées
    3. boucle    : faisceau guidé par le réseau → constructions meilleures → on réapprend sur les meilleures (k = 1, 2, …)

Entrée du réseau, pour chaque pose candidate : un cube 16 × 8 × 16 cases autour de la pièce
(forme visée, déjà occupé, tenons libres, la pièce elle-même, cases encore à remplir) + l'identité de la pièce + son gain
+ une **vue globale** de toute la forme réduite ×4 (forme visée, déjà construit, plate en cours).
Sorties : une note par pose (on trie par la note) et une **valeur** par état (le volume commun final prédit),
qui choisit la moitié des états gardés dans le faisceau quand elle sait départager deux états (≥ 60 % sur le test). Suivi en direct : data/brickheadz/fill_train/status.json (note 13).

    python -m brickforge.fill_learn            # tout (sur le Mac Studio)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from brickforge import fill as F

RUN = Path(os.environ.get("FL_RUN", F.OUT / "fill_train"))
CX, CY, CZ = 16, 8, 16          # cube vu par le réseau (cases)
OFF = 2                         # la pièce commence à 2 cases du bord du cube
PAD = 18
LAM, RATIO, RELAX, BETA, PASSES = 2.0, 0.5, 0.5, 0.8, 3

# ------------------------------------------------------------------ cibles

def fine_vox(pts, r=2):
    """Case pleine si plus de la moitié de son volume l'est (calcul à résolution ×r)."""
    from scipy import ndimage
    n, ny = F.N * r, F.NY * r
    ix = np.floor(pts[:, 0] / (F.CX / r)).astype(int) + F.C0 * r
    iy = np.floor(-pts[:, 1] / (F.CY / r)).astype(int)
    iz = np.floor(pts[:, 2] / (F.CX / r)).astype(int) + F.C0 * r
    ok = (ix >= 0) & (ix < n) & (iy >= 0) & (iy < ny) & (iz >= 0) & (iz < n)
    g = np.zeros((n, ny, n), bool)
    g[ix[ok], iy[ok], iz[ok]] = True
    g = ndimage.binary_fill_holes(ndimage.binary_closing(g, iterations=1))
    return g.reshape(F.N, r, F.NY, r, F.N, r).sum((1, 3, 5)) > (r ** 3) / 2


def real_vox(placed, seed=0):
    """Forme réelle d'un ensemble de pièces (géométrie LDraw, tenons compris), en cases « à plus de la moitié »."""
    from brickforge.brickheadz_zones import tris
    rng = np.random.default_rng(seed)
    P = []
    for p in placed:
        t = tris(p)
        if not len(t):
            continue
        t = t.reshape(-1, 3, 3)
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
        k = np.clip((area * 2).astype(int), 3, 3000)
        rep = np.repeat(np.arange(len(t)), k)
        u, w = rng.random((2, len(rep)))
        f = u + w > 1
        u[f], w[f] = 1 - u[f], 1 - w[f]
        P.append(a[rep] + (b[rep] - a[rep]) * u[:, None] + (c[rep] - a[rep]) * w[:, None])
    if not P:
        return np.zeros((F.N, F.NY, F.N), bool)
    return fine_vox(np.vstack(P))


def iou(A, B):
    return round(float((A & B).sum() / max(1, (A | B).sum())), 4)


DONALD = "40377-1:0"


def targets():
    """Formes à remplir : la vraie forme des 101 BrickHeadz officielles (pièces LDraw, tenons compris). Mises en cache."""
    RUN.mkdir(parents=True, exist_ok=True)
    cache = RUN / "targets_v3.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        return list(z["names"]), list(z["T"]), list(z["held"])
    names, Ts, held = [], [], []
    figs = json.loads((F.OUT / "figures.json").read_text())
    for n, f in enumerate(figs):
        name = f"{f['num']}:{f['fig']}"
        names.append(name)
        Ts.append(real_vox(f["placed"]))                          # la vraie forme de la LEGO officielle
        held.append(n % 10 == 0 or name == DONALD)                # 1 sur 10 + Donald : jamais vues à l'entraînement
    np.savez_compressed(cache, names=np.array(names), T=np.array(Ts), held=np.array(held))
    return names, Ts, held



# ------------------------------------------------------------------ ce que voit le réseau
#   vue locale  : cube 16 × 8 × 16 cases autour de chaque pose candidate (5 calques)
#   vue globale : toute la forme réduite ×4 (13 × 23 × 13) — forme visée, déjà construit, plate en cours — une fois par état

GX, GY, GZ = 13, 23, 13
NSC = 11


def glob_view(T, blocked, j):
    def ds(a):
        p = np.zeros((GX * 4, GY * 4, GZ * 4), bool)
        p[:a.shape[0], :a.shape[1], :a.shape[2]] = a
        return p.reshape(GX, 4, GY, 4, GZ, 4).any((1, 3, 5))
    L = np.zeros((GX, GY, GZ), bool)
    L[:, min(GY - 1, j // 4), :] = True
    return np.stack([ds(T), ds(blocked), L])


_MT = None


def _mask_templates(lib):
    """La pièce placée à (OFF, OFF, OFF) dans le cube, rognée au cube."""
    global _MT
    if _MT is None:
        _MT = np.zeros((len(lib), CX, CY, CZ), bool)
        for ei, e in enumerate(lib):
            M = e["mask"][:CX - OFF, :CY - OFF, :CZ - OFF]
            _MT[ei, OFF:OFF + M.shape[0], OFF:OFF + M.shape[1], OFF:OFF + M.shape[2]] = M
    return _MT


def features(st, T, j, cands, lib, ps):
    """Cubes (n, 5, CX, CY, CZ) bool + nombres (n, NSC) + identité de pièce (n,) + vue globale (3, GX, GY, GZ)."""
    from numpy.lib.stride_tricks import sliding_window_view as sw
    blocked = st["occ"] | st["res"]
    S2 = st["studs"][j, :F.N, :F.N]                               # tenons libres de la plate j, posés sur la case voisine
    vol = np.zeros((4, F.N + 2 * PAD, F.NY + 2 * PAD, F.N + 2 * PAD), bool)
    sl = (slice(PAD, PAD + F.N), slice(PAD, PAD + F.NY), slice(PAD, PAD + F.N))
    vol[0][sl] = T
    vol[1][sl] = blocked
    vol[2][sl] = S2[:, None, :]
    vol[3][sl] = T & ~blocked
    c = np.array([cc[1:4] for cc in cands], int)                  # ei, i, k
    ei, ii, kk = c[:, 0], c[:, 1], c[:, 2]
    x0, y0, z0 = ii - OFF + PAD, j - OFF + PAD, kk - OFF + PAD
    win = sw(vol, (CX, CY, CZ), axis=(1, 2, 3))                   # vue sans copie
    cube = np.empty((len(c), 5, CX, CY, CZ), bool)
    for ch in range(4):
        cube[:, ch if ch < 3 else 4] = win[ch, x0, y0, z0]
    cube[:, 3] = _mask_templates(lib)[ei]
    g = np.array([cc[0] for cc in cands], np.float32)
    vols = np.array([lib[e]["mask"].sum() for e in ei], np.float32)
    sh = np.array([lib[e]["mask"].shape for e in ei], np.float32)
    keep = np.array([bool(lib[e]["keep"]) for e in ei], np.float32)
    n = len(c)
    sc = np.stack([g / np.maximum(vols, 1), g / 100, vols / 100, np.full(n, j / F.NY), np.full(n, ps / 2),
                   keep, sh[:, 0] / 16, sh[:, 1] / 8, ii / F.N, kk / F.N, np.full(n, j / F.NY)], 1).astype(np.float32)
    return cube, sc, ei.astype(np.int64), glob_view(T, blocked, j)


def make_net(nent):
    import torch
    from torch import nn

    class Net(nn.Module):
        """Note des poses (tête de politique) + pronostic de la silhouette finale d'un état (tête de valeur)."""

        def __init__(s):
            super().__init__()
            s.emb = nn.Embedding(nent, 16)
            s.local = nn.Sequential(nn.Conv3d(5, 24, 3, stride=2, padding=1), nn.ReLU(),
                                    nn.Conv3d(24, 48, 3, stride=2, padding=1), nn.ReLU(),
                                    nn.Conv3d(48, 64, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool3d(1), nn.Flatten())
            s.glob = nn.Sequential(nn.Conv3d(3, 16, 3, padding=1), nn.ReLU(),
                                   nn.Conv3d(16, 32, 3, stride=2, padding=1), nn.ReLU(),       # 7 × 12 × 7
                                   nn.Conv3d(32, 32, 3, stride=2, padding=1), nn.ReLU(),       # 4 × 6 × 4
                                   nn.Flatten(), nn.Linear(32 * 4 * 6 * 4, 64), nn.ReLU())
            s.head = nn.Sequential(nn.Linear(64 + 16 + NSC + 64, 128), nn.ReLU(), nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 1))
            s.vhead = nn.Sequential(nn.Linear(64, 64), nn.ReLU(), nn.Linear(64, 1))

        def forward(s, cube, sc, ei, gv, gi):
            ge = s.glob(gv)[gi]
            return s.head(torch.cat([s.local(cube), s.emb(ei), sc, ge], 1)).squeeze(1)

        def value(s, gv):
            return torch.sigmoid(s.vhead(s.glob(gv)).squeeze(1))
    return Net()


class Policy:
    """Note des candidates : le réseau (CPU, 1 fil) ; sans poids → le gain de l'heuristique."""

    def __init__(self, path=None, nent=0):
        self.net = None
        self.has_value = False
        if path and Path(path).exists():
            import torch
            torch.set_num_threads(1)
            ck = torch.load(path, map_location="cpu")
            self.net = make_net(nent)
            self.net.load_state_dict(ck["net"] if "net" in ck else ck)
            self.net.eval()
            self.has_value = bool(ck.get("value_ok", False)) if "net" in ck else False

    def __call__(self, st, T, j, cands, lib, ps):
        if not cands:
            return np.zeros(0)
        if self.net is None:
            return np.array([c[0] for c in cands], float)
        import torch
        out = []
        with torch.no_grad():
            for a in range(0, len(cands), 2048):
                cube, sc, ei, gv = features(st, T, j, cands[a:a + 2048], lib, ps)
                gi = torch.zeros(len(ei), dtype=torch.long)
                out.append(self.net(torch.from_numpy(cube).float(), torch.from_numpy(sc), torch.from_numpy(ei),
                                    torch.from_numpy(gv[None]).float(), gi).numpy())
        return np.concatenate(out).astype(float)

    def values(self, states, T, j):
        import torch
        gv = np.stack([glob_view(T, s["occ"] | s["res"], j) for s in states])
        with torch.no_grad():
            return self.net.value(torch.from_numpy(gv).float()).numpy().astype(float)


# ------------------------------------------------------------------ un épisode (faisceau guidé par la politique et la valeur)

def _rekey(cands, key):
    return [(float(k),) + tuple(c[1:]) for k, c in zip(key, cands)]


def _noisy(base, rng, heuristic, sigma):
    if not len(base):
        return base
    if heuristic:
        return base * (1 + sigma * rng.standard_normal(len(base)))
    s = base.std() + 1e-6
    return (base - base.mean()) / s + sigma * 1.5 * rng.standard_normal(len(base))


def _select(children, width, values=None):
    """Garde `width` états distincts : moitié par la tête de valeur (si elle existe), le reste par la note faite main."""
    def uniq(order, seen, out, k):
        for n in order:
            if len(out) >= k:
                break
            key = hash(children[n][1]["occ"].tobytes())
            if key not in seen:
                seen.add(key)
                out.append(n)
    seen, keep = set(), []
    if values is not None:
        uniq(list(np.argsort(-values)), seen, keep, (width + 1) // 2)
    uniq(sorted(range(len(children)), key=lambda n: -children[n][0]), seen, keep, width)
    return [children[n][1] for n in keep]


def episode(T, lib, pol, lam=LAM, width=4, branch=3, sigma=0.35, seed=0, passes=PASSES):
    """Faisceau sur la 1re passe (ordre = note ± bruit ; états gardés par la valeur + la note faite main),
    passes de bouchage dans l'ordre de la note, puis pose latérale. Renvoie toutes les constructions finales, la meilleure d'abord."""
    rng = np.random.default_rng(seed)
    bnd = F._bounds(T)
    notT = ~T
    heur = pol.net is None
    root = F._new_state(T)
    root["ps"] = []
    beam = [root]
    for j in range(0, bnd[4], 2):
        children = []
        for st in beam:
            cands = F._candidates(st, j, T, notT, lib, lam, RATIO, bnd, BETA)
            base = pol(st, T, j, cands, lib, 0)
            for b in range(branch):
                c = F._copy(st)
                n0 = len(c["pieces"])
                F._accept(c, _rekey(cands, base if b == 0 else _noisy(base, rng, heur, sigma)), j, lib, 0)
                c["ps"] += [0] * (len(c["pieces"]) - n0)
                children.append((F._partial_score(c, T, j, lam), c))
        vals = pol.values([c for _, c in children], T, j) if pol.has_value and len(children) > width else None
        beam = _select(children, width, vals)
    finals = []
    for st in beam:
        for ps in range(1, passes):
            lam_p = lam * RELAX ** ps
            for j in range(0, bnd[4], 2):
                cands = F._candidates(st, j, T, notT, lib, lam_p, RATIO, bnd, BETA)
                n0 = len(st["pieces"])
                F._accept(st, _rekey(cands, pol(st, T, j, cands, lib, ps)), j, lib, ps)
                st["ps"] += [ps] * (len(st["pieces"]) - n0)
        placed = F.to_placed(st["pieces"], lib)
        placed, occ, nside = F.side_pass(T, st["occ"], placed, lam=lam)
        R = real_vox(placed)                                      # ce qu'on a vraiment construit (tenons compris)
        finals.append({"score": iou(T, R), "sil": F.silhouettes(T, R), "grid": iou(T, occ), "pieces": st["pieces"], "ps": st["ps"],
                       "placed": placed, "n": len(placed), "side": nside, "lam": lam})
    finals.sort(key=lambda f: -f["score"])
    return finals


def replay(T, lib, pieces, ps_list, lam, neg=48, rng=None, passes=PASSES):
    """Rejoue une construction d'expert et en tire les exemples de politique : à chaque plate, les pièces posées (positives)
    et celles qu'elles ont bloquées (négatives, les plus fortes d'abord) ; une vue globale par plate."""
    rng = rng or np.random.default_rng(0)
    bnd = F._bounds(T)
    notT = ~T
    st = F._new_state(T)
    out = {"cube": [], "sc": [], "ei": [], "grp": [], "pos": [], "glob": []}
    g = 0
    for ps in range(passes):
        lam_p = lam * RELAX ** ps
        for j in range(0, bnd[4], 2):
            exp = [p for p, q in zip(pieces, ps_list) if q == ps and p["j"] == j]
            if not exp:
                continue
            cands = F._candidates(st, j, T, notT, lib, lam_p, RATIO, bnd, BETA)
            idx = {(c[1], c[2], c[3]): n for n, c in enumerate(cands)}
            pos = [idx[(p["e"], p["i"], p["k"])] for p in exp if (p["e"], p["i"], p["k"]) in idx]
            if pos and len(cands) > len(pos):
                ps_set = set(pos)
                boxes = [(cands[p][2], cands[p][3], lib[cands[p][1]]["mask"].shape) for p in pos]
                hard, rest = [], []
                for n, c in enumerate(cands):
                    if n in ps_set:
                        continue
                    sh = lib[c[1]]["mask"].shape
                    hit = any(c[2] < bi + bs[0] and bi < c[2] + sh[0] and c[3] < bk + bs[2] and bk < c[3] + sh[2]
                              for bi, bk, bs in boxes)
                    (hard if hit else rest).append(n)
                hard.sort(key=lambda n: -cands[n][0])
                negs = hard[:neg] + list(rng.choice(rest, min(8, len(rest)), replace=False) if rest else [])
                sel = pos + negs
                cube, sc, ei, gv = features(st, T, j, [cands[n] for n in sel], lib, ps)
                out["cube"].append(np.packbits(cube, axis=-1))
                out["sc"].append(sc.astype(np.float16))
                out["ei"].append(ei.astype(np.int16))
                out["grp"].append(np.full(len(sel), g, np.int32))
                out["pos"].append(np.array([1] * len(pos) + [0] * len(negs), bool))
                out["glob"].append(np.packbits(gv, axis=-1)[None])
                g += 1
            rk = [(float(len(exp) - r), p["e"], p["i"], p["k"], p["px"], p["pz"]) for r, p in enumerate(exp)]
            F._accept(st, rk, j, lib, ps)
    if not g:
        return None
    return {k: np.concatenate(v) for k, v in out.items()}


def value_states(T, lib, pieces, ps_list):
    """Vues globales après chaque plate de la 1re passe (ce que la tête de valeur juge dans le faisceau)."""
    bnd = F._bounds(T)
    st = F._new_state(T)
    out = []
    for j in range(0, bnd[4], 2):
        exp = [p for p, q in zip(pieces, ps_list) if q == 0 and p["j"] == j]
        rk = [(float(len(exp) - r), p["e"], p["i"], p["k"], p["px"], p["pz"]) for r, p in enumerate(exp)]
        F._accept(st, rk, j, lib, 0)
        out.append(np.packbits(glob_view(T, st["occ"] | st["res"], j), axis=-1))
    return np.stack(out)


# ------------------------------------------------------------------ tâches parallèles

_W = {}


def _fname(name):
    return name.replace(':', '_')


def _init():
    _W["lib"] = F.library()
    _W["names"], _W["T"], _W["held"] = targets()


def _task(t):
    """t = {kind: ceiling|expert|eval, name, lam, width, branch, seed, iter, policy, record}"""
    t0 = time.time()
    lib = _W["lib"]
    T = _W["T"][_W["names"].index(t["name"])]
    path = t.get("policy")
    key = (path, os.path.getmtime(path)) if path and Path(path).exists() else None
    if "pol" not in _W or _W.get("pkey") != key:
        _W["pol"], _W["pkey"] = Policy(path, len(lib)), key
    finals = episode(T, lib, _W["pol"], lam=t["lam"], width=t["width"], branch=t["branch"], seed=t["seed"])
    best = finals[0]
    res = {**t, "score": best["score"], "sil": best["sil"], "n": best["n"], "side": best["side"], "seconds": round(time.time() - t0, 1),
           "placed": best["placed"], "pieces": best["pieces"], "ps": best["ps"]}
    if t["kind"] == "expert":                                     # exemples pour la tête de valeur : toutes les fins du faisceau
        vd = RUN / "value"
        vd.mkdir(parents=True, exist_ok=True)
        vs = [value_states(T, lib, f["pieces"], f["ps"]) for f in finals]
        np.savez_compressed(vd / f"{_fname(t['name'])}__it{t['iter']}_s{t['seed']}.npz", glob=np.concatenate(vs),
                            y=np.concatenate([np.full(len(v), f["score"], np.float32) for v, f in zip(vs, finals)]))
    if t.get("record"):
        _write_policy(t["name"], T, lib, best["pieces"], best["ps"], t["lam"], t["seed"])
    return res


def _write_policy(name, T, lib, pieces, ps, lam, seed=0):
    d = replay(T, lib, pieces, ps, lam, rng=np.random.default_rng(seed))
    if d is not None:
        f = RUN / "data" / f"{_fname(name)}.npz"
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(f, **d)


def _record(a):
    name, pieces, ps, lam = a
    _write_policy(name, _W["T"][_W["names"].index(name)], _W["lib"], pieces, ps, lam)
    return name


# ------------------------------------------------------------------ apprentissage

def load_data(names):
    parts = []
    for n in names:
        f = RUN / "data" / f"{_fname(n)}.npz"
        if f.exists():
            z = np.load(f)
            if "glob" in z:
                parts.append({k: z[k] for k in ("cube", "sc", "ei", "grp", "pos", "glob")})
    if not parts:
        return None
    off, out = 0, {k: [] for k in parts[0]}
    for p in parts:
        for k in out:
            out[k].append(p[k] + off if k == "grp" else p[k])
        off += len(p["glob"])
    d = {k: np.concatenate(v) for k, v in out.items()}
    pairs = []
    order = np.argsort(d["grp"], kind="stable")
    cuts = np.nonzero(np.diff(d["grp"][order]))[0] + 1
    for blk in np.split(order, cuts):
        p, n = blk[d["pos"][blk]], blk[~d["pos"][blk]]
        if len(p) and len(n):
            pairs.append(np.stack(np.meshgrid(p, n, indexing="ij"), -1).reshape(-1, 2))
    d["pairs"] = np.concatenate(pairs)
    return d


def load_value(names):
    G, Y = [], []
    want = {_fname(n) for n in names}
    for f in sorted((RUN / "value").glob("*.npz")):
        if f.name.split("__")[0] in want:
            z = np.load(f)
            G.append(z["glob"])
            Y.append(z["y"])
    if not G:
        return None
    return {"glob": np.concatenate(G), "y": np.concatenate(Y)}


def train(train_names, held_names, nent, steps, init=None, on_log=None):
    import torch
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    tr, va = load_data(train_names), load_data(held_names)
    vtr, vva = load_value(train_names), load_value(held_names)
    net = make_net(nent).to(dev)
    if init and Path(init).exists():
        ck = torch.load(init, map_location=dev)
        net.load_state_dict(ck["net"] if "net" in ck else ck)
    opt = torch.optim.AdamW(net.parameters(), 2e-3 if not init else 7e-4, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    rng = np.random.default_rng(0)
    unp = lambda a, n: torch.from_numpy(np.unpackbits(a, axis=-1, count=n).astype(np.float32)).to(dev)

    def batch(d, idx):
        ug, gi = np.unique(d["grp"][idx], return_inverse=True)
        return (unp(d["cube"][idx], CZ), torch.from_numpy(d["sc"][idx].astype(np.float32)).to(dev),
                torch.from_numpy(d["ei"][idx].astype(np.int64)).to(dev), unp(d["glob"][ug], GZ), torch.from_numpy(gi).to(dev))

    def acc(d, n=4000):
        if d is None:
            return None
        net.eval()
        pr = d["pairs"][rng.choice(len(d["pairs"]), min(n, len(d["pairs"])), replace=False)]
        with torch.no_grad():
            lp, ln = net(*batch(d, pr[:, 0])), net(*batch(d, pr[:, 1]))
        net.train()
        return round(float((lp > ln).float().mean()), 4)

    def vstats(d, n=4000):
        """Écart moyen entre la silhouette prédite et la vraie ; et si la valeur sait départager deux états (même forme)."""
        if d is None:
            return None, None
        net.eval()
        idx = rng.choice(len(d["y"]), min(n, len(d["y"])), replace=False)
        with torch.no_grad():
            p = net.value(unp(d["glob"][idx], GZ)).cpu().numpy()
        net.train()
        y = d["y"][idx]
        a, b = rng.integers(0, len(idx), (2, 20000))
        m = np.abs(y[a] - y[b]) > 0.01
        rank = float(((p[a] > p[b]) == (y[a] > y[b]))[m].mean()) if m.any() else None
        return round(float(np.abs(p - y).mean()), 4), (round(rank, 4) if rank is not None else None)

    hist = []
    B, BV = 384, 256
    for s in range(steps):
        pr = tr["pairs"][rng.integers(0, len(tr["pairs"]), B)]
        out = net(*batch(tr, np.concatenate([pr[:, 0], pr[:, 1]])))
        loss_p = torch.nn.functional.softplus(out[B:] - out[:B]).mean()
        loss = loss_p
        loss_v = torch.zeros(())
        if vtr is not None:
            vi = rng.integers(0, len(vtr["y"]), BV)
            loss_v = torch.nn.functional.mse_loss(net.value(unp(vtr["glob"][vi], GZ)), torch.from_numpy(vtr["y"][vi]).to(dev))
            loss = loss_p + 20 * loss_v
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
        if s % 100 == 0 or s == steps - 1:
            h = {"step": s, "loss": round(float(loss_p), 4), "vloss": round(float(loss_v), 5)}
            if s % 500 == 0 or s == steps - 1:
                h["acc_train"], h["acc_test"] = acc(tr), acc(va)
                h["v_mae_test"], h["v_rank_test"] = vstats(vva)
            hist.append(h)
            if on_log:
                on_log(h)
    last = hist[-1]
    value_ok = last.get("v_rank_test") is not None and last["v_rank_test"] >= 0.6      # sinon le faisceau garde la note faite main
    info = {"pairs_train": int(len(tr["pairs"])), "pairs_test": int(len(va["pairs"])) if va else 0,
            "value_train": int(len(vtr["y"])) if vtr else 0, "value_ok": value_ok}
    return {"net": net.cpu().state_dict(), "value_ok": value_ok}, hist, info


# ------------------------------------------------------------------ orchestration + état pour la page

class Status:
    def __init__(self):
        self.f = RUN / "status.json"
        self.s = json.loads(self.f.read_text()) if self.f.exists() else {
            "started": time.time(), "stage": "", "iter": 0, "ceiling": [], "targets": {}, "loss": [], "evals": [], "log": []}

    def save(self):
        self.s["updated"] = time.time()
        tmp = self.f.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.s))
        tmp.replace(self.f)

    def log(self, msg):
        print(time.strftime("%H:%M:%S"), msg, flush=True)
        self.s["log"] = (self.s["log"] + [[time.time(), msg]])[-60:]
        self.save()


def _short(r):
    return {k: r[k] for k in ("kind", "name", "lam", "width", "seed", "iter", "score", "sil", "n", "side", "seconds") if k in r}


def _save_model(name, r, tag):
    d = RUN / "models"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{_fname(name)}__{tag}.json").write_text(json.dumps({"name": name, "tag": tag, **_short(r), "placed": r["placed"]}))


def main(iters=4, workers=13):
    import multiprocessing as mp
    RUN.mkdir(parents=True, exist_ok=True)
    S = Status()
    S.s["stage"] = "cibles"
    S.s["version"] = 3
    S.s["metric"] = "volume"
    S.log("préparation des formes à remplir (version 3 : vraie forme des LEGO, volume seul)")
    names, Ts, held = targets()
    lib = F.library()
    trn = [n for n, h in zip(names, held) if not h]
    tst = [n for n, h in zip(names, held) if h]
    don = DONALD
    S.s.update({"train": trn, "test": tst, "donald": don, "nent": len(lib)})
    S.log(f"{len(trn)} formes d'entraînement, {len(tst)} de test (dont {don})")
    best = S.s["targets"]
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers, initializer=_init) as pool:

        def run(tasks, label):
            S.s["stage"] = label
            S.s["progress"] = [0, len(tasks)]
            S.save()
            out = []
            for r in pool.imap_unordered(_task, tasks):
                out.append(r)
                S.s["progress"][0] += 1
                sh = _short(r)
                if r["kind"] == "ceiling":
                    S.s["ceiling"].append(sh)
                    if max(S.s["ceiling"], key=lambda x: x["score"]) is sh:
                        _save_model(r["name"], r, "plafond")
                b = best.get(r["name"])
                if r["kind"] in ("expert", "ceiling") and (b is None or r["score"] > b["score"]):
                    best[r["name"]] = sh
                if r["kind"] == "eval":
                    _save_model(r["name"], r, f"eval{r['iter']}_w{r['width']}")
                S.log(f"{label} · {r['name']} λ={r['lam']} faisceau {r['width']} → volume {r['score']:.3f} "
                      f"({r['n']} pièces, {r['seconds']:.0f} s)")
            return out

        if S.s["iter"] == 0:
            ceil = [] if len(S.s["ceiling"]) >= 8 else [
                {"kind": "ceiling", "name": don, "lam": lam, "width": 24, "branch": 6, "seed": s, "iter": 0} for lam in (2.0, 3.0) for s in range(4)]
            exp = [{"kind": "expert", "name": n, "lam": (2.0, 3.0)[k % 2], "width": 4, "branch": 3, "seed": k, "iter": 0,
                    "record": True} for k, n in enumerate(trn + tst)]
            base = [{"kind": "eval", "name": n, "lam": lam, "width": 1, "branch": 1, "seed": 0, "iter": 0} for n in tst for lam in (2.0, 3.0)]
            res = run(ceil + base + exp, "plafond + experts (heuristique)")
            ev = _best_eval([r for r in res if r["kind"] == "eval"])
            S.s["evals"].append({"iter": 0, "label": "heuristique (glouton, meilleur λ)", "test_mean": round(float(np.mean([r["score"] for r in ev])), 4),
                                 "donald": next((r["score"] for r in ev if r["name"] == don), None),
                                 "per": {r["name"]: r["score"] for r in ev}})
            S.s["iter"] = 1
            S.save()
        pol_path = RUN / "policy.pt"
        for it in range(S.s["iter"], iters + 1):
            import torch
            S.s["stage"] = f"apprentissage {it}"
            S.log(f"itération {it} : apprentissage (politique + valeur) sur les meilleures constructions")
            S.s["loss"].append({"iter": it, "hist": []})

            def on_log(h):
                S.s["loss"][-1]["hist"].append(h)
                S.save()
            ck, hist, info = train(trn, tst, len(lib), 3000 if it == 1 else 1500, init=pol_path if it > 1 else None, on_log=on_log)
            torch.save(ck, pol_path)
            S.s["loss"][-1].update(info)
            S.log(f"itération {it} : réseau enregistré ({info['pairs_train']} paires, {info['value_train']} états pour la valeur) · "
                  f"classement test {hist[-1].get('acc_test')} · valeur {'utilisée' if info['value_ok'] else 'pas encore fiable'} "
                  f"(départage {hist[-1].get('v_rank_test')})")
            ev = [{"kind": "eval", "name": n, "lam": lam, "width": 1, "branch": 1, "seed": 0, "iter": it, "policy": str(pol_path)} for n in tst for lam in (2.0, 3.0)]
            ev += [{"kind": "eval", "name": don, "lam": lam, "width": 6, "branch": 3, "seed": it, "iter": it, "policy": str(pol_path)} for lam in (2.0, 3.0)]
            exp = [{"kind": "expert", "name": n, "lam": (2.0, 3.0)[(k + it) % 2], "width": 4, "branch": 3, "seed": 100 * it + k, "iter": it,
                    "policy": str(pol_path), "record": False} for k, n in enumerate(trn)]
            res = run(ev + exp, f"itération {it} : réseau + faisceau")
            better = [r for r in res if r["kind"] == "expert" and r["score"] >= best.get(r["name"], {}).get("score", -1) - 1e-9]
            if better:
                S.log(f"itération {it} : {len(better)} formes améliorées, extraction des exemples")
                for r in better:
                    best[r["name"]] = _short(r)
                pool.map(_record, [(r["name"], r["pieces"], r["ps"], r["lam"]) for r in better])
            ev1 = _best_eval([r for r in res if r["kind"] == "eval" and r["width"] == 1])
            evd = [r for r in res if r["kind"] == "eval" and r["width"] > 1]
            S.s["evals"].append({"iter": it, "label": f"réseau {it} (glouton)", "test_mean": round(float(np.mean([r["score"] for r in ev1])), 4),
                                 "donald": next((r["score"] for r in ev1 if r["name"] == don), None),
                                 "donald_beam": max((r["score"] for r in evd), default=None),
                                 "donald_beam_sil": max(evd, key=lambda r: r["score"])["sil"] if evd else None,
                                 "per": {r["name"]: r["score"] for r in ev1},
                                 "train_mean": round(float(np.mean([b["score"] for n, b in best.items() if n in trn])), 4)})
            S.s["iter"] = it + 1
            S.save()
    S.s["stage"] = "terminé"
    S.log("terminé")


def _best_eval(rs):
    """Par forme, le meilleur des λ essayés."""
    out = {}
    for r in rs:
        if r["name"] not in out or r["score"] > out[r["name"]]["score"]:
            out[r["name"]] = r
    return list(out.values())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "smoke":                 # essai rapide : une forme, un épisode, un rejeu, un apprentissage
        import torch
        lib = F.library()
        names, Ts, held = targets()
        nm = sys.argv[2] if len(sys.argv) > 2 else names[1]
        T = Ts[names.index(nm)]
        t0 = time.time()
        fins = episode(T, lib, Policy(), width=2, branch=2)
        print("épisode", [f["score"] for f in fins], round(time.time() - t0, 1), "s")
        b = fins[0]
        (RUN / "data").mkdir(parents=True, exist_ok=True)
        (RUN / "value").mkdir(parents=True, exist_ok=True)
        _write_policy(nm, T, lib, b["pieces"], b["ps"], LAM)
        vs = [value_states(T, lib, f["pieces"], f["ps"]) for f in fins]
        np.savez_compressed(RUN / "value" / f"{_fname(nm)}__it0_s0.npz", glob=np.concatenate(vs),
                            y=np.concatenate([np.full(len(v), f["score"], np.float32) for v, f in zip(vs, fins)]))
        ck, hist, info = train([nm], [nm], len(lib), 60)
        print("apprentissage", hist[-1], info)
        torch.save(ck, RUN / "policy.pt")
        pol = Policy(RUN / "policy.pt", len(lib))
        pol.has_value = True
        t0 = time.time()
        fins2 = episode(T, lib, pol, width=2, branch=2)
        print("épisode réseau + valeur", [f["score"] for f in fins2], round(time.time() - t0, 1), "s")
    else:
        main()
