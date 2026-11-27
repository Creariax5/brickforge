"""Défi : reproduire la figurine « homme en costume bleu marine » (image Gemini, data/defi_costume/cible.jpeg).

Méthode (notes 15–16) : on garde le squelette d'une BrickHeadz officielle de même construction — Marty McFly (41611, 2e figurine) :
noyau de tête en briques à tenons latéraux 22885, cadre du corps, socle — et on refait tout ce qui se voit d'après l'image :
couleurs, cheveux, col de chemise en V, mains, sans accessoire. Le moteur vérifie ensuite que rien ne vole et qu'il n'y a pas de collision.

Repère LDraw : y vers le bas (le haut de la tête est vers y négatif), l'avant de la figurine est vers z négatif.

    python -m brickforge.defi_costume        → data/defi_costume/model.json, model.ldr, rapport de constructibilité
"""

from __future__ import annotations

import json
from pathlib import Path

from brickforge import fill as F
from brickforge.buildcheck import check

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "defi_costume"

# couleurs LDraw
BLACK, WHITE, DARK_BLUE, REDDISH_BROWN, LIGHT_NOUGAT, LBG = 0, 15, 272, 70, 78, 71


def base_figure():
    figs = {f"{f['num']}:{f['fig']}": f for f in json.loads((F.OUT / "figures.json").read_text())}
    return [dict(p) for p in figs["41611-1:1"]["placed"]]


def recolor(placed):
    """Couleurs de la cible : costume bleu marine, chemise blanche, peau claire, cheveux brun-roux, socle noir."""
    remap = {
        4: DARK_BLUE,        # gilet rouge de Marty → veste bleu marine
        1: DARK_BLUE,        # jambes bleues → pantalon bleu marine
        19: LIGHT_NOUGAT,    # peau tan → peau claire (visage, oreilles, mains)
        70: REDDISH_BROWN,   # cheveux : déjà brun-roux
        272: DARK_BLUE,      # manches
        14: LBG, 2: LBG, 29: LBG, 72: LBG,   # pièces cachées du noyau : gris neutre
    }
    out = []
    for p in placed:
        q = dict(p)
        c = p.get("color", 71)
        if p["part"] == "3023" and c == 15:          # chaussures blanches → pantalon jusqu'au socle
            c = DARK_BLUE
        q["color"] = remap.get(c, c)
        if p["part"] == "98138pz0":                 # yeux : noirs unis sur l'image (pas de reflets imprimés)
            q["part"] = "98138"
        out.append(q)
    return out


def remove_accessory(placed):
    """L'objet noir tenu à la main par Marty (pas dans la cible)."""
    acc = {"60849", "4595", "3069bpzc"}
    return [p for p in placed if not (p["part"] in acc and p["m"][0] > 40)]


def shirt(placed):
    """Chemise : la brique imprimée de Marty → brique blanche unie (le col en V est fait par la veste)."""
    for p in placed:
        if p["part"].startswith("3245c"):
            p["part"] = "3245c"
            p["color"] = WHITE
    return placed


FACE = [-1, 0, 0, 0, 0, 1, 0, 1, 0]          # tuile posée sur la face avant (tenons vers −z), comme les tuiles du visage de Marty
FACE_ROUND_BR = [1, 0, 0, 0, 0, -1, 0, 1, 0]  # quart de rond, coin arrondi en bas à droite (vu de face)
FACE_ROUND_BL = [0, 0, 1, 1, 0, 0, 0, 1, 0]   # … en bas à gauche
FACE_ROUND_TR = [0, 0, -1, -1, 0, 0, 0, 1, 0] # … en haut à droite
IDENT = [1, 0, 0, 0, 1, 0, 0, 0, 1]


def at(P, part, x, y, z):
    """Indice de la pièce `part` à la position (x, y, z) (à 1 LDU près)."""
    for i, p in enumerate(P):
        if p["part"].startswith(part) and all(abs(a - b) < 1.5 for a, b in zip(p["m"][:3], (x, y, z))):
            return i
    raise KeyError((part, x, y, z))


