"""Tortue : modèle conçu pièce par pièce à partir des vues Gemini (imgs/lego_tortue).

Repère : x = largeur (tenons, 0 = axe de symétrie), z = longueur (tenons, tête vers -z),
k = hauteur en plaques (0 = sol). Une case (x, z) couvre [x, x+1] × [z, z+1].

Usage : python -m designs.tortue   -> imgs/lego_tortue/assemblage.json (+ .ldr dans out/)
"""

from __future__ import annotations

from designs.kit import Build, Rx, Ry, Rz

# Couleurs LDraw
DORANGE, RBROWN, TAN, SAND, DTAN, OLIVE, YELLOW, BLACK, DBGRAY, NOUGAT, LBGRAY = 484, 70, 19, 378, 28, 330, 14, 0, 72, 84, 71

import os
b = Build("tortue")
# Inclinaison des nageoires vers le bas (degrés, autour du centre de la rotule). La comparaison préfère ~25°,
# limitée par le sol : les pointes doivent reposer sur la table (réglages choisis par designs.optimize).
FRONT_TILT = float(os.environ.get("FRONT_TILT", 13))
REAR_TILT = float(os.environ.get("REAR_TILT", 9))
PIVOT_UP = int(os.environ.get("PIVOT_UP", 0))   # rotules des nageoires remontées de N plaques
FRONT_YAW = float(os.environ.get("FRONT_YAW", 30))   # balayage des nageoires vers l arriere (degres)
REAR_YAW = float(os.environ.get("REAR_YAW", 53))
HEAD_DK = int(os.environ.get("HEAD_DK", 1))
FRONT_SHORT = int(os.environ.get("FRONT_SHORT", 1))
HEAD_DZ = int(os.environ.get("HEAD_DZ", 0))          # tête reculée vers le corps de N tenons  # 1 = nageoires avant raccourcies d un tenon         # tete montee ou descendue de N plaques
# Proportions mesurées sur le profil Gemini : le bas était trop épais de ~2 plaques.
# Tout le modèle descend d'une plaque, et les pieds passent de 2 plaques à 1 (voir plus bas).
b.k_offset = -1

# ------------------------------------------------------------------ carapace : rangées d'avant en arrière
# (z, longueur de la bande, couleur, hauteur du dessus en plaques)
ROWS = [
    (0, 2, DORANGE, 14),
    (1, 3, RBROWN, 16),
    (2, 3, TAN, 17),
    (3, 4, DORANGE, 17),
    (4, 3, DORANGE, 17),   # z4-z5 : plaque marron 1x2 à tenons contre la colonne, puis pentes 3x1
    (5, 3, DORANGE, 17),
    (6, 4, DORANGE, 17),
    (7, 3, TAN, 17),
    (8, 3, RBROWN, 16),
    (9, 2, NOUGAT, 14),
]
RIM_TOP = 8          # dessus de la bordure (plaques)
# Le profil Gemini ne montre que 2 segments au-dessus de la corniche (un mur d'une brique + la pente
# courbe) : le dôme descend de 3 plaques par rapport à la première version.
DROP = int(os.environ.get("DROP", 3))
DOME_BASE = RIM_TOP + DROP
b.k_offset = -1 - DROP
HALF = {-1: 1, 0: 4, 1: 5, 2: 5, 3: 5, 4: 5, 5: 5, 6: 5, 7: 5, 8: 5, 9: 4, 10: 3, 11: 1}  # demi-largeur de l'emprise

curved = {2: "11477", 3: "50950", 4: "61678"}
# Rayures verticales du flanc, d'avant en arrière (vue de profil) : couleur du remplissage sous chaque bande
STRIPE = {0: TAN, 1: RBROWN, 2: DORANGE, 3: RBROWN, 4: RBROWN, 5: DORANGE, 6: DORANGE, 7: TAN, 8: RBROWN, 9: DORANGE}
height = {"11477": 2, "50950": 3, "61678": 3}

