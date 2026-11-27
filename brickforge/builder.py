"""Constructeur pièce par pièce : pose des pièces LDraw en les emboîtant sur des tenons libres,
comme un humain, jusqu'à remplir la forme cible.

À chaque étape, pour chaque pièce du catalogue et chacune de ses orientations, on évalue d'un coup
toutes les positions de la grille (corrélations) :
- gain   : Σ remplissage × récompense de la cible (positive dedans, négative dehors) − coût par pièce ;
- valide : aucune case déjà prise ET au moins une cavité de la pièce posée sur un tenon libre.
On pose le meilleur geste, on met à jour les tenons libres (ceux recouverts disparaissent, ceux de la
nouvelle pièce apparaissent), et on recommence. L'ordre des gestes est l'ordre de montage.

Le premier étage s'appuie sur une plaque de base virtuelle (le sol) ; les couleurs sont choisies après
coup, en lisant les photos là où chaque pièce est visible.

Usage : python -m brickforge.builder lego_tortue [--out lego_tortue_auto]
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from scipy.signal import correlate

from . import colors
from . import compare as C
from .connect import orientations
from .target import Target, carve

ROOT = Path(__file__).resolve().parent.parent

# Catalogue du constructeur (pièces dont les motifs sont fiables). Les pentes viennent en fin de montée.
PARTS = [
    # briques
    "3001", "3002", "3003", "3004", "3010", "3009", "3622", "3005",
    # plaques
    "3020", "3021", "3022", "3023", "3024", "3623", "3710", "3666", "3460", "3795", "3034", "3031", "3032",
    # tuiles (finition)
    "3068b", "3069b", "3070b", "63864", "2431", "87079", "26603",
    # pentes et pentes courbes
    "54200", "85984", "3040b", "3039", "4286", "3298", "11477", "15068", "50950", "61678", "93606",
    # arrondis
    "79491", "30357", "25269", "27925", "6141", "4032",
]
CORE_ONLY = {"3001", "3002", "3003", "3004", "3010", "3009", "3622", "3005"}   # briques : intérieur seulement
OUTSIDE = 1.5       # pénalité supplémentaire par case remplie hors de la cible
PIECE_COST = 0.35   # coût fixe d'une pièce (favorise les grandes pièces)
STUD_SHOWN = 0.6    # pénalité par tenon qui resterait visible en surface (les sets finissent en tuiles)


def corr(a, k):
    """Corrélation « valide » : r[t] = Σ_c a[t + c] · k[c], pour toutes les translations où k tient dans a."""
    return correlate(a, k, mode="valid", method="auto")


class Builder:
    def __init__(self, target: Target, parts=PARTS, log=print):
        self.t = target
        self.log = log
        self.I, self.J, self.K = target.frac.shape
        f = target.frac
        # Gain d'une pièce = baisse de l'écart quadratique entre remplissage et cible, case par case :
        # Σ occ·(2f − occ) − pénalité hors cible. Une pente (occ ~ 0,5) épouse mieux une case à moitié
        # dans la cible qu'une brique pleine.
        self.two_f = (2 * f).astype(np.float32)
        self.outside = (f < 0.05).astype(np.float32) * OUTSIDE
        # un tenon dont la base est au bas de la couche k est visible si cette case est (quasi) hors cible
        self.shown = (f < 0.3).astype(np.float32)
        # cœur / peau : les briques hautes (3 plaques) ne vont qu'à l'intérieur ; la bordure est
        # réservée aux plaques, pentes et tuiles, comme dans les sets
        self.skin = (f < 0.85).astype(np.float32)
        self.occupied = np.zeros(f.shape, bool)
        self.studs = np.zeros(f.shape, bool)          # tenon libre dont la base est au bas de la couche k
        self.studs[:, :, 0] = f[:, :, 0] > 0           # le sol : plaque de base virtuelle sous l'emprise
        self.kernels = [k for p in parts for k in orientations(p)]
        self.placed = []
        log(f"{len(self.kernels)} motifs (pièces × orientations), grille {f.shape}")

    def best_move(self):
        best = None
        occ_f = self.occupied.astype(np.float32)
        st_f = self.studs.astype(np.float32)
        for kn in self.kernels:
            X, Z, Kk = kn.shape
            if X > self.I or Z > self.J or Kk > self.K:
                continue
            occ = kn.occ.astype(np.float32)
            gain = corr(self.two_f, occ) - corr(self.outside, occ) - float((occ ** 2).sum()) - PIECE_COST
            if kn.part in CORE_ONLY:
                gain = np.where(corr(self.skin, kn.solid.astype(np.float32)) > 0.5, -np.inf, gain)
            if kn.male:
                mk = np.zeros((X, Z, Kk + 1), np.float32)
                for (a_, b_, c_) in kn.male:
                    if c_ <= Kk:
                        mk[a_, b_, c_] = 1
                shown = np.pad(self.shown, ((0, 0), (0, 0), (0, 1)), constant_values=1)
                gain = gain - STUD_SHOWN * corr(shown, mk)[:, :, :gain.shape[2]]
            if gain.max() <= 0:
                continue
            coll = corr(occ_f, kn.solid.astype(np.float32)) > 0.5
            fem = np.zeros((X, Z, 1), np.float32)
            fem[:, :, 0] = kn.female
            sup = corr(st_f[:, :, :self.K - Kk + 1], fem) > 0.5          # cavités sur au moins un tenon libre
            ok = sup & ~coll[:, :, :sup.shape[2]]
            g = np.where(ok, gain[:, :, :sup.shape[2]], -np.inf)
            idx = np.unravel_index(np.argmax(g), g.shape)
            # à gain égal, on préfère le plus bas (on monte étage par étage, comme un vrai montage)
            if np.isfinite(g[idx]) and g[idx] > 0 and (best is None or g[idx] > best[0] + 1e-6):
                best = (float(g[idx]), kn, idx)
        return best

    def place(self, kn, t):
        i, j, k = t
        X, Z, Kk = kn.shape
        self.occupied[i:i + X, j:j + Z, k:k + Kk] |= kn.solid
        # tenons recouverts par les cavités : consommés ; cases désormais pleines : plus de tenon
        fi, fj = np.nonzero(kn.female)
        self.studs[i + fi, j + fj, k] = False
        self.studs &= ~self.occupied
        for (a, b, c) in kn.male:
            ii, jj, kk = i + a, j + b, k + c
            if 0 <= ii < self.I and 0 <= jj < self.J and 0 <= kk < self.K and not self.occupied[ii, jj, kk]:
                self.studs[ii, jj, kk] = True
        # matrice LDraw : origine de la pièce = coin du motif + décalage ; Y vers le bas
        corner = np.array([self.t.x0 + 20 * i, -8 * k, self.t.z0 + 20 * j], float)
        pos = corner + kn.origin_offset
        self.placed.append({"part": kn.part, "q": kn.q, "cell": [int(i), int(j), int(k)], "shape": list(kn.shape),
                            "m": [round(float(v), 3) for v in pos] + [round(float(v), 6) for v in kn.R.reshape(-1)],
                            "occ": kn.occ})

    def run(self, max_parts=1500):
        t0 = time.time()
        while len(self.placed) < max_parts:
            mv = self.best_move()
            if mv is None:
                break
            gain, kn, t = mv
            self.place(kn, t)
            n = len(self.placed)
            if n % 25 == 0:
                cover = (self.occupied & (self.t.frac > 0.5)).sum() / max((self.t.frac > 0.5).sum(), 1)
                self.log(f"  {n} pièces, couverture {cover:.0%}, dernière {kn.part} gain {gain:.2f} ({time.time() - t0:.0f} s)")
        cover = (self.occupied & (self.t.frac > 0.5)).sum() / max((self.t.frac > 0.5).sum(), 1)
        outside = (self.occupied & (self.t.frac == 0)).sum()
        self.log(f"terminé : {len(self.placed)} pièces, couverture {cover:.0%}, cases hors cible {outside} "
                 f"({time.time() - t0:.0f} s)")

    # ---------------------------------------------------------- couleurs, d'après les photos
    def colorize(self):
        """Couleur de chaque pièce : médiane des pixels des photos là où ses cases visibles se projettent."""
        occ_owner = -np.ones(self.occupied.shape, int)
        for n, p in enumerate(self.placed):
            i, j, k = p["cell"]
            X, Z, Kk = p["shape"]
            sl = occ_owner[i:i + X, j:j + Z, k:k + Kk]
            sl[(p["occ"] > 0.3) & (sl < 0)] = n
        pal_codes = [c for c, _, _ in colors.PALETTE]
        samples = [[] for _ in self.placed]
        filled = occ_owner >= 0
        pad = np.pad(filled, 1)
        for name, (photo, mask) in self.t.views.items():
            cam = self.t.cams[name]
            H, W = mask.shape
            lab = cv2.cvtColor(C.flatten_lighting(photo, mask.astype(np.uint8) * 255) if hasattr(C, "flatten_lighting")
                               else photo, cv2.COLOR_BGR2LAB)
            d, f, right, up = C.camera_basis(cam["az"], cam["el"], cam["roll"])
            # face exposée vers la caméra : on regarde le voisin dans la direction de la caméra
            dirs = [((1, 0, 0), d[0]), ((-1, 0, 0), -d[0]), ((0, 0, 1), d[2]), ((0, 0, -1), -d[2]),
                    ((0, 1, 0), d[1]), ((0, -1, 0), -d[1])]
            ii, jj, kk = np.nonzero(filled)
            vis = np.zeros(len(ii), bool)
            for (di, dk_, dj), w in [((a, c, b), w) for (a, c, b), w in dirs]:
                if w <= 0.25:
                    continue
                nb = pad[ii + 1 + di, jj + 1 + dj, kk + 1 + dk_]
                vis |= ~nb
            ii, jj, kk = ii[vis], jj[vis], kk[vis]
            P = self.t.cell_center_world(ii, jj, kk)
            x, y, _ = C.project(P, cam, (W, H), self.t.center)
            xi, yi = np.round(x).astype(int), np.round(y).astype(int)
            ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
            for a, b, c, X_, Y_ in zip(ii[ok], jj[ok], kk[ok], xi[ok], yi[ok]):
                if mask[Y_, X_]:
                    samples[occ_owner[a, b, c]].append(lab[Y_, X_])
        lab_pal = cv2.cvtColor(np.array([[colors.code_bgr(c) for c in pal_codes]], np.uint8), cv2.COLOR_BGR2LAB)[0].astype(np.float32)
        w = np.array([colors.L_WEIGHT, 1, 1], np.float32)
        for p, s in zip(self.placed, samples):
            if s:
                med = np.median(np.array(s, np.float32), axis=0)
                p["color"] = int(pal_codes[int((((lab_pal - med) * w) ** 2).sum(1).argmin())])
            else:
                p["color"] = 19                               # pièce cachée : beige

    def assembly(self, subject):
        parts = [{"id": f"b{n + 1}", "part": p["part"], "color": p.get("color", 19), "m": p["m"],
                  "src": "constructeur", "status": "à vérifier", "step": n + 1} for n, p in enumerate(self.placed)]
        return {"subject": subject, "source": "constructeur pièce par pièce",
                "created": datetime.now().isoformat(timespec="seconds"), "parts": parts}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("--out", default=None, help="sujet de sortie (défaut : <sujet>_auto, images partagées)")
    ap.add_argument("--max", type=int, default=1500)
    a = ap.parse_args()
    out = a.out or a.subject + "_auto"
    t = carve(a.subject)
    b = Builder(t)
    b.run(a.max)
    b.colorize()
    odir = ROOT / "imgs" / out
    odir.mkdir(exist_ok=True)
    for f in (ROOT / "imgs" / a.subject).glob("*"):
        if f.suffix.lower() in (".jpeg", ".jpg", ".png") and not (odir / f.name).exists():
            (odir / f.name).symlink_to(f.resolve())
    (odir / "assemblage.json").write_text(json.dumps(b.assembly(out), ensure_ascii=False))
    print(f"-> imgs/{out}/assemblage.json")


if __name__ == "__main__":
    main()
