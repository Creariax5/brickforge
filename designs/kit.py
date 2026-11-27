"""Petit kit de conception : poser des pièces LDraw en coordonnées tenons/plaques, remplir des
volumes en briques, construire des sous-ensembles tournés, puis écrire l'assemblage pour l'app.

Repère : x, z en tenons (une case (x, z) couvre [x, x+1] × [z, z+1]), k en plaques depuis le sol.
LDraw : X = x·20, Z = z·20, Y = -k·8 (Y vers le bas).
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

from brickforge.ldlib import part_mesh

ROOT = Path(__file__).resolve().parent.parent
BRICKS = {(1, 1): "3005", (1, 2): "3004", (1, 3): "3622", (1, 4): "3010", (1, 6): "3009",
          (2, 2): "3003", (2, 3): "3002", (2, 4): "3001"}
PLATES = {(1, 1): "3024", (1, 2): "3023", (1, 3): "3623", (1, 4): "3710", (1, 6): "3666", (1, 8): "3460",
          (2, 2): "3022", (2, 3): "3021", (2, 4): "3020", (2, 6): "3795", (2, 8): "3034"}
TILES = {(1, 1): "3070b", (1, 2): "3069b", (1, 3): "63864", (1, 4): "2431", (1, 6): "6636", (1, 8): "4162",
         (2, 2): "3068b", (2, 3): "26603", (2, 4): "87079", (2, 6): "69729"}


def Ry(deg):
    a = math.radians(deg)
    c, s = round(math.cos(a), 9), round(math.sin(a), 9)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def Rz(deg):
    a = math.radians(deg)
    c, s = round(math.cos(a), 9), round(math.sin(a), 9)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def Rx(deg):
    a = math.radians(deg)
    c, s = round(math.cos(a), 9), round(math.sin(a), 9)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


_mesh = {}


def mesh(part):
    if part not in _mesh:
        _mesh[part] = part_mesh(part)
    return _mesh[part]


def natural_size(part):
    """Emprise (x, z) en tenons dans l'orientation canonique."""
    lo, hi = mesh(part)["bbox"]
    return round((hi[0] - lo[0]) / 20), round((hi[2] - lo[2]) / 20)


class Placer:
    """Méthodes de pose communes au modèle et aux sous-ensembles (qui redéfinissent place)."""

    def place(self, part, color, cx, cz, kb, R, note=""):
        raise NotImplementedError

    def at_origin(self, part, color, ox, oz, k, R, note=""):
        """Pose par l'origine LDraw de la pièce : (ox, oz) en tenons, origine à la hauteur du dessus
        de la couche k (pour une plaque : la plaque occupe la couche k). Utile quand la boîte englobante
        n'est pas centrée sur la pièce (rotules, pièces à appendice)."""
        self.place_origin(part, color, ox, oz, k + 1, R, note)

    def rotated(self, part, color, cx, cz, kb, R, note=""):
        """Pose avec une rotation quelconque (pièces montées de côté, SNOT)."""
        self.place(part, color, cx, cz, kb, R, note)

    def part(self, part, color, cx, cz, k, yaw=0, roll=0, note=""):
        R = Ry(yaw) @ (Rz(90 * roll) if roll else np.eye(3))
        self.place(part, color, cx, cz, k, R, note)

    def _flat(self, part, color, x, z, k, w, d, along, note):
        sx, sz = natural_size(part)
        if w is None or d is None:
            w, d = (sx, sz) if along != "z" else (min(sx, sz), max(sx, sz))
            if along == "x":
                w, d = max(sx, sz), min(sx, sz)
        yaw = 0 if (sx, sz) == (w, d) else 90
        self.place(part, color, x + w / 2, z + d / 2, k, Ry(yaw), note)

    def plate(self, part, color, x, z, k, w=None, d=None, along=None, note=""):
        self._flat(part, color, x, z, k, w, d, along, note)

    def tile(self, part, color, x, z, k, w=None, d=None, upright=False, note=""):
        if upright:   # tuile debout, face vers l'avant (-z), collée contre la face z+1
            w = w or natural_size(part)[0]
            self.place(part, color, x + w / 2, z + 1 - 0.2, k, Rx(90), note)
        else:
            self._flat(part, color, x, z, k, w, d, None, note)

    def slope(self, part, color, x, z, w, d, k, descend, note=""):
        dx, dz = descend
        yaw = math.degrees(math.atan2(-dx, -dz))   # géométrie canonique : descend vers -Z
        self.place(part, color, x + w / 2, z + d / 2, k, Ry(yaw), note)