for z, L, col, top in ROWS:
    for side in (-1, 1):
        start = 1 if side > 0 else -1           # première case hors colonne : x = 1 (droite) / x = -2 (gauche)
        inner = 0
        if z in (4, 5):                          # plaque 1x2 marron à tenons contre la colonne (posée une fois)
            inner = 1
            if z == 4:
                xc = 1 if side > 0 else -2
                b.plate("3023", RBROWN, x=xc, z=4, k=top - 1, along="z")
                b.fill_column_range([(xc, 4), (xc, 5)], DOME_BASE, top - 1, RBROWN)
        part = curved[L]
        h = height[part]
        x0 = (1 + inner) if side > 0 else (-1 - inner - L)
        b.slope(part, col, x=x0, z=z, w=L, d=1, k=top - h, descend=(side, 0))
        cells = [(x0 + i, z) for i in range(L)]
        b.fill_column_range(cells, DOME_BASE, top - h, STRIPE[z])

# Colonne centrale (x = -1, 0)
SPINE = [(-1, 12), (0, 15), (1, 16), (2, 17), (3, 17), (4, 17), (5, 17), (6, 17), (7, 17), (8, 16), (9, 15), (10, 14)]
spine_top = dict(SPINE)
b.slope("11477", RBROWN, x=-1, z=-1, w=1, d=2, k=13, descend=(0, -1))      # avant : pentes courbes vers l'avant
b.slope("11477", RBROWN, x=0, z=-1, w=1, d=2, k=13, descend=(0, -1))
b.fill_column_range([(-1, -1), (0, -1), (-1, 0), (0, 0)], DOME_BASE, 13, RBROWN)
b.plate("3022", RBROWN, x=-1, z=1, k=15, w=2, d=2)                          # 2 tenons (z1) : plaque 2x2
b.fill_column_range([(-1, 1), (0, 1), (-1, 2), (0, 2)], DOME_BASE, 15, RBROWN)
b.tile("3068b", DORANGE, x=-1, z=2, k=16, w=2, d=2)                          # tuiles 2x2 orange / marron / orange
b.tile("3068b", RBROWN, x=-1, z=4, k=16, w=2, d=2)
b.tile("3068b", DORANGE, x=-1, z=6, k=16, w=2, d=2)
b.fill_column_range([(x, z) for x in (-1, 0) for z in range(2, 8)], DOME_BASE, 16, RBROWN)
b.plate("3022", RBROWN, x=-1, z=8, k=15, w=2, d=2)                          # 2 tenons (z8)
b.fill_column_range([(-1, 8), (0, 8)], DOME_BASE, 15, RBROWN)
b.slope("11477", RBROWN, x=-1, z=9, w=1, d=2, k=13, descend=(0, 1))         # arrière : pentes courbes vers l'arrière
b.slope("11477", RBROWN, x=0, z=9, w=1, d=2, k=13, descend=(0, 1))
b.fill_column_range([(-1, 9), (0, 9), (-1, 10), (0, 10)], DOME_BASE, 13, RBROWN)
# Arrière des bandes (z10) : plaques 1x1 orange à tenon
b.plate("3024", DORANGE, x=-2, z=10, k=12)
b.plate("3024", DORANGE, x=1, z=10, k=12)
b.fill_column_range([(-2, 10), (1, 10)], DOME_BASE, 12, TAN)

b.k_offset = -1                                                              # fin du dôme
# ------------------------------------------------------------------ corniche (k5 -> k8)
# k5 : plaque beige sur toute l'emprise ; k6-k8 : bourrelet de pentes 1x1 tournées vers l'extérieur,
# couleurs alternées relevées sur le profil (d'avant en arrière).
RIM = {-1: RBROWN, 0: TAN, 1: DORANGE, 2: RBROWN, 3: DORANGE, 4: DORANGE, 5: RBROWN, 6: DORANGE, 7: DORANGE,
       8: RBROWN, 9: TAN, 10: TAN, 11: TAN}
for z, hw in HALF.items():
    for x in range(-hw, hw):
        b.fill(x, z, [5], TAN)