def drop(P, keys):
    idx = {at(P, *k) for k in keys}
    return [p for i, p in enumerate(P) if i not in idx]


def piece(part, color, x, y, z, R=IDENT):
    return {"part": part, "color": color, "m": [x, y, z] + list(R)}


def collar(P):
    """Col en V : la brique blanche 1 × 2 × 2 → 4 briques 1 × 1 blanches à tenon de face (4070) ; dessus, tuiles blanches en haut
    et quarts de rond bleu marine en bas, dont les coins arrondis dessinent la pointe du V."""
    P = drop(P, [("3245c", 0, -112, -30), ("3023", 0, -64, -30)])
    P += [piece("3023", WHITE, 0, -112, -30)]
    for x in (-10, 10):
        P += [piece("4070", WHITE, x, -104, -30), piece("4070", WHITE, x, -80, -30)]
        P += [piece("3070b", WHITE, x, -94, -44, FACE)]
    P += [piece("25269", DARK_BLUE, -10, -70, -44, FACE_ROUND_TR), piece("25269", DARK_BLUE, 10, -70, -44, FACE)]
    return P


def sideburns(P):
    """Favoris : les deux rangées du haut du visage, brunes sur les bords, arrondies vers l'intérieur en bas (quarts de rond)."""
    P = drop(P, [("3070b", -30, -182, -56), ("3623", 10, -182, -56), ("2431", 0, -162, -56),
                 ("3069b", 20, -182, -64), ("25269", -10, -182, -64)])
    P += [piece("3070b", REDDISH_BROWN, -30, -182, -56, FACE), piece("3069b", LIGHT_NOUGAT, 0, -182, -56, FACE),
          piece("3070b", REDDISH_BROWN, 30, -182, -56, FACE),
          piece("25269", REDDISH_BROWN, -30, -162, -56, FACE_ROUND_BR), piece("3069b", LIGHT_NOUGAT, 0, -162, -56, FACE),
          piece("25269", REDDISH_BROWN, 30, -162, -56, FACE_ROUND_BL)]
    return P


def fringe(P):
    """Frange : deux pentes courbes 2 × 2 symétriques à l'avant du crâne, à la place de la mèche de Marty ;
    les doubles pentes 4 × 1 des côtés deviennent des pentes 2 × 1 à l'arrière (l'avant est couvert par la frange)."""
    P = drop(P, [("3022", 0, -200, -40), ("25269", -10, -208, -50), ("11477", 20, -192, -50), ("2420", -10, -208, -30),
                 ("2420", 30, -200, -10), ("2420", -30, -200, -10), ("11477", 40, -182, -40),
                 ("93273", -30, -192, 0), ("93273", 30, -192, 0)])
    # base de la frange : plaque 2 × 4 qui déborde au-dessus du front (comme la 2 × 2 de Marty), puis 1 × 4 + tuile derrière
    P += [piece("3020", REDDISH_BROWN, 0, -200, -40), piece("3710", REDDISH_BROWN, 0, -200, -10),
          piece("3069b", REDDISH_BROWN, -20, -208, -10), piece("3070b", REDDISH_BROWN, 30, -208, -10)]
    # les deux rouleaux, une plate plus haut que le reste des cheveux (en relief, comme sur l'image)
    P += [piece("15068", REDDISH_BROWN, -20, -200, -40), piece("15068", REDDISH_BROWN, 20, -200, -40)]
    BACK = [-1, 0, 0, 0, 1, 0, 0, 0, -1]                         # pente qui descend vers l'arrière
    P += [piece("11477", REDDISH_BROWN, -30, -192, 20, BACK), piece("11477", REDDISH_BROWN, 30, -192, 20, BACK)]
    return P


