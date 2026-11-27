---
title: Changer de méthode : partir de la BrickHeadz la plus proche
date: 2026-11-27
authors: Florian De Martini, Claude (Anthropic)
status: en cours
cover: /research/assets/15-cover.jpg
summary: Les plafonds mesurés montrent qu’aucune construction « brique par brique » ne dépasse ~89 % de volume. Partir de la BrickHeadz officielle la plus proche puis la retoucher fait mieux sur la plupart des formes (3 formes sur 12 au-dessus de 95 %). Et Hunyuan3D contre TRELLIS.2, depuis la photo et depuis 3 vues.
tags: brickheadz, méthode, mesure, hunyuan, trellis
metrics: plus proche + retouches = 85,9 % ; ancienne méthode = 78,6 % ; formes ≥ 95 % = 3 / 12 ; Hunyuan (photo) = 92,3 %
---

## En bref
- **Mesure unique** : le volume commun entre la vraie forme de notre construction (pièces LDraw, tenons compris) et la vraie forme de la BrickHeadz visée. Une case de ½ tenon × ½ plate compte pleine si plus de la moitié de son volume l'est (note 14).
- **L'ancienne méthode est au bout de ce qu'elle peut faire.** Même découpée parfaitement en cubes de 1 tenon × 1 plate, la vraie forme ne fait que 85 % ; nous sommes à 79–82 %.
- **Nouvelle méthode : partir de la BrickHeadz officielle la plus proche et la retoucher.** Sur les 12 formes de test, on passe en moyenne de **78,6 % à 85,9 %**, et 3 formes dépassent **95 %**. Mais pour les 3 formes les plus originales (40466, 40270, 40412), aucune officielle n'est assez proche, et l'ancienne méthode reste meilleure. Rien ne vole, aucune collision.
- **Limite trouvée** : le volume ne « voit » pas assez ce qui fait reconnaître un personnage. Pour Donald, l'officielle la plus proche en volume est Mr. Indestructible : bonne silhouette, mais ni bec ni chapeau.

## 1. Les plafonds : ce qu'une méthode peut espérer au mieux
On découpe la **vraie forme** de chaque officielle à différentes résolutions, sans aucune contrainte d'assemblage, et on mesure le volume commun. Aucune méthode de cette résolution ne peut faire mieux.

| Résolution de la construction | Donald | Moyenne des 101 | ≥ 95 % |
|---|---|---|---|
| Cubes de 1 tenon × 1 plate (grille fixe) | 85,6 % | 85,4 % | 0 |
| idem, avec un décalage d'½ tenon permis à chaque plate | 89,3 % | 87,5 % | 0 |
| **½ tenon × 1 plate** (plaques posées sur le côté, comme les vraies BrickHeadz) | **94,8 %** | **94,9 %** | 54 |

Viser 95 % demande donc une finesse d'**½ tenon horizontalement** : c'est ce que les vraies BrickHeadz obtiennent avec leurs faces en plaques fixées sur le côté (SNOT).

## 2. Ce qu'on a essayé pour construire de zéro (sur la vraie Donald)
| Essai | Volume | Remarques |
|---|---|---|
| Glouton, ancienne bibliothèque (71 sortes de pièces) | 78,8 % | point de départ |
| Glouton, bibliothèque étendue (138 sortes : quarts de rond, plaques rondes, ailes, pentes…) | 78,9 % | les pièces sont utilisées, mais le glouton ne sait pas quand elles valent le coup ; moyenne des 12 formes de test 78,5 → 78,6 % |
| Recherche très large (faisceau de 24, 8 essais) | 82,2 % | 13 min par essai |
| « Cœur + faces » : cœur en retrait, briques à tenons latéraux, plaques sur les côtés | 79,2 % | les faces posées une à une créent des collisions ; une vraie face de BrickHeadz est **conçue d'un bloc** (équerres, panneaux alignés) |