rim_cells = set()
for z, hw in HALF.items():
    for x in (-hw, hw - 1):                                                   # flancs gauche / droit
        if (x, z) not in rim_cells:
            rim_cells.add((x, z))
            b.slope("54200", RIM[z], x=x, z=z, w=1, d=1, k=6, descend=(1 if x >= 0 else -1, 0))
    for x in range(-hw + 1, hw - 1):                                          # avant / arrière : bord exposé
        front = HALF.get(z - 1, 0) <= abs(x + 0.5)
        back = HALF.get(z + 1, 0) <= abs(x + 0.5)
        if (front or back) and (x, z) not in rim_cells and not (-1 <= x <= 0 and z in (-1, 11)):
            rim_cells.add((x, z))
            b.slope("54200", RIM[z], x=x, z=z, w=1, d=1, k=6, descend=(0, -1) if front else (0, 1))
for z, hw in HALF.items():                                                    # intérieur de la corniche
    for x in range(-hw, hw):
        if (x, z) not in rim_cells:
            b.fill(x, z, [6, 7], TAN)

# ------------------------------------------------------------------ dessous : dôme inversé (k2 -> k5)
# Colonne centrale (x -1..0), la partie la plus basse : bas à k2.
for x in (-1, 0):
    b.slope("24201", TAN, x=x, z=0, w=1, d=2, k=2, descend=(0, -1))           # avant arrondi (pentes courbes inversées)
for z in range(2, 8):
    b.plate("3023", TAN, x=-1, z=z, k=2, w=2, d=1)                             # 6 plaques 1x2 en travers
for x in (-1, 0):
    b.plate("3623", TAN, x=x, z=8, k=2, w=1, d=3)                              # arrière : 2 plaques 1x3
# Bandes : pentes courbes inversées, partie épaisse contre la colonne, partie fine vers le bord.
# (z, pièce, longueur, couleur gauche, couleur droite) — vue de dessous
BELLY = [
    (2, "24201", 2, TAN, TAN),
    (3, "13547", 4, OLIVE, DTAN),
    (4, "13547", 4, TAN, TAN),
    (5, "13547", 4, TAN, TAN),
    (6, "13547", 4, DTAN, OLIVE),
    (7, "24201", 2, TAN, TAN),
]
belly_top = {}                                                                # (x, z) -> dessus de la pièce du dessous
for z, part, Lb, cl, cr in BELLY:
    for side, col in ((-1, cl), (1, cr)):
        x0 = 1 if side > 0 else -1 - Lb
        b.slope(part, col, x=x0, z=z, w=Lb, d=1, k=2, descend=(side, 0))
        for i in range(Lb):
            belly_top[(x0 + i, z)] = 2 + (3 if part == "13547" else 2)
# Avant (z0-z1) : 2 pentes courbes inversées par côté, vers l'avant (beige contre la colonne, olive à l'extérieur)
for side in (-1, 1):
    for i, col in ((1, TAN), (2, OLIVE)):
        x = i if side > 0 else -1 - i
        b.slope("24201", col, x=x, z=0, w=1, d=2, k=2, descend=(0, -1))
        for zz in (0, 1):
            belly_top[(x, zz)] = 4
# Arrière (z8-z9) : nougat contre la colonne, olive autour
for side in (-1, 1):
    xi = 1 if side > 0 else -2
    xo = 2 if side > 0 else -3
    b.plate("3024", NOUGAT, x=xi, z=8, k=2)
    b.plate("3024", OLIVE, x=xi, z=9, k=2)
    b.slope("24201", OLIVE, x=xo, z=8, w=1, d=2, k=2, descend=(0, 1))
    belly_top.update({(xi, 8): 3, (xi, 9): 3, (xo, 8): 4, (xo, 9): 4})
for x in (-1, 0):
    for z in (0, 1):
        belly_top[(x, z)] = 4
    for z in range(2, 11):
        belly_top[(x, z)] = 3
