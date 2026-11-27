---
title: Veille : OurBricks et données de vrais modèles
date: 2026-11-25
authors: Florian DEMARTINI, Claude (Anthropic)
status: en cours
cover: /research/assets/08-cover.jpg
summary: Comment fonctionne un concurrent qui fait des maisons en briques, et où trouver de vrais modèles LEGO avec leur ordre de montage pour entraîner nos modèles.
tags: veille, données
metrics: OMR LDraw=1 472 sets officiels ; StableText2Brick=47 000 structures ; OurBricks=99 à 699 €
---

## OurBricks (ourbricks.eu)
Petite entreprise belge (Gand, 2024). Une photo de façade ou une adresse (Street View) devient un kit de briques **compatibles, sans marque**.

- **Méthode annoncée** : le logiciel, « avec l'aide de l'IA », produit un modèle 3D en briques, puis **une personne vérifie chaque modèle** (proportions, détails, constructibilité). Modèle livré en 24 h, retouches gratuites, kit fabriqué à la commande, livré en 3 à 4 semaines. Notice en ligne, étape par étape, en 3D.
- **Gamme** : Mini 99 € (250 à 300 pièces), Façade 179 €, Complet 349 €, Maxi 699 € (environ 3 500 pièces).
- **Limites** : maisons, immeubles, fermes. **Pas d'animaux « (pour l'instant) »**, ni de personnes, ni de voitures.

Ce qu'on en déduit (le site ne le dit pas) :
- Une façade est presque plane et rectiligne : une grille de briques s'y aligne directement.
- Le domaine est fermé : on détecte fenêtres, portes et toit, puis on pose des modules déjà conçus.
- L'humain corrige le reste, sans doute dans un éditeur du type Studio.

**Leçons pour Brick Forge**
- Un humain dans la boucle est un modèle viable : notre assembleur et notre bac à sable jouent ce rôle.
- Restreindre le domaine paie. Pour nous, l'équivalent serait une **bibliothèque de modules d'animaux** validés (pattes, têtes, carapaces, oreilles), assemblés et mis à l'échelle par le générateur.
- Les briques compatibles règlent le coût de fabrication.
- Les animaux (courbes, SNOT, rotules) sont le créneau qu'ils évitent.

## Sources de vrais modèles

