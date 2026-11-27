"""Chèvre v2 : d'après le concept Gemini (imgs/lego_chevre/concept.jpeg) et sa liste de pièces.

La notice de Gemini contient des incohérences (4 briques 1x2 en ligne ne font pas 6 tenons, etc.) :
on suit l'image et on reprend ses pièces quand elles sont réalistes.

- Corps : cœur de 2 tenons de large en briques à tenons latéraux (11211), flancs habillés de plaques
  montées sur le côté (SNOT) avec les taches noires ; dos en plaques, tuiles et pente courbe ; ventre arrondi.
- Pattes fines (de bas en haut) : sabot rond noir, plaque ronde blanche, cône noir, genou noir,
  deux briques rondes blanches.
- Cou blanc et noir, collier de plaques rondes orange et grises.
- Tête : chanfrein blanc en pentes courbes, joues noires sur le côté, oreilles noires à l'horizontale,
  cornes (53451) inclinées vers l'arrière, touffe d'herbe (32607) dans la bouche.
- Queue blanche relevée.

Repère : x = largeur (corps de x -1 à 1), z = longueur (tête vers -z), k = hauteur en plaques.
Usage : python -m designs.chevre_v2      (la version 1, conçue d'après la photo seule : designs/chevre_v1.py)
"""

from __future__ import annotations

from designs.kit import Build, Rx, Ry, Rz

WHITE, BLACK, ORANGE, LBGRAY, DBGRAY, GREEN, DTAN = 15, 0, 25, 71, 72, 2, 28

b = Build("chevre_v2")
b.use_bricks = True

# ------------------------------------------------------------------ pattes (k0 -> k12)
for x in (-1, 0):
    for z in (1, 6):
        cx, cz = x + 0.5, z + 0.5
        b.part("6141", BLACK, cx=cx, cz=cz, k=0)          # sabot
        b.part("6141", WHITE, cx=cx, cz=cz, k=1)          # pâturon blanc
        b.part("4589", BLACK, cx=cx, cz=cz, k=2)          # canon : cône noir
        b.part("6141", BLACK, cx=cx, cz=cz, k=5)          # genou
        b.part("3062b", WHITE, cx=cx, cz=cz, k=6)         # cuisse / avant-bras
        b.part("3062b", WHITE, cx=cx, cz=cz, k=9)

# ------------------------------------------------------------------ ventre (k12) et arrondi du dessous
b.plate("3034", WHITE, x=-1, z=0, k=12, w=2, d=8)         # plaque 2x8 posée sur les 4 pattes
b.slope("3660", WHITE, x=-1, z=2, w=2, d=2, k=9, descend=(0, -1))    # ventre arrondi entre les pattes
b.slope("3660", WHITE, x=-1, z=4, w=2, d=2, k=9, descend=(0, 1))

# ------------------------------------------------------------------ cœur du corps (k13 -> k19)
# deux étages de briques à tenons latéraux : côté gauche tenons vers -x, côté droit vers +x
for k in (13, 16):
    for z in range(0, 8, 2):
        b.rotated("11211", WHITE, cx=-0.6, cz=z + 1, kb=k, R=Ry(90))   # corps x -1..0, tenons latéraux jusqu à -1.2
        b.rotated("11211", WHITE, cx=0.6, cz=z + 1, kb=k, R=Ry(-90))

# flancs : plaques montées sur le côté (une rangée par étage), taches noires asymétriques
LEFT = {13: [BLACK, WHITE, BLACK, WHITE], 16: [BLACK, WHITE, BLACK, WHITE]}      # côté vu sur le concept
RIGHT = {13: [BLACK, BLACK, WHITE, WHITE], 16: [BLACK, WHITE, WHITE, BLACK]}
for k in (13, 16):
    for i, z in enumerate(range(0, 8, 2)):
        # tenons latéraux de la 11211 à 14 LDU du bas : centre de la plaque à k + 1,75 -> bas à k + 0,5
        b.rotated("3023", LEFT[k][i], cx=-1.3, cz=z + 1, kb=k + 0.5, R=Rz(-90) @ Ry(90))
        b.rotated("3023", RIGHT[k][i], cx=1.3, cz=z + 1, kb=k + 0.5, R=Rz(90) @ Ry(90))