# Remplissage entre le dessous et la corniche ; les cases sans pièce du dessous commencent plus haut (k4)
for z, hw in HALF.items():
    for x in range(-min(hw, 4), min(hw, 4)):
        b.fill(x, z, range(belly_top.get((x, z), 4), 5), TAN)

# Pieds : rangées 4 et 5 (vue de dessous), plaques rondes vert sauge + beige sous la partie épaisse des bandes
for (x, z) in [(-2, 4), (1, 4), (-2, 5), (1, 5)]:
    b.part("6141", TAN, cx=x + 0.5, cz=z + 0.5, k=1)                          # une seule plaque ronde (k1 -> sol avec le décalage)

# ------------------------------------------------------------------ cou et tête
b.k_offset = -1 - DROP + HEAD_DK
b.z_offset = HEAD_DZ                                                         # tête avancée (-) ou reculée (+), avec sa rotule                                                      # la tête suit le dôme (profil Gemini)
# Tête : cœur de 2 tenons de large (x -1..1) et 5 de long (z -7..-3), collier en z -2, du sol k=8 au dessus k=16.
# Rotules « Joint-8 » : bille au bout (22890, côté corps) + logement au bout (14418, côté membre).
# Centre de la bille / du logement : à 1,5 tenon du centre de la plaque, à mi-épaisseur.
BALL, SOCKET = "22890", "14418"
# cou : bille encastrée à l'avant du corps (vers -z), logement sous l'arrière de la tête (vers +z)
b.at_origin(BALL, DBGRAY, ox=0, oz=0, k=6, R=Ry(90))                          # centre de bille : (0, -1.5), k 6.5
b.at_origin(SOCKET, LBGRAY, ox=0, oz=-3, k=6, R=Ry(-90))                      # centre du logement : (0, -1.5), k 6.5
# Profil de la tête (d'avant en arrière : z -7 .. -3, collier en z -2) — d'après la vue de profil :
# menton en courbe continue, dessus arrondi devant et derrière, plaque beige à 2 tenons au milieu,
# museau olive arrondi, pente beige foncé qui prolonge l'arrière vers le collier.
import numpy as np
# Tête v2 (d'après la comparaison dessus / dessous / profil) : 4 tenons de large avec les joues,
# 4 de long (z -6..-3) + collier (z -2). Les yeux sont vers le milieu des côtés, pas au coin avant.
# mâchoire (k7 -> k10) : menton arrondi = pente courbe inversée 2x2, partie fine vers l'avant
b.slope("32803", TAN, x=-1, z=-6, w=2, d=2, k=7, descend=(0, -1))
b.plate("3022", TAN, x=-1, z=-6, k=9, w=2, d=2)
for k in (7, 8, 9):
    b.plate("3021", TAN, x=-1, z=-4, k=k, w=2, d=3)                             # arrière de la mâchoire + collier (z -4..-2)
# k10 : plaque 4x4 qui relie les deux joues au cœur de la tête
b.plate("3031", TAN, x=-2, z=-6, k=10, w=4, d=4)
b.plate("3023", TAN, x=-1, z=-2, k=10, w=2, d=1)                              # collier
# joues (x -2 et x 1, z -6..-3) : beige en bas (sous la plaque 4x4), vert sauge au-dessus, tuile sur le dessus
for xc in (-2, 1):
    b.fill_column_range([(xc, z) for z in range(-6, -2)], 8, 10, TAN)
    b.fill_column_range([(xc, z) for z in range(-6, -2)], 11, 13, SAND)
    b.tile("2431", SAND, x=xc, z=-6, k=13, w=1, d=4)
# crâne (k11 -> k14)
b.plate("3002", SAND, x=-1, z=-6, k=11, w=2, d=3)
b.plate("3004", TAN, x=-1, z=-3, k=11, w=2, d=1)
# dessus (k14 -> k16) : courbe avant, plaque beige à 2 tenons, courbe arrière
b.slope("15068", SAND, x=-1, z=-6, w=2, d=2, k=14, descend=(0, -1))
b.plate("3023", SAND, x=-1, z=-4, k=14, w=2, d=1)
b.plate("3023", TAN, x=-1, z=-4, k=15, w=2, d=1)                              # 2 tenons beiges (vus de face et de profil)
b.slope("15068", SAND, x=-1, z=-3, w=2, d=2, k=14, descend=(0, 1))
# collier (z -2) : pente beige foncé qui continue l'arrondi de l'arrière de la tête
for x in (-1, 0):
    b.slope("54200", DTAN, x=x, z=-2, w=1, d=1, k=11, descend=(0, 1))