def local_pose(part, cx, cz, kb, R):
    """Position LDraw (LDU) de l'origine d'une pièce posée comme Build.place, dans un repère local."""
    m = mesh(part)
    lo, hi = np.array(m["bbox"][0]), np.array(m["bbox"][1])
    corners = np.array([[a, b, c] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for c in (lo[2], hi[2])])
    rc = corners @ R.T
    rlo, rhi = rc.min(0), rc.max(0)
    pos = np.array([cx * 20, 0, cz * 20]) - np.array([(rlo[0] + rhi[0]) / 2, 0, (rlo[2] + rhi[2]) / 2])
    pos[1] = -kb * 8 - rhi[1]
    return pos


_group_ids = iter(range(1, 10**6))


class Group(Placer):
    """Sous-ensemble rigide : coordonnées locales (x local = vers l'extérieur), tourné autour d'un pivot.
    yaw : rotation horizontale ; tilt : inclinaison vers le bas de la pointe (degrés), autour du pivot.
    Le pivot est le centre de la rotule : (x, z) en tenons, à mi-hauteur de la couche k."""

    def __init__(self, parent, pivot, yaw, k, mirror, tilt=0.0):
        self.parent, self.pivot, self.k = parent, np.array(pivot, float), k
        self.R = Ry((180 if mirror else 0) + yaw) @ Rz(tilt)
        self.gid = next(_group_ids)
        self.P = np.array([self.pivot[0] * 20, -(k + 0.5) * 8, self.pivot[1] * 20])   # sans décalage global

    def _emit(self, part, color, pos_local, R, note):
        pos_local = pos_local + np.array([0, 0.5 * 8, 0])        # repère local : y = 0 au bas de la couche k
        pos = self.P + self.R @ pos_local
        self.parent.place_raw(part, color, pos, self.R @ R, note, group=self.gid)

    def place(self, part, color, cx, cz, kb, R, note=""):
        self._emit(part, color, local_pose(part, cx, cz, kb, R), R, note)

    def place_origin(self, part, color, ox, oz, ytop, R, note=""):
        self._emit(part, color, np.array([ox * 20, -ytop * 8, oz * 20], float), R, note)


