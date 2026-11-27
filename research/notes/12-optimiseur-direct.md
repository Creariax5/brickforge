---
title: L'optimiseur de remplissage, en direct
date: 2026-11-26
authors: Florian DEMARTINI, Claude (Anthropic)
status: en cours
cover: /research/assets/12-cover.jpg
summary: Regarder l'algorithme poser les pièces une à une sur la forme visée (maillage Hunyuan3D ou BrickHeadz officielle), avec la couche en cours et les silhouettes qui montent vers l'objectif de 90 %.
tags: brickheadz, optimisation, construction, direct
live: fill-live
metrics: objectif = silhouettes ≥ 90 % ; rien ne vole (accroches réelles)
---

## Ce que montre la page
- **En bleu transparent** : la forme à remplir. Ce sont les cases de surface de la cible, en ½ tenon × ½ plate.
- **Les pièces** apparaissent dans l'ordre où l'optimiseur les pose. La dernière est en orange.
- **Le plan orange** indique la plate en cours. On voit les **passes** successives : la première est stricte (on ne déborde pas), les suivantes sont plus permissives pour boucher les trous.
- **À droite** : le nombre de pièces, la dernière pièce posée avec son gain, et les silhouettes face, profil, dessus et volume. Le trait vertical marque l'objectif de 90 %.

## Réglages
| Réglage | Rôle |
|---|---|
| **λ (débord)** | Coût d'une case posée hors de la forme. Plus il est grand, plus l'optimiseur reste à l'intérieur. |
| **part dedans** | Part minimale du volume d'une pièce qui doit tomber dans la forme. |
| **relâche** | Facteur appliqué à λ à chaque passe. |
| **passes** | Nombre de balayages de bas en haut. |

La méthode est détaillée dans la note 11, section « Remplissage optimisé ». Le code est dans `brickforge/fill.py`, la page appelle `app/fill_live.py`.