# ------------------------------------------------------------------ dos (k19 -> k21)
b.plate("3021", BLACK, x=-1, z=-1, k=19, w=2, d=3)         # garrot noir : porte le cou et le poitrail
# poitrail noir : colonne suspendue sous le garrot, devant le corps, arrondie en bas
b.fill_column_range([(-1, -1), (0, -1)], 13, 19, BLACK)
b.fill_column_range([(-1, -1), (0, -1)], 12, 13, BLACK)
b.plate("3022", WHITE, x=-1, z=2, k=19, w=2, d=2)
b.plate("3022", WHITE, x=-1, z=4, k=19, w=2, d=2)
b.tile("3069b", WHITE, x=-1, z=2, k=20, w=2, d=1)
b.tile("3069b", BLACK, x=-1, z=3, k=20, w=2, d=1)         # tache noire sur le dos
b.tile("3069b", BLACK, x=-1, z=4, k=20, w=2, d=1)
b.tile("3069b", WHITE, x=-1, z=5, k=20, w=2, d=1)
b.plate("3022", WHITE, x=-1, z=6, k=19, w=2, d=2)          # croupe : plaque à tenons
b.slope("11477", WHITE, x=0, z=6, w=1, d=2, k=20, descend=(0, 1))    # arrondi de la croupe
b.tile("3070b", WHITE, x=-1, z=6, k=20)
# queue relevée : brique 1x1 sur un tenon de la croupe + pente fromage
b.part("3005", WHITE, cx=-0.5, cz=7.5, k=20)
b.slope("54200", WHITE, x=-1, z=7, w=1, d=1, k=23, descend=(0, 1))

# ------------------------------------------------------------------ cou (k20 -> k25)
for k in range(20, 25):
    for x in (-1, 0):
        b.fill(x, 0, [k], BLACK if k < 22 else WHITE)
        b.fill(x, 1, [k], WHITE)
# collier : deux briques 1x1 à tenon latéral (vers l'avant) dans le cou, plaques rondes emboîtées dessus
for x in (-1, 0):
    b.rotated("87087", WHITE, cx=x + 0.5, cz=0.4, kb=21, R=Ry(0))       # corps z 0..1, tenon latéral vers -z
    b.rotated("6141", ORANGE, cx=x + 0.5, cz=-0.3, kb=22.25, R=Rx(90))  # perle orange sur le tenon latéral
    b.rotated("85861", LBGRAY, cx=x + 0.5, cz=-0.7, kb=22.25, R=Rx(90)) # perle grise sur la perle orange

# ------------------------------------------------------------------ tête (k25 -> k31)
b.plate("3020", WHITE, x=-1, z=-3, k=25, w=2, d=4)         # posée sur le cou (z 0..1)
b.part("32607", GREEN, cx=-0.5, cz=-2.5, k=24)             # touffe d'herbe sous le museau
for k in range(26, 29):
    for z in range(-3, 1):
        for x in (-1, 0):
            b.fill(x, z, [k], WHITE)
for s_, x in ((-1, -1), (1, 0)):                         # joues : 2 briques 1x1 à tenon latéral par côté
    for z in (-2, -1):
        b.rotated("87087", WHITE, cx=x + 0.5 + s_ * 0.1, cz=z + 0.5, kb=26, R=Ry(-90 * s_))
    b.rotated("3023", BLACK, cx=s_ * 1.3, cz=-1, kb=26.5, R=Rz(90 * s_) @ Ry(90))     # plaque 1x2 noire
b.plate("3666", BLACK, x=-3, z=0, k=29, w=6, d=1)          # oreilles noires à l'horizontale
b.fill(-1, -1, [29], WHITE)
b.fill(0, -1, [29], WHITE)
for x in (-1, 0):
    b.slope("11477", WHITE, x=x, z=-3, w=1, d=2, k=29, descend=(0, -1))   # chanfrein blanc
    b.slope("54200", WHITE, x=x, z=-1, w=1, d=1, k=30, descend=(0, -1))   # front blanc
    b.part("85861", DBGRAY, cx=x + 0.5, cz=0.5, k=30)                     # plaque ronde à tenon creux
    b.rotated("53451", DTAN, cx=x + 0.5, cz=0.5, kb=31, R=Rx(90))          # corne : son tenon dans le tenon creux

if __name__ == "__main__":
    b.save()
