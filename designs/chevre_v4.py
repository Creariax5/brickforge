"""Chèvre v4 : d'après le rendu Gemini imgs/lego_chevre_v4/concept.jpeg, proportions MESURÉES sur l'image.

Étalon : les plaques 2x2 à tenons des flancs (~80 px par tenon).
- corps : ~9 tenons de long, ~12 plaques de haut (dos arrondi compris), ~2,8 tenons de large
  (cœur de 2 tenons + plaques montées sur le côté) : corps étroit et long, pas une vache ;
- pattes : 12 plaques (un peu plus que l'épaisseur du corps) ;
- tête grosse et haute sur un cou montant, bandeau noir sur les yeux, chanfrein blanc,
  oreilles noires larges, cornes, touffe d'herbe ; collier orange et gris ; queue haute.
Toutes les fixations sont de vrais emboîtements (tenons verticaux ou latéraux).

Repère : x = largeur (cœur de x -1 à 1), z = longueur (tête vers -z), k = hauteur en plaques.
Usage : python -m designs.chevre_v4
"""

from __future__ import annotations

from designs.kit import Build, Rx, Ry, Rz

WHITE, BLACK, ORANGE, LBGRAY, DBGRAY, GREEN, DTAN = 15, 0, 25, 71, 72, 2, 28

b = Build("chevre_v4")
b.use_bricks = True

# ------------------------------------------------------------------ pattes (k0 -> k12)
for x in (-1, 0):
    for z in (1, 7):
        cx, cz = x + 0.5, z + 0.5
        b.part("6141", BLACK, cx=cx, cz=cz, k=0)          # sabot
        b.part("6141", WHITE, cx=cx, cz=cz, k=1)          # bague blanche
        b.part("4589", BLACK, cx=cx, cz=cz, k=2)          # canon : cône noir
        b.part("6141", BLACK, cx=cx, cz=cz, k=5)          # genou / jarret noir
        b.part("3062b", WHITE, cx=cx, cz=cz, k=6)         # haut de patte blanc
        b.part("3062b", WHITE, cx=cx, cz=cz, k=9)

# ------------------------------------------------------------------ ventre (k12) et arrondi du dessous
b.plate("3034", WHITE, x=-1, z=0, k=12, w=2, d=8)
b.plate("3023", WHITE, x=-1, z=8, k=12, w=2, d=1)
b.slope("3660", WHITE, x=-1, z=3, w=2, d=2, k=9, descend=(0, -1))    # ventre arrondi entre les pattes

# ------------------------------------------------------------------ corps : 3 étages SNOT (k13 -> k22)
SEGS = [(0, 2), (2, 2), (4, 2), (6, 2), (8, 1)]          # (z, longueur) des briques à tenons latéraux
for k in (13, 16, 19):
    for z, L in SEGS:
        part = "11211" if L == 2 else "87087"
        col = BLACK if z == 0 else WHITE                  # poitrail noir
        b.rotated(part, col, cx=-0.6, cz=z + L / 2, kb=k, R=Ry(90))     # tenons latéraux vers -x
        b.rotated(part, col, cx=0.6, cz=z + L / 2, kb=k, R=Ry(-90))     # tenons latéraux vers +x
# flancs (côté visible sur le rendu = gauche) : poitrail noir, tache 2x2 noire en bas au milieu,
# bande noire en haut vers l'arrière, croupe blanche
LEFT = {13: [BLACK, WHITE, BLACK, WHITE, WHITE], 16: [BLACK, WHITE, BLACK, WHITE, WHITE],
        19: [BLACK, WHITE, WHITE, BLACK, WHITE]}
RIGHT = {13: [BLACK, WHITE, WHITE, BLACK, WHITE], 16: [BLACK, BLACK, WHITE, WHITE, WHITE],
         19: [BLACK, WHITE, WHITE, WHITE, WHITE]}
