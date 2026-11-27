---
title: Objectifs et bilan d'étape
date: 2026-11-27
authors: Florian De Martini, Claude (Anthropic)
status: en cours
cover: /research/assets/03-tortue-conception.png
summary: Où on en est après 17 recherches, ce qui marche, ce qui bloque, et les deux objectifs fixés : 1. une BrickHeadz depuis une image, 2. n'importe quel objet. Les méthodes de l'objectif 1 doivent rester universelles.
tags: bilan, objectifs, méthode
metrics: Objectif 1 = BrickHeadz ; Objectif 2 = n'importe quoi ; meilleurs résultats = Claude pièce par pièce (tortue, défi costume)
---

## Les deux objectifs

1. **Une BrickHeadz depuis une image** : montable avec de vraies pièces, propre, et on reconnaît le personnage.
2. **N'importe quel objet** : animal, véhicule, objet du quotidien.

**Contrainte :** le but final est un outil **universel**. Tout ce qu'on construit pour l'objectif 1 doit donc pouvoir servir à l'objectif 2. Ce qui est propre aux BrickHeadz (le squelette commun, les modules de cheveux et de corps) est un **a priori qu'on branche**. Il ne doit pas être codé en dur dans la chaîne.

## Bilan

| Étape | Où on en est |
|---|---|
| **Concept (Gemini)** | Utile, mais Gemini invente beaucoup de choses impossibles à construire : pièces qui n'existent pas, accroches impossibles. Ses images **aident pourtant Claude** à concevoir. On les traite donc comme une **inspiration**, jamais comme la cible à mesurer. |
| **Forme 3D** | Réglée. Une fois recalés, Hunyuan3D atteint 92 % de volume et TRELLIS.2 89 % (notes 14, 15). |
| **Forme → pièces, automatiquement** | Bloqué entre 79 et 86 % : tout se monte, mais le rendu reste « voxel ». Le plafond de la méthode brique par brique est d'environ 89 % (note 15). |
| **Claude pièce par pièce** | Les meilleurs résultats : la **tortue** (note 03) et le **défi costume** (note 17, 121 pièces, rien ne vole, aucune collision). Mais c'est fait à la main. |
| **Outils** | Solides : moteur de constructibilité (vraies accroches, vraies collisions), bac à sable, comparaison rendu / image. |

**Ce que ça dit.** Le blocage n'est plus la forme, c'est le **langage LEGO** : tuiles posées sur des tenons de face, pentes courbes, modules. Un remplissage de volume ne le trouve pas, alors que Claude, guidé par une image, le trouve.

**Notre mesure ne regarde que le volume.** Une construction peut avoir un très bon volume et ressembler au mauvais personnage.

## La direction : universelle, et testée d'abord sur les BrickHeadz

On garde ce qui marche, Claude qui conçoit, et on l'outille pour qu'il le fasse seul et de façon vérifiable :

1. **Image → concept** (Gemini), qui sert d'inspiration.
2. **Image → forme 3D** (Hunyuan / TRELLIS), qui sert de cible de volume et de couleurs.
3. **A priori** sur la façon de construire ce type d'objet :
   - pour une BrickHeadz : squelette commun plus modules par zone, tirés des 101 officielles ;
   - pour n'importe quoi : les techniques et sous-ensembles tirés des sets officiels (OMR, 1 472 sets).
4. **Claude conçoit** pièce par pièce avec le bac à sable comme outil, comme pour le défi.
5. **Contrôle à chaque étape** : le moteur vérifie que rien ne vole et qu'il n'y a pas de collision. Un **rendu comparé à l'image** (silhouette et couleur, plusieurs angles) indique où ça s'écarte.
6. Claude corrige, et on recommence jusqu'à ce que ça converge.

Seule l'étape 3 change d'un objectif à l'autre. Le reste est commun.

## Pas encore testé

- La mesure par rendu contre l'image, à la place du volume seul.
- Les modules par zone : combiner les meilleurs cheveux, visage et torse issus de figurines différentes.
- Le visage et les couleurs tirés de la texture du modèle 3D.
- La boucle Claude + moteur + rendu, **automatisée**.
- De vraies photos d'utilisateur, de bout en bout.
- Les gros jeux de données : StableText2Brick et les sets OMR.
- La notice de montage, le prix des pièces, et un montage physique réel.
