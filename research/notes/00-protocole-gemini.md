---
title: Protocole Gemini (concept et vues)
date: 2026-11-24
authors: Florian De Martini, Claude (Anthropic)
status: terminé
summary: Comment obtenir de Gemini un concept LEGO crédible et des vues cohérentes entre elles.
cover: /thumb/imgs/lego_tortue/concept.jpeg?w=640
tags: données, Gemini
metrics: Vues par sujet=6 ; Prompt de référence=celui de Florian
---

## Objectif
Obtenir de Gemini un **concept** de modèle en briques, puis des **vues sous plusieurs angles** du même modèle, exploitables pour la reconstruction.

## Ce qui marche
- **Prompt de concept** : celui de Florian, qui donne une contrainte de taille (« un petit set de 80 à 100 pièces »), demande des pièces variées (pentes, arrondis, SNOT) et réelles. Les versions courtes produisent beaucoup de pièces inventées.
- **Une vue par conversation**, avec l'image du concept jointe : « Voici un set LEGO de 80 à 100 pièces. Montre exactement le même modèle, avec les mêmes pièces, vu de face. »
- **6 vues** : concept, dessus, profil, face, dos, dessous.

## Ce qui ne marche pas
- **La planche de vues en une seule image** : les profils sont des copies en miroir, et l'échelle diffère d'une vue à l'autre.
- **Le nombre de pièces demandé n'est pas respecté** (la tortue en fait plutôt 150 à 300).

![Vues de la tortue](/thumb/imgs/lego_tortue/dessus.jpeg?w=480)
