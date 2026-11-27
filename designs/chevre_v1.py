"""Chèvre naine (photo imgs/lego_chevre/photo.png) : modèle conçu pièce par pièce, sans passer par Gemini.

Traits repris de la photo : corps blanc à taches noires, avant et cou noirs, pattes fines aux sabots
noirs (avant entièrement noires), tête blanche au chanfrein clair et museau noir, oreilles noires
à l'horizontale, petites cornes grises, queue blanche relevée, collier rouge.

Repère : x = largeur (tenons, corps de x -2 à 2), z = longueur (tête vers -z), k = hauteur en plaques.
Usage : python -m designs.chevre_v1
"""

from __future__ import annotations

from designs.kit import Build, Rz

WHITE, BLACK, RED, LBGRAY, GREEN, TAN = 15, 0, 4, 71, 2, 19

b = Build("chevre_v1")
b.use_bricks = True

# ------------------------------------------------------------------ pattes (k0 -> k9) : briques rondes 1x1
LEGS = {(-2, 1): "avant", (1, 1): "avant", (-2, 6): "arrière", (1, 6): "arrière"}
for (x, z), kind in LEGS.items():
    if kind == "avant":                                       # pattes avant noires
        cols = [BLACK, BLACK, BLACK]
    else:                                                     # pattes arrière blanches, sabot noir
        cols = [BLACK, WHITE, WHITE] if x == -2 else [BLACK, BLACK, WHITE]   # bande noire sur une patte
    for i, c in enumerate(cols):
        b.part("3062b", c, cx=x + 0.5, cz=z + 0.5, k=3 * i)

# ------------------------------------------------------------------ corps (k9 -> k18)
b.plate("3035", WHITE, x=-2, z=0, k=9, w=4, d=8)              # ventre : plaque 4x8 posée sur les 4 pattes


def body_color(x, z, k):
    if z == 0 or (z == 1 and k <= 12):                        # poitrail et épaule noirs
        return BLACK
    if x == -2 and z in (3, 4) and 11 <= k <= 14:             # tache sur le flanc gauche
        return BLACK
    if x == 1 and z in (4, 5) and 12 <= k <= 15:              # tache sur le flanc droit
        return BLACK
    if z == 7 and k >= 13:                                    # tache arrière
        return BLACK
    return WHITE


for x in range(-2, 2):
    for z in range(0, 8):
        for k in range(10, 16):
            b.fill(x, z, [k], body_color(x, z, k))
# dos arrondi : pentes 1x2 sur les bords, plaques au centre
for z in range(0, 8, 2):
    for xe, d in ((-2, -1), (1, 1)):
        c = BLACK if (z == 0) or (xe == 1 and z == 4) or (z == 6 and xe == 1) else WHITE
        b.slope("85984", c, x=xe, z=z, w=1, d=2, k=16, descend=(d, 0))
for z in range(0, 8):
    b.fill(-1, z, [16], WHITE)
    b.fill(0, z, [16], WHITE)
b.tile("3068b", WHITE, x=-1, z=2, k=17, w=2, d=2)
b.tile("3068b", BLACK, x=-1, z=4, k=17, w=2, d=2)             # tache noire sur le dos

# ------------------------------------------------------------------ queue (relevée, blanche)
b.plate("3022", WHITE, x=-1, z=6, k=17, w=2, d=2)
b.part("3062b", WHITE, cx=-0.5, cz=7.5, k=18)
b.slope("54200", WHITE, x=-1, z=7, w=1, d=1, k=21, descend=(0, 1))

# ------------------------------------------------------------------ cou (k17 -> k22) avec collier rouge
b.plate("3022", BLACK, x=-1, z=0, k=17, w=2, d=2)
for k in range(18, 22):
    for z in (0, 1):
        c = RED if k == 19 else (BLACK if z == 0 else WHITE)
        b.fill(-1, z, [k], c)
        b.fill(0, z, [k], c)

# ------------------------------------------------------------------ tête (k22 -> k29), tournée vers l'avant
b.plate("3020", BLACK, x=-1, z=-3, k=22, w=2, d=4)            # mâchoire noire, posée sur le cou (z 0..2)
for z in range(-2, 2):                                        # crâne blanc
    for k in range(23, 26):
        b.fill(-1, z, [k], WHITE)
        b.fill(0, z, [k], WHITE)
b.fill(-1, -3, [23], BLACK)                                   # museau noir, court
b.fill(0, -3, [23], BLACK)
for x in (-1, 0):
    b.slope("54200", BLACK, x=x, z=-3, w=1, d=1, k=24, descend=(0, -1))   # nez arrondi
# oreilles : plaque 1x6 noire en travers (dépasse de 2 tenons de chaque côté)
b.plate("3666", BLACK, x=-3, z=0, k=26, w=6, d=1)
b.fill(-1, 1, [26], WHITE)
b.fill(0, 1, [26], WHITE)
b.fill(-1, -1, [26], WHITE)
b.fill(0, -1, [26], WHITE)
b.fill(-1, -2, [26], WHITE)
b.fill(0, -2, [26], WHITE)
# dessus de la tête : chanfrein blanc vers l'avant, plaque pour les cornes
b.slope("15068", WHITE, x=-1, z=-2, w=2, d=2, k=27, descend=(0, -1))
b.plate("3022", WHITE, x=-1, z=0, k=27, w=2, d=2)
for x in (-1, 0):                                             # cornes : cônes 1x1 gris
    b.part("4589", LBGRAY, cx=x + 0.5, cz=1.5, k=28)
b.tile("3069b", WHITE, x=-1, z=0, k=28, w=2, d=1)
# yeux : plaques rondes noires sur les côtés de la tête
for s_ in (-1, 1):
    b.rotated("6141", BLACK, cx=s_ * 1.3, cz=-1.5, kb=24.5, R=Rz(90 * s_))
# brin d'herbe dans la bouche : tuile verte qui dépasse sur le côté
b.tile("3069b", GREEN, x=0, z=-3, k=23, w=2, d=1)

if __name__ == "__main__":
    b.save()
