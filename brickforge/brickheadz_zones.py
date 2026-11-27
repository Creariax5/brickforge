"""Étape 2 du focus BrickHeadz : les zones du gabarit, ce qui y varie, et avec quelles pièces.

Entrée : data/brickheadz/figures.json (étape 1 : figurines recalées, face vers -Z, origine = axe de la tête, dessous du socle).
Sorties : data/brickheadz/zones.json, research/assets/09b-*.png

    python -m brickforge.brickheadz_zones
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from brickforge.brickheadz import ASSETS, COLS, OUT, title
from brickforge.ldlib import part_triangles

V = 10.0                                  # voxel : demi-tenon (LDU) dans les 3 directions → hauteur en 1,25 demi-plate
NX, NY, NZ = 28, 72, 28                   # 14 × 36 × 14 tenons (≈ 90 plates de haut : couvre les plus grands)
PL = 8.0                                  # une plate = 8 LDU

# zones du gabarit (hauteurs en plates depuis le dessous du socle, |x| et |z| en tenons depuis l'axe de la tête)
ZONES = [
    ("socle",  "Socle (plaque 6 × 6 et tuiles)",        lambda x, y, z: y < 2),
    ("jambes", "Jambes / pieds",                         lambda x, y, z: 2 <= y < 5 and abs(x) <= 3.5 and abs(z) <= 3.5),
    ("corps",  "Corps (torse, tenue)",                   lambda x, y, z: 5 <= y < 12 and abs(x) <= 3.0 and abs(z) <= 3.5),
    ("bras",   "Bras et mains",                          lambda x, y, z: 5 <= y < 13 and 3.0 < abs(x) <= 5.0),
    ("face",   "Face (plan avant de la tête)",           lambda x, y, z: 12 <= y < 26 and abs(x) <= 3.5 and z < -2.0),
    ("tete",   "Tête : côtés, arrière, noyau",           lambda x, y, z: 12 <= y < 26 and abs(x) <= 3.5 and -2.0 <= z <= 3.5),
    ("dessus", "Au-dessus de la tête (cheveux, chapeau, oreilles)", lambda x, y, z: y >= 26 and abs(x) <= 4.5 and abs(z) <= 4.5),
    ("hors",   "Hors gabarit (accessoires, oreilles latérales, queue, décors)", lambda x, y, z: True),
]


def tris(p):
    t = part_triangles(p["part"]).reshape(-1, 3).astype(float)
    if not len(t):
        return t
    M = np.array(p["m"][3:]).reshape(3, 3)
    return t @ M.T + np.array(p["m"][:3])


def sample(t, rng):
    t = t.reshape(-1, 3, 3)
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    n = np.clip((area / 3).astype(int), 2, 300)
    rep = np.repeat(np.arange(len(t)), n)
    u, v = rng.random((2, len(rep)))
    f = u + v > 1
    u[f], v[f] = 1 - u[f], 1 - v[f]
    return a[rep] + (b[rep] - a[rep]) * u[:, None] + (c[rep] - a[rep]) * v[:, None]


def to_idx(pts):
    return (np.floor(pts[:, 0] / V + NX / 2).astype(int), np.floor(-pts[:, 1] / V).astype(int), np.floor(pts[:, 2] / V + NZ / 2).astype(int))


def zone_of(x, y, z):
    for k, _, f in ZONES:
        if f(x, y, z):
            return k


def exposed(occ):
    """Voxels visibles de l'extérieur le long d'un des axes (on ne regarde pas par-dessous)."""
    e = np.zeros_like(occ)
    for ax in (0, 2):                     # gauche/droite, avant/arrière
        c = np.cumsum(occ, axis=ax)
        r = np.flip(np.cumsum(np.flip(occ, ax), axis=ax), ax)
        e |= occ & ((c == 1) | (r == 1))
    c = np.flip(np.cumsum(np.flip(occ, 1), axis=1), 1)     # depuis le dessus
    e |= occ & (c == 1)
    return e


def analyse():
    figures = json.loads((OUT / "figures.json").read_text())
    rng = np.random.default_rng(0)
    vocab = defaultdict(Counter)          # zone → pièce → nb de figurines (pièces visibles)
    vocab_n = defaultdict(Counter)        # zone → pièce → nb d'exemplaires
    hidden = Counter()
    hidden_fig = Counter()
    zstats = defaultdict(lambda: defaultdict(list))
    feats = []
    faces = []
    occ_all = []
    for f in figures:
        idg = np.full((NX, NY, NZ), -1, np.int32)
        cen = []
        for i, p in enumerate(f["placed"]):
            t = tris(p)
            if not len(t):
                cen.append(None)
                continue
            pts = sample(t, rng)
            ix, iy, iz = to_idx(pts)
            ok = (ix >= 0) & (ix < NX) & (iy >= 0) & (iy < NY) & (iz >= 0) & (iz < NZ)
            idg[ix[ok], iy[ok], iz[ok]] = i
            c = t.reshape(-1, 3).mean(0)
            cen.append((c[0] / 20, -c[1] / PL, c[2] / 20))
        occ = idg >= 0
        occ_all.append(occ)
        ex = exposed(occ)
        vis = Counter(idg[ex].tolist())
        tot = Counter(idg[occ].tolist())
        per_zone = defaultdict(list)
        seen = defaultdict(set)
        for i, p in enumerate(f["placed"]):
            if cen[i] is None:
                continue
            z = zone_of(*cen[i])
            visible = vis.get(i, 0) >= max(2, 0.08 * tot.get(i, 1))
            per_zone[z].append((p, visible))
            if visible:
                vocab_n[z][p["part"]] += 1
                if p["part"] not in seen[z]:
                    vocab[z][p["part"]] += 1
                    seen[z].add(p["part"])
            else:
                hidden[p["part"]] += 1
                if p["part"] not in seen["_hidden"]:
                    hidden_fig[p["part"]] += 1
                    seen["_hidden"].add(p["part"])
        for k, _, _ in ZONES:
            L = per_zone.get(k, [])
            zstats[k]["parts"].append(len(L))
            zstats[k]["visible"].append(sum(v for _, v in L))
            zstats[k]["colors"].append(len({p["color"] for p, v in L if v}))
        # face : image de la tête vue de face (première matière depuis l'avant), 7 × 14 tenons/plates → grille fine
        y0, y1 = int(12 * PL / V), int(26 * PL / V)
        x0, x1 = NX // 2 - 7, NX // 2 + 7
        face = np.full((y1 - y0, x1 - x0), -1, np.int32)
        for xi in range(x0, x1):
            for yi in range(y0, y1):
                col = idg[xi, yi, :]
                k = np.nonzero(col >= 0)[0]
                if len(k):
                    face[y1 - 1 - yi, xi - x0] = f["placed"][col[k[0]]]["color"]
        vals = face[face >= 0]
        skin = Counter(vals.tolist()).most_common(1)[0][0] if len(vals) else -1
        faces.append((face, skin))
        n_all = len(f["placed"])
        n_vis = sum(v for L in per_zone.values() for _, v in L)
        up = occ[:, int(np.ceil(27.5 * PL / V)):, :]      # au-dessus du dessus plat de la tête (~26 plates)
        feats.append({
            "num": f["num"], "fig": f["fig"], "set": f["set"], "parts": n_all,
            "visible_share": round(n_vis / max(1, n_all), 2),
            "skin": COLS.get(skin, ("?",))[0], "face_colors": len(set(vals.tolist())),
            "above_head": bool(up.any()), "ears_or_horns": bool(up[:NX // 2 - 2].any() and up[NX // 2 + 2:].any() and not up[NX // 2 - 1:NX // 2 + 1].any()),
            "outside": len(per_zone.get("hors", [])),
        })
    return figures, feats, vocab, vocab_n, hidden, hidden_fig, zstats, faces, np.stack(occ_all)


def report(figures, feats, vocab, vocab_n, hidden, hidden_fig, zstats, faces, occ):
    import cv2
    n = len(figures)
    out = {"n": n, "zones": [], "hidden_top": [], "features": feats}
    for k, label, _ in ZONES:
        s = zstats[k]
        out["zones"].append({
            "id": k, "label": label,
            "present": round(float(np.mean(np.array(s["parts"]) > 0)), 2),
            "parts_median": float(np.median(s["parts"])), "visible_median": float(np.median(s["visible"])),
            "colors_median": float(np.median(s["colors"])),
            "vocab_size": len(vocab[k]),
            "vocab": [(p, title(p), vocab[k][p], vocab_n[k][p]) for p, _ in vocab[k].most_common(25)],
        })
    out["hidden_top"] = [(p, title(p), hidden_fig[p], hidden[p]) for p, _ in hidden_fig.most_common(25)]
    out["visible_share_median"] = float(np.median([f["visible_share"] for f in feats]))

    # 1. carte des zones + variabilité de la forme (p(1-p)) en face et en profil
    p = occ.mean(0)                                          # [x, y, z]
    var_front = (p * (1 - p)).max(axis=2).T[::-1] * 4        # 0..1
    var_side = (p * (1 - p)).max(axis=0)[::-1] * 4           # [y, z]
    pres_front = occ.any(axis=3).mean(0).T[::-1]
    zone_cols = {"socle": (90, 90, 90), "jambes": (60, 120, 200), "corps": (70, 170, 90), "bras": (40, 200, 200),
                 "face": (60, 80, 230), "tete": (200, 120, 60), "dessus": (180, 70, 180), "hors": (235, 235, 235)}
    zmap = np.zeros((NY, NX, 3), np.uint8)
    for yi in range(NY):
        for xi in range(NX):
            x, y = (xi - NX / 2 + 0.5) / 2, (yi + 0.5) * V / PL
            z = zone_of(x, y, -3.0) if 12 <= y < 26 and abs(x) <= 3.5 else zone_of(x, y, 0.0)
            zmap[NY - 1 - yi, xi] = zone_cols[z]
    shade = (0.35 + 0.65 * pres_front)[..., None]
    zimg = (zmap * shade).astype(np.uint8)
    hm = lambda a: cv2.applyColorMap((np.clip(a, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_MAGMA)
    big = lambda a: cv2.resize(a, (a.shape[1] * 8, a.shape[0] * 6), interpolation=cv2.INTER_NEAREST)
    crop = slice(NY - int(40 * PL / V), NY)                 # 40 plates de haut
    sep = np.full((big(zimg[crop]).shape[0], 14, 3), 255, np.uint8)
    cv2.imwrite(str(ASSETS / "09b-zones.png"), np.hstack([big(zimg[crop]), sep, big(hm(var_front)[crop]), sep, big(hm(var_side)[crop])]))

    # 2. faces : les têtes de face, triées par couleur de peau, et la carte « où la face diffère de la peau »
    tiles, diff = [], []
    for (face, skin), ft in sorted(zip(faces, feats), key=lambda a: a[1]["skin"]):
        img = np.full(face.shape + (3,), 200, np.uint8)
        for (r, c), v in np.ndenumerate(face):
            if v >= 0:
                hx = COLS.get(int(v), ("", "999999"))[1]
                img[r, c] = [int(hx[i:i + 2], 16) for i in (4, 2, 0)]
        tiles.append(np.pad(cv2.resize(img, (face.shape[1] * 6, face.shape[0] * 6), interpolation=cv2.INTER_NEAREST), ((3, 3), (3, 3), (0, 0)), constant_values=255))
        diff.append(((face >= 0) & (face != skin)).astype(float))
    cols = 17
    rows = [np.hstack(tiles[i:i + cols] + [np.full_like(tiles[0], 255)] * (cols - len(tiles[i:i + cols]))) for i in range(0, len(tiles), cols)]
    cv2.imwrite(str(ASSETS / "09b-faces.png"), np.vstack(rows))
    d = np.mean(diff, axis=0)
    cv2.imwrite(str(ASSETS / "09b-face-variation.png"), cv2.resize(hm(d), (d.shape[1] * 20, d.shape[0] * 20), interpolation=cv2.INTER_NEAREST))
    out["face_diff"] = d.round(2).tolist()
    return out


if __name__ == "__main__":
    r = report(*analyse())
    (OUT / "zones.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print("figurines", r["n"], "· part des pièces visibles (médiane)", r["visible_share_median"])
    for z in r["zones"]:
        print(f"\n== {z['label']}  présente {z['present']:.0%}  pièces {z['parts_median']:.0f} (visibles {z['visible_median']:.0f})  couleurs {z['colors_median']:.0f}  vocabulaire {z['vocab_size']}")
        print("   " + " · ".join(f"{p} {t[:28]} ({u})" for p, t, u, _ in z["vocab"][:10]))
    print("\n== Cachées (structure)")
    print("   " + " · ".join(f"{p} {t[:28]} ({u})" for p, t, u, _ in r["hidden_top"][:14]))
    F = r["features"]
    print("\nau-dessus de la tête", sum(f["above_head"] for f in F), "· oreilles/cornes", sum(f["ears_or_horns"] for f in F),
          "· peau", Counter(f["skin"] for f in F).most_common(8))