def build(steps=("recolor", "accessory", "shirt", "collar", "sideburns", "fringe")):
    P = base_figure()
    if "accessory" in steps:
        P = remove_accessory(P)
    if "recolor" in steps:
        P = recolor(P)
    if "shirt" in steps:
        P = shirt(P)
    if "collar" in steps:
        P = collar(P)
    if "sideburns" in steps:
        P = sideburns(P)
    if "fringe" in steps:
        P = fringe(P)
    if "parting" in steps:
        P = parting(P)
    return P


def save(P, name="model"):
    OUT.mkdir(parents=True, exist_ok=True)
    chk = check(P)
    rep = {"pieces": len(P), "floating": len(chk["floating"]), "floating_parts": chk["floating_parts"],
           "collisions": len(chk["collisions"]), "no_snap": chk["no_snap"]}
    (OUT / f"{name}.json").write_text(json.dumps({"placed": P, "check": rep}))
    lines = ["0 Défi costume — Brick Forge", "0 Name: " + name + ".ldr"]
    for p in P:
        m = p["m"]
        lines.append(f"1 {p.get('color', 71)} " + " ".join(f"{v:g}" for v in m[:3]) + " " + " ".join(f"{v:g}" for v in m[3:]) + f" {p['part']}.dat")
    (OUT / f"{name}.ldr").write_text("\n".join(lines) + "\n")
    return rep


TO_PLUS_X = [0, 0, -1, 0, 1, 0, 1, 0, 0]       # pente qui descend vers +x
TO_MINUS_X = [0, 0, 1, 0, 1, 0, -1, 0, 0]      # pente qui descend vers −x


def parting(P):
    """Raie au milieu : deux rouleaux de l'avant à l'arrière. Chaque côté est une pente courbe 2 × 2 qui descend vers la raie ;
    deux rangées (avant, milieu) sur une base de plaques. Les côtés des cheveux redescendent déjà vers l'extérieur."""
    P = [p for p in P if not (p["part"] == "15068" and p["m"][2] < 0)]           # les rouleaux de la v3 (avant)
    P = drop(P, [("3069b", -20, -208, -10), ("3070b", 30, -208, -10), ("2420", 10, -208, 10)])
    # la 15068 a un dessous en marche : son côté haut repose une plaque plus haut → plaque 1 × 4 sous le bord extérieur
    ALONG_Z = [0, 0, 1, 0, 1, 0, -1, 0, 0]
    P = drop(P, [("11477", -30, -192, 20), ("11477", 30, -192, 20)])
    P += [piece("3710", REDDISH_BROWN, -30, -208, -20, ALONG_Z), piece("3710", REDDISH_BROWN, 30, -208, -20, ALONG_Z)]
    for x in (-30, 30):                                           # arrière des côtés : couvrir les tenons du noyau de tête
        P += [piece("3024", REDDISH_BROWN, x, -200, 30), piece("3070b", REDDISH_BROWN, x, -208, 30), piece("3024", REDDISH_BROWN, x, -200, 10)]
    for z in (-40, 0):
        P += [piece("15068", REDDISH_BROWN, -20, -200, z, TO_PLUS_X), piece("15068", REDDISH_BROWN, 20, -200, z, TO_MINUS_X)]
    return P


VERSIONS = [
    ("v1 · squelette de Marty recoloré", "couleurs de la cible, accessoire retiré, chemise unie", ("recolor", "accessory", "shirt")),
    ("v2 · col en V et favoris", "tuiles et quarts de rond posés sur les tenons de face", ("recolor", "accessory", "shirt", "collar", "sideburns")),
    ("v3 · frange en deux rouleaux", "plaque 2 × 4 qui déborde au-dessus du front + deux pentes courbes 2 × 2 en relief", ("recolor", "accessory", "shirt", "collar", "sideburns", "fringe")),
]


def publish():
    vs = []
    for title, sub, steps in VERSIONS:
        P = build(steps)
        rep = save(P, name=title.split(" ")[0])
        vs.append({"title": title, "sub": sub, "placed": P, "check": rep})
        print(title, rep)
    (ROOT / "research" / "assets" / "17-defi.json").write_text(json.dumps({"versions": vs}))


if __name__ == "__main__":
    publish()