class Build(Placer):
    def __init__(self, subject):
        self.subject = subject
        self.parts = []
        self.vox = {}        # (x, z, k) -> couleur : volumes remplis, convertis en briques à la fin
        self.solid = set()   # (x, z, k) occupés par des pièces posées explicitement
        self.k_offset = 0    # décalage vertical global (plaques), appliqué à toutes les poses
        self.z_offset = 0    # décalage global en profondeur (tenons), comme k_offset
        self.use_bricks = False  # remplissage en plaques seulement : joints croisés à chaque couche

    def place(self, part, color, cx, cz, kb, R, note=""):
        kb = kb + self.k_offset
        cz = cz + self.z_offset
        m = mesh(part)
        lo, hi = np.array(m["bbox"][0]), np.array(m["bbox"][1])
        corners = np.array([[a, b, c] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for c in (lo[2], hi[2])])
        rc = corners @ R.T
        rlo, rhi = rc.min(0), rc.max(0)
        center_local = np.array([(rlo[0] + rhi[0]) / 2, 0, (rlo[2] + rhi[2]) / 2])
        pos = np.array([cx * 20, 0, cz * 20]) - center_local
        pos[1] = -kb * 8 - rhi[1]                       # le point le plus bas de la pièce sur la couche kb
        self.parts.append({"part": part, "color": int(color), "R": R, "pos": pos, "note": note})
        # occupation (pièces alignées sur la grille seulement)
        x0, x1 = (pos[0] + rlo[0]) / 20, (pos[0] + rhi[0]) / 20
        z0, z1 = (pos[2] + rlo[2]) / 20, (pos[2] + rhi[2]) / 20
        top = -(pos[1] + rlo[1]) / 8
        if abs(R[1, 1]) > 0.99 and abs(R[0, 0]) in (0, 1):
            for xi in range(math.floor(x0 + 0.01), math.ceil(x1 - 0.01)):
                for zi in range(math.floor(z0 + 0.01), math.ceil(z1 - 0.01)):
                    for ki in range(int(round(kb)), max(int(round(kb)) + 1, int(math.floor(top + 0.01)))):
                        self.solid.add((xi, zi, ki))

    def place_origin(self, part, color, ox, oz, ytop, R, note=""):
        ytop = ytop + self.k_offset
        oz = oz + self.z_offset
        pos = np.array([ox * 20, -ytop * 8, oz * 20], float)
        self.parts.append({"part": part, "color": int(color), "R": R, "pos": pos, "note": note})
        if abs(R[1, 1]) > 0.99:   # occupation : la plaque (sans l'appendice) sur la couche ytop-1
            m = mesh(part)
            lo, hi = np.array(m["bbox"][0]), np.array(m["bbox"][1])
            for gx in np.arange(lo[0] + 10, hi[0] - 9, 20):
                for gz in np.arange(lo[2] + 10, hi[2] - 9, 20):
                    w = R @ np.array([gx, 0, gz]) + pos
                    self.solid.add((math.floor(w[0] / 20), math.floor(w[2] / 20), int(round(ytop - 1))))

    def group(self, pivot, yaw, k, tilt=0.0):
        return Group(self, pivot, yaw, k, mirror=pivot[0] < 0, tilt=tilt)

    def place_raw(self, part, color, pos, R, note="", group=None):
        """Pose directe (LDU), avec le décalage vertical global ; sans occupation de la grille."""
        pos = np.array(pos, float) + np.array([0, -self.k_offset * 8, 0])
        self.parts.append({"part": part, "color": int(color), "R": R, "pos": pos, "note": note, "group": group})

    def fill(self, x, z, layers, color):
        for k in layers:
            self.vox[(x, z + self.z_offset, k + self.k_offset)] = color

    def fill_column_range(self, cells, k0, k1, color):
        for x, z in cells:
            self.fill(x, z, range(k0, k1), color)

    def mark_top(self, *a):
        pass

    # ---------------------------------------------------------- volumes -> briques, plaques, tuiles
    def _merge_fill(self):
        if not self.vox:
            return
        xs, zs, ks = zip(*self.vox)
        ox, oz = min(xs), min(zs)
        W, L, H = max(xs) - ox + 1, max(zs) - oz + 1, max(ks) + 2
        col = -np.ones((W, L, H), int)
        for (x, z, k), c in self.vox.items():
            if (x, z, k) not in self.solid:
                col[x - ox, z - oz, k] = c
        solid = np.zeros((W, L, H), bool)
        for (x, z, k) in self.solid:
            if 0 <= x - ox < W and 0 <= z - oz < L and 0 <= k < H:
                solid[x - ox, z - oz, k] = True
        used = col < 0
        # Voxels cachés (entourés de tous côtés par de la matière) : une seule couleur, pour que les
        # plaques de remplissage puissent faire le pont entre des zones de couleurs différentes.
        mat = (col >= 0) | solid
        pad = np.pad(mat, 1, constant_values=False)
        hidden = (col >= 0) & pad[:-2, 1:-1, 1:-1] & pad[2:, 1:-1, 1:-1] & pad[1:-1, :-2, 1:-1] \
            & pad[1:-1, 2:, 1:-1] & pad[1:-1, 1:-1, :-2] & pad[1:-1, 1:-1, 2:]
        col[hidden] = 19

        def rects(avail, colors, sizes, k, kind, dk):
            for a, bb in sorted(sizes, key=lambda s: -(s[0] * s[1] * 10 + max(s))):
                # joints croisés : couche paire -> long côté selon x, impaire -> selon z
                pair = [(max(a, bb), min(a, bb)), (min(a, bb), max(a, bb))]
                for di, dj in dict.fromkeys(pair if k % 2 == 0 else pair[::-1]):
                    part = sizes[(min(di, dj), max(di, dj))]
                    for i in range(W - di + 1):
                        for j in range(L - dj + 1):
                            blk = avail[i:i + di, j:j + dj]
                            if not blk.all():
                                continue
                            cc = colors[i:i + di, j:j + dj]
                            if (cc != cc[0, 0]).any():
                                continue
                            avail[i:i + di, j:j + dj] = False
                            for kk in range(k, k + dk):
                                used[i:i + di, j:j + dj, kk] = True
                            self._flat(part, int(cc[0, 0]), i + ox, j + oz, k, di, dj, None, kind)

        for k in range(H):
            # briques : 3 couches identiques et libres
            if self.use_bricks and k + 2 < H:
                same = (~used[:, :, k]) & (~used[:, :, k + 1]) & (~used[:, :, k + 2]) \
                    & (col[:, :, k] == col[:, :, k + 1]) & (col[:, :, k] == col[:, :, k + 2])
                rects(same.copy(), col[:, :, k], BRICKS, k, "remplissage", 3)
            free = ~used[:, :, k]
            above = np.zeros((W, L), bool)
            if k + 1 < H:
                above = (col[:, :, k + 1] >= 0) | solid[:, :, k + 1]
            rects((free & ~above).copy(), col[:, :, k], TILES, k, "remplissage", 1)
            rects((free & above).copy(), col[:, :, k], PLATES, k, "remplissage", 1)

    def save(self):
        self.k_offset = 0          # les voxels ont déjà reçu leur décalage au moment du fill
        self.z_offset = 0
        self._merge_fill()
        parts = []
        for n, p in enumerate(self.parts):
            R, pos = p["R"], p["pos"]
            m = [round(float(v), 3) for v in pos] + [round(float(v), 6) for v in R.reshape(-1)]
            parts.append({"id": f"c{n + 1}", "part": p["part"], "color": p["color"], "m": m,
                          "src": "conception" if p["note"] != "remplissage" else "structure",
                          "status": "à vérifier" if p["note"] != "remplissage" else "structure",
                          **({"grp": p["group"]} if p.get("group") else {})})
        doc = {"subject": f"lego_{self.subject}", "source": "conception manuelle (Claude)",
               "created": datetime.now().isoformat(timespec="seconds"), "parts": parts}
        dest = ROOT / "imgs" / f"lego_{self.subject}" / "assemblage.json"
        if dest.exists():
            dest.with_suffix(".json.bak").write_text(dest.read_text())
        dest.write_text(json.dumps(doc, ensure_ascii=False))
        ldr = ROOT / "out" / f"{self.subject}_conception.ldr"
        lines = [f"0 {self.subject}", "0 Author: Brick Forge (conception)", ""]
        lines += [f"1 {p['color']} " + " ".join(f"{v:g}" for v in p["m"]) + f" {p['part']}.dat" for p in parts]
        ldr.write_text("\n".join(lines) + "\n")
        from collections import Counter
        print(f"{len(parts)} pièces ({Counter(p['src'] for p in parts)}) -> {dest}")
