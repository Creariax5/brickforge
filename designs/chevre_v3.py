"""Chèvre v3 : les proportions de la v1 (d'après la photo) avec les détails de la v2 (concept Gemini).

- Dimensions v1 : corps 4 x 8 tenons, pattes de 9 plaques, tête à 2 tenons de large au-dessus d'un cou court.
- Détails v2 : flancs montés sur le côté (briques 11211 + plaques 1x2), pattes en cônes et plaques rondes,
  collier de perles orange et grises, cornes 53451 dans des plaques à tenon creux, herbe 32607,
  yeux sur des briques à tenon latéral.
- Couleurs de la photo : avant et pattes avant noirs, pattes arrière blanches aux sabots noirs.
Toutes les fixations sont de vrais emboîtements (tenons verticaux ou latéraux).

Repère : x = largeur (corps de x -2 à 2), z = longueur (tête vers -z), k = hauteur en plaques.
Usage : python -m designs.chevre_v3
"""

from __future__ import annotations

from designs.kit import Build, Rx, Ry, Rz

WHITE, BLACK, ORANGE, LBGRAY, DBGRAY, GREEN, DTAN = 15, 0, 25, 71, 72, 2, 28

b = Build("chevre_v3")
b.use_bricks = True

# ------------------------------------------------------------------ pattes (k0 -> k9)
for x in (-2, 1):
    for z in (1, 6):
        cx, cz = x + 0.5, z + 0.5
        front = z == 1
        band = (x == 1 and not front)                      # bande noire sur une patte arrière (photo)
        upper = BLACK if front else WHITE
        b.part("6141", BLACK, cx=cx, cz=cz, k=0)                                   # sabot
        b.part("6141", BLACK if front else WHITE, cx=cx, cz=cz, k=1)              # pâturon
        b.part("4589", BLACK if (front or band) else WHITE, cx=cx, cz=cz, k=2)    # canon (cône)
        b.part("6141", upper, cx=cx, cz=cz, k=5)                                   # genou
        b.part("3062b", upper, cx=cx, cz=cz, k=6)                                  # cuisse

# ------------------------------------------------------------------ corps (k9 -> k18)
b.plate("3035", WHITE, x=-2, z=0, k=9, w=4, d=8)          # ventre : plaque 4x8 sur les 4 pattes
# deux étages : colonnes extérieures en briques à tenons latéraux, intérieur rempli
for k in (10, 13):
    for z in range(0, 8, 2):
        b.rotated("11211", BLACK if z == 0 else WHITE, cx=-1.6, cz=z + 1, kb=k, R=Ry(90))    # x -2..-1, tenons vers -x
        b.rotated("11211", BLACK if z == 0 else WHITE, cx=1.6, cz=z + 1, kb=k, R=Ry(-90))    # x 1..2, tenons vers +x
    for z in range(0, 8):
        b.fill(-1, z, range(k, k + 3), BLACK if z == 0 else WHITE)          # avant noir (poitrail)
        b.fill(0, z, range(k, k + 3), BLACK if z == 0 else WHITE)
# flancs : plaques 1x2 sur les tenons latéraux (14 LDU du bas de la brique -> bas de la plaque à k + 0,5)
LEFT = {10: [BLACK, BLACK, WHITE, WHITE], 13: [BLACK, BLACK, WHITE, WHITE]}
RIGHT = {10: [BLACK, WHITE, BLACK, WHITE], 13: [BLACK, WHITE, BLACK, BLACK]}
for k in (10, 13):
    for i, z in enumerate(range(0, 8, 2)):
        b.rotated("3023", LEFT[k][i], cx=-2.3, cz=z + 1, kb=k + 0.5, R=Rz(-90) @ Ry(90))
        b.rotated("3023", RIGHT[k][i], cx=2.3, cz=z + 1, kb=k + 0.5, R=Rz(90) @ Ry(90))