L'entraînement du réseau (note 13) a été **arrêté** : il apprenait sur cette méthode plafonnée, et saturait la mémoire du Mac.

## 3. Nouvelle méthode : partir du plus proche, puis retoucher
1. **Trouver** l'officielle dont la vraie forme a le plus grand volume commun avec la cible, en essayant de petits décalages (½ tenon). Pour un test honnête, **les figurines du même set que la cible sont exclues**.
2. **Garder** son squelette : équerres, faces en plaques, tout est déjà constructible.
3. **Enlever** les pièces qui sont surtout hors de la cible (si ça ne fait voler aucune pièce).
4. **Ajouter** les pièces manquantes avec notre optimiseur, accrochées sur les tenons libres de la figurine, puis vérifier avec le moteur (rien ne vole, pas de collision).

On essaie les 3 plus proches et λ = 2 ou 3, et on garde le meilleur résultat.

| Forme de test | Ancienne méthode (glouton) | Officielle la plus proche | **Retouchée** | Pièces enlevées / ajoutées |
|---|---|---|---|---|
| 41612 | 81,2 % | 97,7 % | **98,1 %** | −2 / +0 |
| 41587 | 81,3 % | 92,1 % | **95,4 %** | −4 / +2 |
| 41630 | 82,0 % | 93,6 % | **95,3 %** | −3 / +2 |
| 41618 | 82,6 % | 91,5 % | **94,8 %** | −12 / +2 |
| 41490 | 85,6 % | 88,0 % | **92,0 %** | −3 / +10 |
| 41487 | 80,2 % | 91,4 % | **91,9 %** | −6 / +0 (et 8 → 2 pièces qui volent) |
| 41602 | 80,8 % | 87,2 % | **89,6 %** | −9 / +0 |
| **Donald (40377)** | 78,9 % | 87,9 % | **88,9 %** | −2 / +2 |
| 40353 | 70,9 % | 76,7 % | **79,3 %** | −4 / +2 |
| 40412 | 80,2 % | 75,3 % | **77,0 %** | −8 / +9 |
| 40466 | 75,1 % | 43,7 % | **69,3 %** | −22 / +14 |
| 40270 | 64,5 % | 55,7 % | **59,1 %** | −25 / +1 |
| **Moyenne (12)** | **78,6 %** | **81,7 %** | **85,9 %** | |

Sur 20 autres officielles évaluées avant l'échantillon, même tendance : chaque retouche fait gagner de 1 à 5 points (par exemple 95,6 → 96,8 %), sans pièce qui vole.

**Les trois figurines côte à côte** : la vraie LEGO visée, l'officielle de départ (pièces enlevées en rouge transparent), et le résultat retouché (pièces ajoutées en orange). Le menu en haut permet de passer d'une figurine à l'autre. [Ouvrir en grand](/research/assets/15-compare.html)

<iframe src="/research/assets/15-compare.html" style="width:100%;height:560px;border:1px solid var(--line);border-radius:10px" loading="lazy" title="Vraie LEGO, plus proche officielle, retouchée"></iframe>

**Quand ça ne marche pas** : 40466, 40270 et 40412 n'ont pas de « sœur » proche parmi les officielles (43,7 %, 55,7 % et 75,3 % au départ). Les retouches remontent beaucoup (jusqu'à +26 points) mais restent sous l'ancienne méthode. La bonne règle est donc de garder **le meilleur des deux** : partir du plus proche s'il est assez ressemblant, sinon construire de zéro. Avec cette règle, la moyenne des 12 passe à **87,1 %**.