# museau : pente courbe olive montée debout sur la face avant (z = -6)
SNOUT = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]], float)                   # longueur -> verticale, dessus -> avant
b.rotated("11477", OLIVE, cx=0, cz=-6.4, kb=10, R=SNOUT)
# faces extérieures des joues (SNOT) : œil vers l'avant du milieu, tuile vert sauge (autocollant écailles) derrière
for s_ in (-1, 1):
    up = Rz(90 * s_)                                                          # dessus de la pièce tourné vers ±x
    b.rotated("6141", BLACK, cx=s_ * 2.2, cz=-5.5, kb=11, R=up)               # œil : plaque ronde 1x1 noire, cellule avant
    b.rotated("3068b", SAND, cx=s_ * 2.2, cz=-4.0, kb=9, R=up)                # joue : tuile 2x2 debout (k9 -> k14), z -5..-3

b.k_offset = -1

b.z_offset = 0
# ------------------------------------------------------------------ nageoires (sous-ensembles tournés)
def joint(side, ball_x, ball_z, k):
    """Bille côté corps, alignée sur la grille, pointant vers l'extérieur ; son centre = pivot de la nageoire."""
    b.at_origin(BALL, DBGRAY, ox=ball_x - side * 1.5, oz=ball_z, k=k, R=Ry(0 if side > 0 else 180))


def front_flipper(side):
    """Nageoire avant : 7,5 x 3 tenons, balayée de 30° vers l'arrière, pivot = centre de la bille.
    Repère local : x vers l'extérieur ; rangées -1, 0, +1 centrées sur l'axe de la rotule.
    Le côté gauche est une rotation (pas un miroir) du droit : le bord d'attaque change de signe."""
    pivot = (side * 4.5, 1.5)
    joint(side, *pivot, k=4 + PIVOT_UP)
    f = b.group(pivot=pivot, yaw=side * -FRONT_YAW, k=4 + PIVOT_UP, tilt=FRONT_TILT)
    L = -1 if side > 0 else 1          # rangée du bord d'attaque (vers l'avant de la tortue)
    T = -L                             # rangée du bord de fuite

    def rz(r):                         # coin min (en z local) de la rangée r
        return r - 0.5

    # k0 : plaque à logement, emboîtée sur la bille
    f.at_origin(SOCKET, LBGRAY, ox=1.5, oz=0, k=0, R=Ry(180))
    S = FRONT_SHORT                    # 1 = nageoire raccourcie d'un tenon (6,5 au lieu de 7,5)
    # k1 : dessous (vu sur la vue de dessous)
    f.plate("3020" if not S else "3021", SAND, x=1, z=min(rz(0), rz(T)), k=1, w=4 - S, d=2)   # vert sauge, rangées 0 et fuite
    f.plate("3623", TAN, x=1, z=rz(L), k=1, w=3, d=1)                         # 1x3 beige, bord d'attaque
    if not S:
        f.plate("3024", TAN, x=4, z=rz(L), k=1)
    f.rotated("30357", TAN, cx=6.5 - S, cz=0, kb=1, R=Ry(0 if side > 0 else 90))  # pointe 3x3, coin arrière-ext. arrondi
    # k2 : dessus (vu sur la vue de dessus)
    f.plate("3024", TAN, x=1, z=rz(L), k=2)                                   # tenon beige près du corps
    f.tile("3070b", TAN, x=2, z=rz(L), k=2)
    f.tile("3070b", YELLOW, x=3, z=rz(L), k=2)                                # accent jaune
    if not S:
        f.tile("3070b", TAN, x=4, z=rz(L), k=2)
    f.plate("3710" if not S else "3623", SAND, x=1, z=rz(0), k=2, w=4 - S, d=1)   # rangée de tenons
    f.tile("2431" if not S else "63864", SAND, x=1, z=rz(T), k=2, w=4 - S, d=1)   # bord de fuite lisse
    # pointe presque toute vert sauge ; la plaque 3x3 beige dessous ne dépasse qu'en liseré sur l'arrondi
    # 79491 = plaque en L de 3 tenons, coin extérieur arrondi (canonique : coin -x-z arrondi, case +x+z vide)
    f.rotated("79491", SAND, cx=7 - S, cz=T * 0.5, kb=2, R=Ry(180 if side > 0 else -90))  # coin arrondi au bout
    f.tile("3070b", SAND, x=6 - S, z=rz(0), k=2)                                   # case vide du L
    f.tile("3069b", SAND, x=5 - S, z=min(rz(0), rz(T)), k=2, w=1, d=2)             # jonction
    f.tile("3070b", SAND, x=5 - S, z=rz(L), k=2)
    if not S:
        f.tile("3070b", SAND, x=6, z=rz(L), k=2)
    f.rotated("25269", SAND, cx=7.5 - S, cz=L, kb=2, R=Ry(0 if side > 0 else -90))  # quart de rond au coin avant-ext.