# dos arrondi : pentes 1x2 sur les bords, plaques et tuiles au centre
for z in range(0, 8, 2):
    for xe, d in ((-2, -1), (1, 1)):
        c = BLACK if z == 0 or (xe == 1 and z == 6) else WHITE
        b.slope("85984", c, x=xe, z=z, w=1, d=2, k=16, descend=(d, 0))
for z in range(0, 8):
    b.fill(-1, z, [16], WHITE)
    b.fill(0, z, [16], WHITE)
b.tile("3068b", WHITE, x=-1, z=2, k=17, w=2, d=2)
b.tile("3068b", BLACK, x=-1, z=4, k=17, w=2, d=2)         # tache noire sur le dos

# ------------------------------------------------------------------ queue relevée
b.plate("3022", WHITE, x=-1, z=6, k=17, w=2, d=2)
b.part("3062b", WHITE, cx=-0.5, cz=7.5, k=18)
b.slope("54200", WHITE, x=-1, z=7, w=1, d=1, k=21, descend=(0, 1))

# ------------------------------------------------------------------ cou (k17 -> k22) et collier
b.plate("3022", BLACK, x=-1, z=0, k=17, w=2, d=2)
for x in (-1, 0):
    b.rotated("87087", BLACK, cx=x + 0.5, cz=0.4, kb=18, R=Ry(0))       # tenon latéral vers l'avant
    b.rotated("6141", ORANGE, cx=x + 0.5, cz=-0.3, kb=19.25, R=Rx(90))  # perle orange
    b.rotated("85861", LBGRAY, cx=x + 0.5, cz=-0.7, kb=19.25, R=Rx(90)) # perle grise
    b.fill(x, 0, [21], BLACK)
    b.fill(x, 1, [18, 19, 20, 21], WHITE)

# ------------------------------------------------------------------ tête (k22 -> k29)
b.plate("3020", BLACK, x=-1, z=-3, k=22, w=2, d=4)         # mâchoire noire, posée sur le cou
b.part("32607", GREEN, cx=-0.5, cz=-2.5, k=21)             # herbe : tenon dans le dessous de la mâchoire
for s_, x in ((-1, -1), (1, 0)):                           # yeux sur des briques à tenon latéral
    b.rotated("87087", WHITE, cx=x + 0.5 + s_ * 0.1, cz=-0.5, kb=23, R=Ry(-90 * s_))
    b.rotated("6141", BLACK, cx=s_ * 1.3, cz=-0.5, kb=23.5, R=Rz(90 * s_))
for z in (-2, 0):
    for x in (-1, 0):
        b.fill(x, z, [23, 24, 25], WHITE)
for x in (-1, 0):
    b.fill(x, 1, [23, 24, 25], WHITE)
b.fill(-1, -3, [23], BLACK)                                # museau noir, court
b.fill(0, -3, [23], BLACK)
for x in (-1, 0):
    b.slope("54200", BLACK, x=x, z=-3, w=1, d=1, k=24, descend=(0, -1))
b.plate("3666", BLACK, x=-3, z=0, k=26, w=6, d=1)          # oreilles noires à l'horizontale
for z in (1, -1, -2):
    b.fill(-1, z, [26], WHITE)
    b.fill(0, z, [26], WHITE)
b.slope("15068", WHITE, x=-1, z=-2, w=2, d=2, k=27, descend=(0, -1))   # chanfrein blanc
b.plate("3022", WHITE, x=-1, z=0, k=27, w=2, d=2)
for x in (-1, 0):                                          # cornes plantées dans des tenons creux
    b.part("85861", DBGRAY, cx=x + 0.5, cz=0.5, k=28)
    b.rotated("53451", DTAN, cx=x + 0.5, cz=0.5, kb=29, R=Rx(90))
b.tile("3069b", WHITE, x=-1, z=1, k=28, w=2, d=1)

if __name__ == "__main__":
    b.save()