| Source | Contenu | Format | Intérêt pour nous |
|---|---|---|---|
| [LDraw OMR](https://library.ldraw.org/omr) | **1 472 sets officiels LEGO** remodélisés par la communauté | .mpd LDraw avec les `0 STEP` de la notice | **Le meilleur** : notre format natif, vrais modèles, ordre de montage fourni |
| [Rebrickable](https://rebrickable.com/downloads/) | Inventaires de presque tous les sets (pièces, couleurs), plus des MOC | CSV mensuels (sets, inventories, inventory_parts…) | Statistiques : quelles pièces les designers LEGO utilisent vraiment, et ensemble |
| [StableText2Brick](https://huggingface.co/datasets/cmu-gil/StableText2Lego) (BrickGPT, CMU, ICCV 2025) | 47 000 structures avec légende, labels de stabilité | Texte : briques et coordonnées | Briques simples seulement (formes ShapeNet voxelisées), mais un LLM génère brique par brique |
| [MEPNet](https://cs.stanford.edu/~rcwang/projects/lego_manual) (Stanford, ECCV 2022) | Notices synthétiques, image de l'étape → pièces et poses | Code et données | Lire une notice, l'inverse de notre problème |
| [LTRON / InstructioNet](https://arxiv.org/abs/2410.01111) | Simulateur LEGO, données construites sur l'OMR | LDraw | Démonter puis remonter, générer des étapes |
| [LEGO-Puzzles](https://arxiv.org/abs/2503.19990) | Fichiers de MOC open source avec étapes | LDraw / Studio | Banc d'essai du raisonnement spatial |
| [Notices LEGO.com](https://www.lego.com/service/buildinginstructions) | PDF gratuits de presque tous les sets depuis environ 2006 | PDF (images) | À lire seulement : pas d'API, droits LEGO, et l'OMR fournit déjà la 3D avec les étapes |

### Pourquoi l'OMR plutôt que les PDF
Un PDF n'est qu'une suite d'images : il faudrait d'abord reconstruire le modèle 3D, ce qui est exactement le problème qu'on cherche à résoudre. L'OMR donne directement le modèle exact, pièce par pièce, **dans l'ordre de la notice**.

Avec notre moteur de rendu, chaque set fournit :
- des vues photo, face, profil, dessus… **avec la vérité terrain exacte**, pour entraîner le détecteur sur de vrais assemblages plutôt que sur des scènes aléatoires ;
- des séquences d'étapes réelles, pour apprendre à un générateur à construire comme un designer LEGO ;
- des **sous-modèles réutilisables** (pattes, têtes, roues, toits) : la matière première de la bibliothèque de modules.

Limite : l'OMR contient surtout des véhicules et des bâtiments, avec peu d'animaux. Les animaux viendront surtout des sets Creator 3-en-1, BrickHeadz et des MOC.

## Premier import : 31088 Les créatures des fonds marins (2019)
Simba (43247, 2021) n'est pas dans l'OMR. Pour trouver un autre set, j'ai indexé les 1 471 sets du catalogue (59 pages, `omr_index.tsv`). L'animal récent le mieux construit est le Creator 3-en-1 **31088** : requin, baudroie, calamar, baleine.

- `brickforge/omr.py` lit le `.mpd`, aplatit les sous-modèles et garde pour chaque pièce **l'étape de la notice** (`step`) et **son sous-modèle** (`sub`). Les pièces embarquées dans le `.mpd` sont écrites dans `data/ldraw/omr_parts`.
- Résultat pour le requin : **230 pièces, exactement le compte officiel du set**, 104 étapes et 8 sous-modèles. Toutes les géométries sont trouvées. Les trois autres modèles comptent 135 à 139 pièces chacun.
- Les quatre sujets s'appellent `lego_omr_31088_*`. Le requin a la photo officielle du set (Rebrickable) comme vue de référence. L'assembleur affiche une **notice pas à pas** : curseur, étape précédente ou suivante, pièces de l'étape en surbrillance.

## Explorateur de sets (`#/explorateur`)
Les 1 472 sets de l'OMR sont consultables dans l'app :
- **Catalogue** : photo de la boîte (Rebrickable, réduite et mise en cache), recherche, thème, années, tri (numéro, récent, ancien, nom, nombre de modèles, nombre de pièces), filtres « Animaux » et « Déjà téléchargés ».
- **Fiche d'un set** : le `.mpd` est téléchargé à la demande dans `data/omr/<num>/`. On y trouve la vue 3D (une géométrie fusionnée par étape, rapide même sur un gros set), la notice (curseur, flèches, lecture automatique, étape en cours en surbrillance), les modèles alternatifs en onglets, les statistiques, les couleurs, les pièces les plus utilisées, un bouton « Ouvrir comme sujet » et le téléchargement du `.mpd`.
- Côté serveur : `app/explorer.py`, plus `/api/parts-batch` (géométries groupées) et la compression gzip.

## Catalogue complet : inventaires Rebrickable (25/11/2026)

- Source : exports CSV publics de Rebrickable (`data/rebrickable/*.csv.gz`, ~17 Mo). Ils sont convertis en `data/rebrickable/rb.sqlite` par `python -m brickforge.rebrickable` (12 s).
- **20 220 sets** avec au moins une pièce, dont **5 657 depuis 2020** (Simba 43247 : 1 445 pièces, 197 références). Les 1 472 sets OMR gardent la 3D et la notice ; les autres n'ont que l'**inventaire de la boîte** : pièce, couleur, quantité, photo, pièces de rechange et minifigs. Il n'y a ni positions ni étapes.
- Explorateur : badge « 3D », filtre « 3D + notice », fiche « Inventaire officiel » avec un export CSV.
- Usage prévu : apprendre la composition réelle des modèles (quelles pièces, combien, quelles couleurs) selon la taille et le sujet. Exemple : 549 sets d'animaux entre 30 et 120 pièces.
- Limites : les couleurs Rebrickable ≠ les codes LDraw, il faudra une table de correspondance. Les sous-sets imbriqués (`inventory_sets`) ne sont pas encore inclus.

## Sets du forum LDraw hors OMR (26/11/2026)

- Le forum « Official Models » (forums.ldraw.org, 397 fils) contient 3 502 liens de modèles. **794 sets** n'y sont pas encore dans l'OMR, surtout récents.
- **Les pièces jointes du forum exigent un compte**, donc seuls les liens publics sont récupérés (opcode.eu.org, Brickshelf, Bricksafe de Philo). Cela donne 61 sets candidats et **60 importés** (70 modèles), dont 45 sortis depuis 2020 : Neuschwanstein 2025, Paris 2026, Medieval Dragon 31161 en 3-en-1, Friendly Snails, Polar Bears, Easter Bunny… Seuls 4 ont des pièces inconnues de notre bibliothèque.
- Code : `python -m brickforge.ldforum threads.json`. Fichiers dans `data/omr/<num>/`, index dans `data/omr/forum_index.json`. Dans l'explorateur, ils ont le badge 3D et un lien vers le fil du forum.
- Eurobricks (« Official LEGO sets made in LDraw ») est derrière un anti-robots Cloudflare : écarté.
- Les ~730 sets restants deviennent accessibles avec un compte du forum (téléchargement manuel), ou automatiquement quand l'admin les fait entrer dans l'OMR. Il suffira alors de relancer l'import de l'OMR.
