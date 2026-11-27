---
title: Reconnaissance des pièces avec SAM
date: 2026-11-24
authors: Florian DEMARTINI, Claude (Anthropic)
status: archivé
summary: Découpage de la vue de dessus avec Segment Anything, puis identification par règles (taille, tenons, dégradé).
cover: /research/assets/02-sam-segments.jpg
tags: vision, SAM
metrics: Segments=95 (SAM complet) ; Sans référence=15 ; Découpage=69 s sur le Mac Studio
---

## Méthode
1. Découpage de la vue de dessus en segments avec **SAM** (MobileSAM sur le PC, SAM complet sur le Mac Studio).
2. Identification par règles : emprise en tenons, tenons visibles, dégradé de lumière (pente), forme ronde, couleur.

![Découpage](/research/assets/02-sam-segments.jpg)
![Pièces reconnues](/research/assets/02-sam-pieces.jpg)

## Résultat
Le découpage suit bien les pièces de la carapace. L'identification par règles reste fragile : sens des pentes, pièces absentes du catalogue, tête imprimée. L'assemblage 3D automatique construit à partir de ces détections était inutilisable.

## Où le retrouver
Les outils (Annoter, Mesures, Historique) sont dans chaque sujet, rubrique **Archive SAM**.