### Ce que montre Donald : la mesure ne suffit pas
L'officielle la plus proche de Donald en volume est **Mr. Indestructible** (87,9 %), et les retouches n'ajoutent pas de bec. La silhouette générale est bonne, mais **le personnage n'est pas reconnaissable** : le bec, le chapeau et les couleurs pèsent peu en volume, mais ce sont eux qui font Donald. Il faudra :
- choisir le point de départ aussi par **ressemblance visuelle** (couleurs, image), pas seulement par volume ;
- donner plus de poids aux **zones caractéristiques** (bec, oreilles, accessoires) dans la mesure ;
- recolorer les pièces gardées avec les couleurs de la cible.

## 4. Maillages 3D : Hunyuan3D 2.1 contre TRELLIS.2
Même photo de la vraie Donald, et même procédure de recalage pour les deux maillages (orientation, miroir, échelle par axe, petite rotation, décalage ; plusieurs points de départ). On mesure le volume commun avec la vraie Donald.

| Depuis la photo | Volume | Silhouettes face / profil / dessus | Temps sur le Mac |
|---|---|---|---|
| **Hunyuan3D 2.1** | **92,3 %** | 93,0 / 94,2 / 96,0 % | ~3 min 40 s |
| TRELLIS.2 (4B, 512) | 89,4 % | 90,6 / 93,1 / 94,8 % | ~5 min 20 s (+ 20 min de texture sans accélération Metal) |

À l'œil, **TRELLIS.2 est nettement plus propre** : vraies arêtes de briques, joints, tenons, couleurs franches. Mais il est **moins juste en volume**, surtout sur les mains, la mèche du chapeau et les proportions. Pour notre usage, Hunyuan reste devant.

Deux pièges réglés : TRELLIS.2 enregistre la hauteur sur l'axe Z (au lieu de Y), et sa texture se lit dans l'autre sens.

<iframe src="/research/assets/15-meshes.html" style="width:100%;height:520px;border:1px solid var(--line);border-radius:10px" loading="lazy" title="Hunyuan3D 2.1 et TRELLIS.2 côte à côte"></iframe>

[Ouvrir en grand](/research/assets/15-meshes.html)

### Avec 3 vues au lieu d'une photo
Ni Hunyuan3D 2.1 ni TRELLIS.2 n'acceptent plusieurs images : chacun ne prend qu'une vue. Hunyuan3D‑2mv (une autre version) prend jusqu'à 4 vues, mais à angles fixes (face, gauche, dos, droite). On essaie donc d'abord **chaque vue seule** : face 3/4, dos 3/4, contre-plongée. Ce sont des rendus de la vraie Donald, donc des vues parfaites.

| Vue | Hunyuan3D 2.1 | TRELLIS.2 |
|---|---|---|
| Face 3/4 | 90,0 % | 88,6 % |
| Dos 3/4 | 89,4 % | 90,2 % |
| Contre-plongée | 89,6 % | 88,1 % |
| *rappel : la photo d'origine* | *92,3 %* | *89,4 %* |

Une seule vue de 3/4, même parfaite, fait **moins bien que la photo** (qui montre la figurine de face) : la face cachée est inventée. Les deux modèles se valent sur ces vues (88 à 90 %). Combiner les vues demanderait un mode multi-images, que ni l'un ni l'autre n'a dans la version installée.

## 5. Suite
1. Choisir le point de départ par **volume + ressemblance visuelle**, puis recolorer.
2. Des retouches plus franches : remplacer des **blocs entiers** (tête, bec, chapeau) par ceux d'autres officielles, pas seulement pièce par pièce.
3. Appliquer la méthode aux **maillages Hunyuan** (photo → maillage → officielle la plus proche → retouches), puis mesurer contre la vraie LEGO.
4. Le réseau (note 13) apprendra les retouches plutôt que la construction complète.

## Fichiers
- Méthode : `brickforge/retrieve_edit.py` ; recalage des maillages : `brickforge/mesh_fit.py`.
- Résultats : `data/brickheadz/retrieve_edit_sample.json` (échantillon), `retrieve_edit_part1.json` (20 premières officielles).
- Vues 3D : `research/assets/15-compare.html`, `15-meshes.html`.