def rear_flipper(side):
    """Nageoire arrière : 5 x 3 tenons, balayée de 45° vers l'arrière, fine (2 plaques).
    Dessus : tuiles lisses près du corps, 6 tenons (2x2 + pointe arrondie), liseré beige autour."""
    pivot = (side * 3.5, 9.5)
    joint(side, *pivot, k=3 + PIVOT_UP)
    f = b.group(pivot=pivot, yaw=side * -REAR_YAW, k=3 + PIVOT_UP, tilt=REAR_TILT)
    L = -1 if side > 0 else 1
    T = -L

    def rz(r):
        return r - 0.5

    f.at_origin(SOCKET, LBGRAY, ox=1.5, oz=0, k=0, R=Ry(180))
    # k1 : dessous — vert sauge côté fuite, base beige côté attaque et pointe
    f.plate("3022", SAND, x=1, z=min(rz(0), rz(T)), k=1, w=2, d=2)
    f.plate("3023", TAN, x=1, z=rz(L), k=1, w=2, d=1)
    f.rotated("30357", TAN, cx=4.5, cz=0, kb=1, R=Ry(0 if side > 0 else 90))  # 3x3, coin arrière-extérieur arrondi
    # k2 : dessus
    f.tile("3070b", SAND, x=1, z=rz(L), k=2)                                   # tuiles lisses près du corps
    f.tile("3070b", SAND, x=1, z=rz(0), k=2)
    f.tile("3070b", TAN, x=1, z=rz(T), k=2)                                    # pièce beige côté fuite
    f.tile("3070b", SAND, x=2, z=rz(T), k=2)
    f.plate("3022", SAND, x=2, z=min(rz(L), rz(0)), k=2, w=2, d=2)             # 4 tenons
    f.rotated("79491", SAND, cx=5, cz=L * 0.5, kb=2, R=Ry(180 if side > 0 else -90))  # pointe arrondie (L de 3 tenons)
    f.tile("3070b", SAND, x=4, z=rz(L), k=2)                                   # case vide du L
    f.tile("3070b", TAN, x=3, z=rz(T), k=2)                                    # liseré beige côté fuite
    f.tile("3070b", TAN, x=4, z=rz(T), k=2)


for s in (-1, 1):
    front_flipper(s)
    rear_flipper(s)

# ------------------------------------------------------------------ queue
b.plate("3022", TAN, x=-1, z=10, k=5, w=2, d=2)                              # ancre la rangée de queue sur la dernière rangée du corps
b.plate("3023", TAN, x=-1, z=11, k=6, w=2, d=1)
b.tile("3069b", DORANGE, x=-1, z=11, k=7, w=2, d=1)

if __name__ == "__main__":
    b.save()
