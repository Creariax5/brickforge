"""Étape 5 du focus BrickHeadz : image → maillage 3D (TRELLIS.2) → figurine LEGO montable.

Le maillage texturé produit par un modèle image → 3D pré-entraîné donne la forme et les couleurs ;
il est converti en grille colorée 10 LDU (même format que bh_layer) puis construit couche par couche.

  1. chargement du GLB (Y vers le haut, convention glTF) → repère du gabarit (LDraw : Y vers le bas, face vers -Z) ;
  2. mise à l'échelle : hauteur totale = `plates` plates (27 = médiane des BrickHeadz) ;
  3. échantillonnage dense de la surface, couleur de chaque point (texture) ramenée à la palette des BrickHeadz ;
  4. intérieur rempli, puis brickforge.bh_layer.build (vraies pièces, rien ne vole, combos réels).

    python -m brickforge.from_mesh data/trellis/<nom>/<fichier>.glb [--yaw 0..3] [--plates 27] [--ref 40377-1:0]
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import ndimage

from brickforge.bh_build2 import solid
from brickforge.brickheadz import COLS, OUT
from brickforge.brickheadz_zones import NX, NY, NZ, V

FLIPV = 0      # v des UV = ligne de l image, sans retournement (vérifié sur un GLB Hunyuan3D)


def load(path):
    import trimesh
    m = trimesh.load(path, force="mesh")
    return m


def palette():
    """Couleurs réellement utilisées par les BrickHeadz officielles (code LDraw → RGB, poids)."""
    figs = json.loads((OUT / "figures.json").read_text())
    cnt = Counter(p["color"] for f in figs for p in f["placed"])
    codes = [c for c, n in cnt.most_common() if n >= 5 and c in COLS and not COLS[c][0].lower().startswith("trans")]
    rgb = np.array([[int(COLS[c][1][i:i + 2], 16) for i in (0, 2, 4)] for c in codes], float)
    return codes, rgb


def _lab(rgb):
    from skimage.color import rgb2lab
    return rgb2lab(np.clip(rgb, 0, 255).reshape(-1, 1, 3) / 255.0).reshape(-1, 3)


def to_frame(mesh, yaw=0, plates=27.0):
    """Sommets dans le repère du gabarit (LDU) : bas à y=0, Y LDraw vers le bas, centre XZ sur l'axe."""
    v = np.asarray(mesh.vertices, float).copy()
    th = yaw * np.pi / 2
    c, s = np.cos(th), np.sin(th)
    x, y, z = v[:, 0] * c + v[:, 2] * s, v[:, 1], -v[:, 0] * s + v[:, 2] * c
    lo, hi = np.array([x.min(), y.min(), z.min()]), np.array([x.max(), y.max(), z.max()])
    k = plates * 8.0 / (hi[1] - lo[1])
    # axe vertical = centre de la tête (zone 45-90 % de la hauteur), pas de la boîte englobante :
    # une visière ou un accessoire qui dépasse ne doit pas décaler la figurine
    hgt = (y - lo[1]) / (hi[1] - lo[1])
    head = (hgt > 0.45) & (hgt < 0.9)
    sel = head if head.sum() > 100 else np.ones_like(head)
    cx = (np.percentile(x[sel], 5) + np.percentile(x[sel], 95)) / 2
    cz = (np.percentile(z[sel], 5) + np.percentile(z[sel], 95)) / 2
    X = (x - cx) * k
    Y = -(y - lo[1]) * k
    Z = (z - cz) * k
    return np.stack([X, Y, Z], 1)


