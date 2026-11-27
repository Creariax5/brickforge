---
title: Image → 3D → LEGO : un modèle pré-entraîné donne la forme
date: 2026-11-26
authors: Florian De Martini, Claude (Anthropic)
status: en cours
cover: /research/assets/11-cover.jpg
summary: Au lieu de deviner le volume à partir de 5 vues, on demande à un modèle image → 3D pré-entraîné (Hunyuan3D 2.1, sur le Mac Studio) de reconstruire l'objet en 3D à partir d'une seule image. Notre constructeur couche par couche le transforme ensuite en figurine LEGO montable.
tags: brickheadz, image-3d, hunyuan3d, construction
live: i3d
metrics: Donald (photo officielle) : volume 0,70 ; face juste 45 % ; 0 pièce qui vole ; ≈ 3 min 40 s par image sur le Mac
---

## Pourquoi
- **Gemini** sait imaginer une figurine, mais invente des pièces.
- **Notre constructeur** pose de vraies pièces, mais il a besoin d'une forme 3D. Celle qu'on déduisait des 5 vues était grossière.
- **Un modèle image → 3D pré-entraîné** apporte la « vision du monde » qui manquait. On en a discuté :
  - les modèles qui construisent sous contrainte, comme BrickGPT et LEGO-Maker ;
  - l'alignement par récompense, comme DSO sur TRELLIS ;
  - JEPA, qui ne génère rien et sert d'encodeur.

## Chaîne
1. **Image → 3D** : Hunyuan3D 2.1 (Tencent), version Mac, sur le Mac Studio. La forme prend environ 3 min, la texture environ 40 s. TRELLIS.2 attend l'accès à DINOv3, qui est protégé.
2. **3D → grille colorée** (`brickforge/from_mesh.py`) :
   - Recalage : axe de la tête, hauteur en plates, quart de tour choisi.
   - Échantillonnage dense de la surface : chaque point lit sa couleur dans la texture.
   - Couleurs ramenées à la palette des BrickHeadz, dans l'espace couleur Lab.
3. **Grille → LEGO** : constructeur couche par couche (note 09, étape 4), puis contrôle par le moteur de constructibilité.

**Vérification du convertisseur** : on lui a donné le vrai Donald exporté en maillage. La grille retrouvée colle à 91 % au volume officiel.

**Deux pièges corrigés** :
- La visière décalait le centrage. On centre maintenant sur la tête.
- La texture était lue à l'envers. Le sens des UV est vérifié : le visage passe de 23 % à 45 % de justesse.

## Premier résultat : Donald, depuis la photo officielle

| | Volume 3D | Face juste | Pièces | Montable |
|---|---|---|---|---|
| Couches, cible 3D du vrai modèle (borne haute) | 0,77 | 66 % | 128 | oui |
| Couches, cible fiche (5 vues) | 0,73 | 68 % | 91 | oui |
| **Hunyuan3D, une seule photo** | **0,70** | **45 %** | 240 | oui |

**Bilan honnête.**
- La forme sortie d'**une seule photo** est presque aussi bonne que celle déduite de 5 vues parfaites. Le bec, le chapeau et le nœud sont là.
- Le visage est moins juste : les yeux sortent gris au lieu de noirs, l'orange des pieds déborde.
- Trop de pièces (240) : le maillage a des bosses. Il faudra le lisser avant la construction.
- **Suite** : les images Gemini (concepts sans modèle officiel), puis lisser le maillage et améliorer les couleurs.

## Remplissage optimisé (forme seule) : `brickforge/fill.py`

**Idée.** On oublie les couleurs et on cherche les pièces qui remplissent le mieux le volume 3D, sans jamais faire voler une pièce.

**Méthode.**
- **Grille 4 fois plus fine** que pour les couches : ½ tenon × ½ plate.
- **Catalogue** : plaques, briques, tuiles, pentes, pentes courbes, pièces rondes, plaques « jumper » et briques à tenons sur le côté. Cela fait 71 pièces et 166 combinaisons pièce × orientation, avec pour chacune son volume (dessous fermé) et ses accroches verticales.
- **Construction plate par plate**, en plusieurs passes :
  - Toutes les positions de toutes les pièces sont notées d'un coup par corrélation (FFT).
  - Score : cases remplies − λ × cases qui débordent, sans aucun chevauchement.
  - Chaque pièce doit être posée sur un tenon libre, ou accrochée sous un creux libre.
  - λ diminue à chaque passe pour boucher les trous.
- **Recherche** : 8 réglages en parallèle (λ, part minimale à l'intérieur). On garde le meilleur.

**Contrôles.**
- Sur une boîte simple, le remplissage est parfait (100 %).
- Sur le vrai Donald (cible exacte), on atteint face 86 %, profil 90 %, dessus 78 %.

**Donald de Hunyuan3D** (cible = son maillage) :

| Face | Profil | Dessus | Volume | Pièces | Volent | Collisions |
|---|---|---|---|---|---|---|
| 89 % | 86 % | 86 % | 78 % | 57 | 0 | 0 |

**Pourquoi on plafonne sous 90 %.** La différence est une bordure d'un demi-tenon tout autour. Les vraies BrickHeadz font 6,4 tenons de large grâce à des tuiles fixées **sur les côtés**, par les briques à tenons latéraux. L'optimiseur n'accroche pour l'instant que vers le haut et vers le bas. Les pièces inclinées par une charnière (visière) ne sont pas encore gérées non plus.

**Suite.**
1. Accroches latérales : pièces tournées de 90° fixées sur les tenons de côté.
2. Pièces spéciales des BrickHeadz, filtrées par famille.
3. Couleurs.

### Avec les accroches latérales
- Les briques à tenons sur le côté (22885, 87087, 99780…) entrent dans le remplissage vertical. Elles **réservent** les cases devant leurs tenons, pour qu'aucune autre pièce n'y bute, et reçoivent un bonus quand ces cases font partie de la forme.
- Ensuite, des plaques, tuiles et pentes **tournées de 90°** se fixent sur ces tenons libres, en deux tours.
- Cela a corrigé un vrai défaut : avant, des 22885 posées contre une voisine enfonçaient leurs tenons dedans (6 collisions).

Résultats sur le **Donald de Hunyuan3D** (8 réglages en parallèle, environ 75 s) :

| | Face | Profil | Dessus | Volume | Pièces | Volent | Collisions |
|---|---|---|---|---|---|---|---|
| Vertical seul | 89 % | 86 % | 86 % | 78 % | 57 | 0 | 0 |
| **+ accroches latérales** | **91 %** | 88 % | 80 % | 76 % | 79 | 0 | 0 |

Sur le vrai Donald comme cible, on obtient face 89,5 %, profil 91 % et dessus 76 %.

**À améliorer.**
- Le dessus reste le point faible : visière, bords de la tête.
- Le choix du meilleur réglage se fait encore sur une moyenne : il faudrait viser « les trois silhouettes ≥ 90 % ».