for k in (13, 16, 19):
    for i, (z, L) in enumerate(SEGS):
        part = "3023" if L == 2 else "3024"
        for side, cols in ((-1, LEFT), (1, RIGHT)):
            b.rotated(part, cols[k][i], cx=side * 1.3, cz=z + L / 2, kb=k + 0.5, R=Rz(90 * side) @ Ry(90))

# ------------------------------------------------------------------ dos (k22 -> k25)
b.plate("3020", BLACK, x=-1, z=0, k=22, w=2, d=4)        # garrot noir : porte le cou
b.plate("3022", WHITE, x=-1, z=4, k=22, w=2, d=2)
b.plate("3021", WHITE, x=-1, z=6, k=22, w=2, d=3)
b.slope("15068", BLACK, x=-1, z=2, w=2, d=2, k=23, descend=(0, -1))  # épaules noires arrondies
b.tile("3069b", BLACK, x=-1, z=4, k=23, w=2, d=1)        # tache noire sur le dos
b.tile("3069b", WHITE, x=-1, z=5, k=23, w=2, d=1)
b.slope("15068", WHITE, x=-1, z=6, w=2, d=2, k=23, descend=(0, 1))   # croupe arrondie
# queue haute : deux briques 1x1 sur la croupe, pente fromage au bout
b.part("3005", WHITE, cx=-0.5, cz=8.5, k=23)
b.part("3005", WHITE, cx=-0.5, cz=8.5, k=26)
b.slope("54200", WHITE, x=-1, z=8, w=1, d=1, k=29, descend=(0, 1))
b.tile("3070b", WHITE, x=0, z=8, k=23)

# ------------------------------------------------------------------ cou (k23 -> k29) et collier
for x in (-1, 0):
    b.rotated("87087", BLACK, cx=x + 0.5, cz=0.4, kb=23, R=Ry(0))       # tenon latéral vers l'avant
    b.rotated("6141", ORANGE, cx=x + 0.5, cz=-0.3, kb=24.25, R=Rx(90))  # perle orange
    b.rotated("85861", LBGRAY, cx=x + 0.5, cz=-0.7, kb=24.25, R=Rx(90)) # perle grise
    b.fill(x, 0, [26, 27, 28], WHITE)
    b.fill(x, 1, range(23, 29), WHITE)

# ------------------------------------------------------------------ tête (k29 -> k35)
b.plate("3020", WHITE, x=-1, z=-3, k=29, w=2, d=4)        # posée sur le cou (z 0..1)
b.part("32607", GREEN, cx=-0.5, cz=-2.5, k=28)             # herbe : tenon dans le dessous du museau
# bandeau noir sur les yeux : briques à tenon latéral + plaques 1x2 noires sur les côtés
for s_, x in ((-1, -1), (1, 0)):
    for z in (-2, -1):
        b.rotated("87087", BLACK, cx=x + 0.5 + s_ * 0.1, cz=z + 0.5, kb=30, R=Ry(-90 * s_))
    b.rotated("3023", BLACK, cx=s_ * 1.3, cz=-1, kb=30.5, R=Rz(90 * s_) @ Ry(90))
for x in (-1, 0):
    b.fill(x, -3, [30, 31, 32], WHITE)                     # museau blanc
    b.fill(x, 0, [30, 31, 32], WHITE)
b.plate("3666", BLACK, x=-3, z=0, k=33, w=6, d=1)          # oreilles noires larges
for x in (-1, 0):
    b.slope("11477", WHITE, x=x, z=-3, w=1, d=2, k=33, descend=(0, -1))   # chanfrein blanc
    b.slope("54200", WHITE, x=x, z=-1, w=1, d=1, k=33, descend=(0, -1))   # front
    b.part("85861", DBGRAY, cx=x + 0.5, cz=0.5, k=34)                     # cornes dans des tenons creux
    b.rotated("53451", DTAN, cx=x + 0.5, cz=0.5, kb=35, R=Rx(90))

if __name__ == "__main__":
    b.save()
