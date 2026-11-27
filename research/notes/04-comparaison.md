---
title: Comparaison rendu / photos et optimisation
date: 2026-11-25
authors: Florian DEMARTINI, Claude (Anthropic)
status: terminé
summary: Caméra calée sur chaque vue Gemini, scores de silhouette et de contour, puis réglages ajustés automatiquement.
cover: /research/assets/05-superposition.jpg
tags: mesure, optimisation
metrics: Silhouette=70 % → 77,8 % ; Contour=2,9 % → 1,9 % ; Calage=~5 s par vue
live: compare
subject: lego_tortue
---

## Méthode
- **Calage de caméra** pour chaque vue : orientation (limitée à ±5° autour de l'angle prévu), distance commune à toutes les vues, focale.
- **Scores** : recouvrement des silhouettes, écart moyen des contours, couleur par zone (indicatif).
- **Optimisation** (`designs/optimize.py`) : les réglages du script (inclinaison et balayage des nageoires, hauteur de la tête…) sont ajustés pour maximiser le score, sous contraintes physiques (pas de pièce flottante, rien sous la table).

![Différences de face](/research/assets/04-diff-face.png)

## Résultat
Silhouette moyenne de **70 % à 77,8 %**. Le score géométrique ne mesure pas la beauté : un modèle moche peut obtenir le même score.
