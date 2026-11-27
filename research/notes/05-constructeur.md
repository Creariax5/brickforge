---
title: Constructeur automatique pièce par pièce
date: 2026-11-25
authors: Florian DEMARTINI, Claude (Anthropic)
status: écarté
summary: Moteur qui emboîte les pièces sur des tenons libres pour remplir la forme cible. Rapide et gratuit, mais visuellement pauvre.
cover: /research/assets/06-tortue-auto.png
tags: génération
metrics: Temps=16 s ; Coût=0 € ; Silhouette=79,0 % ; Pentes=46 sur 110 pièces
subject: lego_tortue_auto
---

## Méthode
- **Points d'accroche** de chaque pièce lus dans LDraw (`brickforge/connect.py`).
- **Forme cible** sculptée depuis les 6 silhouettes (`brickforge/target.py`).
- À chaque étape, toutes les positions de toutes les pièces sont évaluées ; seuls les gestes réels sont autorisés (emboîtée sur un tenon libre, sans collision).

![Tortue automatique](/research/assets/06-tortue-auto.png)

## Résultat
Même score de silhouette que la tortue conçue à la main, mais **sans intention** : ni symétrie, ni sous-ensembles, ni goût. Il servira à remplir l'intérieur caché des modèles et à générer des données d'entraînement.
