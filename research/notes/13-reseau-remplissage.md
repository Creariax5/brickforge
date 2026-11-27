---
title: Un réseau qui apprend à remplir
date: 2026-11-26
authors: Florian De Martini, Claude (Anthropic)
status: en cours
cover: /research/assets/13-cover.png
summary: Un petit réseau 3D apprend dans quel ordre poser les pièces pour coller au mieux à la forme (itération d'expert, façon AlphaZero simplifié). Calcul sur le Mac Studio, suivi en direct ici.
tags: brickheadz, optimisation, apprentissage, direct
live: train-fill
metrics: objectif = 95 % de volume (vraie LEGO) ; glouton sur Donald = 78,8 % ; données = 90 BrickHeadz officielles
---

## L'idée
Le remplisseur (note 12) monte plate par plate. À chaque plate, il pose **toutes** les pièces qui rentrent sans chevaucher. La seule vraie décision est donc **l'ordre dans lequel il les essaie**, parce qu'une pièce posée en bloque d'autres. L'heuristique trie par « gain » (cases justes − λ × débord). La recherche en faisceau a montré que l'ordre compte : selon le hasard, la silhouette du dessus allait de 73 % à 89 %.

Le réseau remplace ce tri. Pour chaque pose possible, il regarde un cube de 16 × 8 × 16 cases autour de la pièce : la forme visée, ce qui est déjà construit, les tenons libres, la pièce elle-même et les cases encore vides. Il voit aussi quelle pièce c'est et son gain, et il rend une note. On trie par cette note.

## Version 2 : vue globale et tête de valeur

- **La vue globale.** Toute la forme est réduite par 4 (13 × 23 × 13 cases), avec trois calques : la forme visée, ce qui est déjà construit et la plate en cours. Trois convolutions 3D la résument en 64 nombres. Chaque pose candidate reçoit ce résumé avec sa position dans la figurine. Le réseau peut ainsi savoir « je suis au bord de la tête », et plus seulement « il y a de la forme à côté ».
- **La tête de valeur.** À partir de ce même résumé, elle prédit la pire silhouette finale d'un état à moitié construit. Elle apprend sur toutes les constructions finales de chaque faisceau, bonnes et mauvaises (erreur quadratique).
- **Son rôle dans le faisceau.** Si elle départage correctement deux états au moins 60 % du temps sur les formes de test, elle choisit la moitié des états gardés. L'autre moitié reste choisie par la note faite main, pour éviter qu'une valeur encore naïve ne gâche la recherche. Sinon, elle n'est pas utilisée.

## Comment il apprend
| Étape | Ce qui se passe |
|---|---|
| **0 · Plafond** | 8 recherches très larges sur Donald (faisceau de 24 au lieu de 6). On voit ce qu'on peut espérer avec ces pièces, sans réseau. |
| **0 · Experts** | Recherche en faisceau avec l'heuristique sur les 101 BrickHeadz officielles : les meilleures constructions trouvées. |
| **1 · Imitation** | Le réseau apprend à classer chaque pièce posée par l'expert **devant** les pièces qu'elle a bloquées (perte par paires). |
| **2, 3, 4 · Boucle** | Faisceau guidé par le réseau. Quand une construction bat la meilleure connue, elle devient le nouvel exemple, et on réapprend. |

**Test honnête** : une officielle sur dix et le maillage Hunyuan de Donald ne servent jamais à l'entraînement. La courbe « réseau seul » montre si le réseau a appris quelque chose de général. La courbe « réseau + faisceau » montre jusqu'où il pousse la recherche sur Donald.

## Premier résultat : le plafond
Les 8 recherches très larges sur Donald (faisceau de 24, au lieu de 6) plafonnent à **88,2 %** pour la pire silhouette. La meilleure a 91,1 % de face, 88,4 % de profil et 88,2 % de dessus. C'est **autant que le faisceau de 6** (88,7 %). Le **profil reste bloqué vers 88–90 %** dans les 8 essais.

Chercher plus longtemps dans le même espace ne rapporte donc plus. Le réseau rendra peut-être la recherche plus rapide, mais l'ordre de pose n'est probablement pas ce qui bloque sous 95 %. Le blocage vient de **ce qu'on a le droit de poser** : les pièces, les accroches et la grille.

## Contre la vraie LEGO
La comparaison détaillée avec la vraie Donald est dans sa propre note : [Hunyuan contre la vraie LEGO](#/note/14-hunyuan-vs-vraie-lego) (recalage, modèles superposés en 3D, pièces manquantes).

En résumé :

- **La mesure change.** On ne garde plus que le **volume 3D**, avec une case pleine si plus de la moitié de son volume l'est.
- **La référence est la vraie LEGO.** Le maillage Hunyuan était en miroir et mal posé ; une fois recalé, il fait 91,9 % contre la vraie.
- **Il manque 12 formes de pièces** à l'optimiseur pour faire Donald, surtout des arrondis et les pièces du bec.

## À lire avec prudence

- L'étape 0 « glouton » est mesurée à λ = 2 (72,5 % sur Donald). Le meilleur glouton connu est à λ = 3 (80,2 %).
- Si le plafond reste sous 95 %, le réseau ne suffira pas. Il faudra plus de sortes de pièces et plus d'accroches latérales, ou une grille plus fine.
- Le Mac recopie son état ici toutes les 20 s. Une construction de Donald, avec ses silhouettes, apparaît à chaque mesure.
