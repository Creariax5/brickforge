"""« Partir du plus proche, puis retoucher » : la BrickHeadz officielle la plus proche de la forme visée, retouchée localement.

1. trouver   : parmi les officielles (sauf celles du même set que la cible), celle dont la vraie forme a le plus grand
               volume commun avec la cible ;
2. enlever   : les pièces qui sont surtout hors de la cible (si ça n'ajoute pas de pièce qui vole) ;
3. ajouter   : l'optimiseur de remplissage, démarré sur la figurine gardée (ses tenons libres servent d'accroche) ;
4. mesurer   : volume commun entre la vraie forme du résultat (pièces LDraw, tenons compris) et la cible.

    python -m brickforge.retrieve_edit            # les 101 officielles, chacune comme cible (résultats : data/brickheadz/retrieve_edit.json)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from brickforge import fill as F
from brickforge import fill_learn as L
from brickforge.buildcheck import check, part_snaps

OUT = F.OUT / "retrieve_edit.json"


def _figs():
    return json.loads((F.OUT / "figures.json").read_text())


def nearest(T, names, Ts, exclude_set=None, k=1, shifts=2):
    """Les k officielles les plus proches (volume commun), hors du set `exclude_set`, chacune avec son meilleur décalage
    (en ½ tenon, sur x et z : déplacer toute la figurine reste constructible)."""
    sc = []
    for n, X in zip(names, Ts):
        if exclude_set and n.split(":")[0] == exclude_set:
            continue
        best = (L.iou(T, X), 0, 0)
        for dx in range(-shifts, shifts + 1):
            for dz in range(-shifts, shifts + 1):
                if dx or dz:
                    v = L.iou(T, np.roll(X, (dx, dz), (0, 2)))
                    if v > best[0]:
                        best = (v, dx, dz)
        sc.append((best[0], n, best[1], best[2]))
    sc.sort(reverse=True)
    return sc[:k]


def shifted(placed, dx, dz):
    return [{**p, "m": [p["m"][0] + dx * F.CX, p["m"][1], p["m"][2] + dz * F.CX] + list(p["m"][3:])} for p in placed]


def piece_cells(placed):
    """Cases de chaque pièce (vraie forme, règle « plus de la moitié »)."""
    return [L.real_vox([p]) for p in placed]


def remove_outside(T, placed, cells, base_float):
    """Enlève les pièces surtout hors de la cible, une à une (les pires d'abord), sans créer de pièce qui vole."""
    keep = list(range(len(placed)))
    order = sorted(keep, key=lambda i: -((cells[i] & ~T).sum() - (cells[i] & T).sum()))
    removed = []
    for i in order:
        out, inn = int((cells[i] & ~T).sum()), int((cells[i] & T).sum())
        if out <= inn:
            break
        trial = [j for j in keep if j != i]
        if len(check([placed[j] for j in trial])["floating"]) > base_float:
            continue
        keep = trial
        removed.append(i)
    return keep, removed


def seed_state(T, placed, occ):
    """État de l'optimiseur démarré sur une figurine existante : cases occupées et tenons libres du dessus."""
    st = F._new_state(T)
    st["occ"] = occ.copy()
    fem = set()
    for p in placed:
        R = np.array(p["m"][3:]).reshape(3, 3)
        o = np.array(p["m"][:3])
        for s in part_snaps(p["part"]):
            if s["g"] == "F" and abs((R @ s["axis"])[1]) > 0.9:
                q = R @ s["pos"] + o
                fem.add((round(q[0]), round(q[1]), round(q[2])))
    for p in placed:
        R = np.array(p["m"][3:]).reshape(3, 3)
        o = np.array(p["m"][:3])
        for s in part_snaps(p["part"]):
            a = R @ s["axis"]
            if s["g"] != "M" or a[1] < 0.9:                       # tenon vers le haut (axe +y ⇒ dépasse vers −y)
                continue
            q = R @ s["pos"] + o
            if (round(q[0]), round(q[1]), round(q[2])) in fem:
                continue
            px, pz, j = q[0] / F.CX + F.C0, q[2] / F.CX + F.C0, -q[1] / F.CY
            if abs(px - round(px)) > 0.15 or abs(pz - round(pz)) > 0.15 or abs(j - round(j)) > 0.15:
                continue
            px, pz, j = int(round(px)), int(round(pz)), int(round(j))
            if 0 <= px <= F.N and 0 <= pz <= F.N and 0 <= j <= F.NY:
                st["studs"][j, px, pz] = True
    st["pieces"] = [{"seed": True}]                               # la figurine existe : toute pièce nouvelle doit s'y accrocher
    return st


def edit(T, base_placed, lam=3.0, ratio=0.5, relax=0.5, passes=3, side=True):
    lib = F.library()
    t0 = time.time()
    cells = piece_cells(base_placed)
    base_float = len(check(base_placed)["floating"])
    keep, removed = remove_outside(T, base_placed, cells, base_float)
    kept = [base_placed[i] for i in keep]
    occ = np.zeros_like(T)
    for i in keep:
        occ |= cells[i]
    st = seed_state(T, kept, occ)
    F.fill(T, lib, lam, ratio, passes=passes, relax=relax, st=st)
    new = F.to_placed([p for p in st["pieces"] if "seed" not in p], lib)
    for p in new:
        p["added"] = True
    out = kept + new
    nside = 0
    if side:
        before = len(out)
        out, _, nside = F.side_pass(T, st["occ"], out, lam=lam)
        for p in out[before:]:
            p["added"] = True
    R = L.real_vox(out)
    chk = check(out)
    return {"placed": out, "removed": [base_placed[i] for i in removed], "score": L.iou(T, R), "sil": F.silhouettes(T, R),
            "n": len(out), "n_removed": len(removed), "n_added": len(new) + nside, "floating": len(chk["floating"]),
            "base_floating": base_float, "collisions": len(chk["collisions"]), "seconds": round(time.time() - t0)}


_G = {}


def _init():
    _G["names"], _G["Ts"], _ = L.targets()
    _G["figs"] = {f"{f['num']}:{f['fig']}": f for f in _figs()}


def _one(name, k=3):
    names, Ts, figs = _G["names"], _G["Ts"], _G["figs"]
    T = Ts[names.index(name)]
    near = nearest(T, names, Ts, exclude_set=name.split(":")[0], k=k)
    best = None
    for s0, nb, dx, dz in near:
        base = shifted(figs[nb]["placed"], dx, dz)
        for lam in (2.0, 3.0):
            r = edit(T, base, lam=lam)
            if best is None or r["score"] > best["score"]:
                best = {**r, "lam": lam, "nearest": nb, "nearest_score": s0, "shift": [dx, dz], "base": base}
    return {"name": name, "candidates": [[n, round(v, 4)] for v, n, _, _ in near], "first_score": near[0][0], "first": near[0][1], **best}


def main(workers=12, sample=False):
    from multiprocessing import Pool
    names, Ts, held = L.targets()
    if sample:                                                    # échantillon : les 12 formes de test (dont Donald)
        names = [n for n, h in zip(names, held) if h]
    t0 = time.time()
    res = []
    with Pool(workers, initializer=_init) as pool:
        for r in pool.imap_unordered(_one, names):
            res.append(r)
            print(f"{len(res):3d}/{len(names)} {r['name']:12s} plus proche {r['first']} {r['first_score']:.3f} · retenue {r['nearest']} {r['nearest_score']:.3f} → retouchée {r['score']:.3f} "
                  f"(−{r['n_removed']} +{r['n_added']} pièces, volent {r['floating']} [avant {r['base_floating']}], collisions {r['collisions']})", flush=True)
            if len(res) % 10 == 0 or len(res) == len(names):
                OUT.write_text(json.dumps({"results": res, "seconds": round(time.time() - t0)}))
    a = np.array([r["first_score"] for r in res])
    b = np.array([r["score"] for r in res])
    print(f"moyenne : plus proche {a.mean():.3f} → retouchée {b.mean():.3f} · ≥ 90 % : {(a >= .9).sum()} → {(b >= .9).sum()} · ≥ 95 % : {(a >= .95).sum()} → {(b >= .95).sum()}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "echantillon":
        OUT = F.OUT / "retrieve_edit_sample.json"
        main(sample=True)
    elif len(sys.argv) > 1:
        _init()
        r = _one(sys.argv[1])
        print({k: v for k, v in r.items() if k not in ("placed", "removed", "base")})
    else:
        main()


def export_viewer(paths=("retrieve_edit_sample.json", "retrieve_edit_part1.json"), out="research/assets/15-compare.json", first="40377-1:0"):
    """Données de la vue 3D de la note 15 : vraie LEGO visée / plus proche (pièces enlevées en fantôme) / retouchée."""
    figs = {f"{f['num']}:{f['fig']}": f for f in _figs()}
    seen, ex = set(), []
    for pth in paths:
        f = F.OUT / pth
        if not f.exists():
            continue
        for r in json.loads(f.read_text())["results"]:
            if r["name"] in seen or "placed" not in r:
                continue
            seen.add(r["name"])
            tgt = figs[r["name"]]
            slim = lambda ps: [{"part": p["part"], "color": p.get("color", 71), "m": p["m"], **({"added": True} if p.get("added") else {})} for p in ps]
            base = slim(r.get("base", [])) if r.get("base") else []
            ghosts = [{"part": p["part"], "color": p.get("color", 71), "m": p["m"], "ghost": True} for p in r.get("removed", [])]
            kept_base = [p for p in base if not any(p["m"] == g["m"] and p["part"] == g["part"] for g in ghosts)]
            ex.append({"name": r["name"], "label": f"{tgt['set']} ({r['name']}) · {r['first_score'] * 100:.1f} % → {r['score'] * 100:.1f} %",
                       "score": r["score"], "panes": [
                           {"title": "Vraie LEGO visée", "sub": f"{tgt['set']} · {len(tgt['placed'])} pièces", "placed": slim(tgt["placed"])},
                           {"title": "Officielle la plus proche", "sub": f"{figs[r['nearest']]['set']} ({r['nearest']}) · en rouge : pièces enlevées",
                            "score": r["nearest_score"], "placed": kept_base + ghosts},
                           {"title": "Retouchée", "sub": f"−{r['n_removed']} / +{r['n_added']} pièces (en orange) · volent {r['floating']} · collisions {r['collisions']}",
                            "score": r["score"], "placed": slim(r["placed"])}]})
    ex.sort(key=lambda e: (e["name"] != first, -e["score"]))
    Path(out).write_text(json.dumps({"examples": ex}))
    return len(ex)