def colored10(mesh, yaw=0, plates=27.0, n=600_000, seed=0):
    import trimesh
    verts = to_frame(mesh, yaw, plates)
    vis = mesh.visual
    m2 = trimesh.Trimesh(verts, mesh.faces, process=False)
    pts, fi = trimesh.sample.sample_surface(m2, n, seed=seed)
    tri = m2.triangles[fi]
    bary = trimesh.triangles.points_to_barycentric(tri, pts)
    rgb = None
    if vis.kind == "texture" and getattr(vis, "uv", None) is not None:
        mat = vis.material
        img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
        if img is not None:
            tex = np.asarray(img.convert("RGB"), float)
            uv = (vis.uv[mesh.faces[fi]] * bary[:, :, None]).sum(1) % 1.0
            px = np.clip((uv[:, 0] * tex.shape[1]).astype(int), 0, tex.shape[1] - 1)
            py = np.clip(((FLIPV - uv[:, 1]) * tex.shape[0] * (1 if FLIPV else -1)).astype(int), 0, tex.shape[0] - 1)
            rgb = tex[py, px]
            fac = getattr(mat, "baseColorFactor", None)
            if fac is not None:
                rgb = rgb * (np.asarray(fac[:3], float) / (255.0 if np.max(fac) > 1 else 1.0))
    if rgb is None:
        try:
            vc = vis.vertex_colors[:, :3].astype(float)
        except Exception:
            vc = np.full((len(verts), 3), 200.0)
        rgb = (vc[mesh.faces[fi]] * bary[:, :, None]).sum(1)
    codes, prgb = palette()
    L, PL = _lab(rgb), _lab(prgb)
    near = np.argmin(((L[:, None, :] - PL[None]) ** 2).sum(-1), 1)
    ix = np.floor(pts[:, 0] / V + NX / 2).astype(int)
    iy = np.floor(-pts[:, 1] / V).astype(int)
    iz = np.floor(pts[:, 2] / V + NZ / 2).astype(int)
    ok = (ix >= 0) & (ix < NX) & (iy >= 0) & (iy < NY) & (iz >= 0) & (iz < NZ)
    votes = {}
    for a, b, cc, k in zip(ix[ok], iy[ok], iz[ok], near[ok]):
        votes.setdefault((a, b, cc), Counter())[k] += 1
    surf = np.zeros((NX, NY, NZ), bool)
    col = np.full((NX, NY, NZ), -1, np.int32)
    for (a, b, cc), cn in votes.items():
        surf[a, b, cc] = True
        col[a, b, cc] = codes[cn.most_common(1)[0][0]]
    occ = solid(surf)
    out = np.where(occ, -2, -1).astype(np.int32)
    out[surf] = col[surf]
    return out


def run(glb, yaw=0, plates=27.0, ref=None, out_dir=None):
    from brickforge import buildcheck
    from brickforge.bh_build import RealCombos, fiche_of, to_mpd
    from brickforge.bh_build2 import shape_metrics
    from brickforge.bh_layer import build
    mesh = load(glb)
    figs = json.loads((OUT / "figures.json").read_text())
    f = None
    if ref:
        num, fig = ref.split(":")
        f = next(x for x in figs if x["num"] == num and x["fig"] == int(fig))
    yaws = range(4) if (f is not None and yaw is None) else [yaw or 0]
    real = RealCombos()
    best = None
    for yw in yaws:
        c10 = colored10(mesh, yw, plates)
        pl, info = build(c10, real)
        m = shape_metrics(f["placed"], pl, fiche_of(f)) if f is not None else {}
        key = (m.get("sil_front", 0) + m.get("sil_side", 0), m.get("front_acc", 0))
        if best is None or key > best[0]:
            best = (key, yw, pl, info, m)
    _, yw, pl, info, m = best
    chk = buildcheck.check(pl)
    out_dir = Path(out_dir or Path(glb).parent)
    name = "trellis_" + Path(glb).parent.name.lower().replace("-", "_")[:40]
    to_mpd(pl, name, out_dir / f"{name}.mpd", author="Brick Forge (TRELLIS.2 + couche par couche)")
    res = {"glb": str(glb), "yaw": yw, "plates": plates, "parts": len(pl), **info,
           "floating": len(chk["floating"]), "collisions": len(chk["collisions"]), "metrics_vs_ref": m, "ref": ref}
    (out_dir / "build.json").write_text(json.dumps({**res, "placed": pl}))
    print(json.dumps(res, ensure_ascii=False))
    return pl, res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("--yaw", type=int, default=None)
    ap.add_argument("--plates", type=float, default=27.0)
    ap.add_argument("--ref", default=None, help="num:fig d'une BrickHeadz officielle pour mesurer (et choisir l'orientation)")
    a = ap.parse_args()
    run(a.glb, a.yaw, a.plates, a.ref)
