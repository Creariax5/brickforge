# Brick Forge — prototype

Photo → concept Gemini → vues → modèle en briques (`.ldr`).
Cahier des charges : `cahier-des-charges-photo-to-brick.md`.

## Installation
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
Le premier lancement télécharge le modèle de détourage rembg (~180 Mo, dans `~/.rembg`).

## Données
Un dossier par sujet dans `imgs/`, avec des fichiers nommés par vue :
`concept`, `dessus`, `profil`, `face`, `dos`, `dessous` (`.jpeg`/`.jpg`/`.png`).
Minimum pour le pipeline : `dessus`, `profil`, `face`.
Conventions : dessus et dessous tête vers le haut de l'image, profil tête à droite
(sinon `--profil-tete gauche`), face = le sujet regarde l'objectif.

## Commandes
```
# Grille de tenons sur une vue de dessus (+ image de contrôle dans out/)
.venv/bin/python -m brickforge.grid imgs/lego_tortue/dessus.jpeg

# Pipeline complet : .ldr, nomenclature CSV, aperçus PNG, résumé JSON dans out/
.venv/bin/python -m brickforge.pipeline imgs/lego_tortue
```

## Brick Forge Lab (app locale)
```
.venv/bin/python -m app.server      # puis http://127.0.0.1:8000
```
- **Annoter** : vérité terrain de la vue de dessus (`imgs/<sujet>/gt_dessus.json`), créée à partir d'un
  lancement puis corrigée pièce par pièce (référence, type, taille, couleur, sens ; fusion, suppression, dessin).
- **Mesures** : rappel, précision, F1, bonne référence / couleur / taille / sens, liste des erreurs cliquable.
- **Historique** : tous les lancements (`out/runs/<sujet>/<id>/`) et l'évolution des scores.
- **Modèle 3D** et **Vues**.
- Lancements en tâche de fond : MobileSAM sur ce PC (mémoire limitée à 3 Go) ou SAM complet sur le
  Mac Studio (adresse dans `.brickforge.local`, non versionné : `BRICKFORGE_REMOTE=utilisateur@hôte` ; clé SSH, dossier `~/brickforge`).

## Modules
| Module | Rôle |
|---|---|
| `grid.py` | détourage (rembg), détection des tenons, grilles locales par sous-ensemble |
| `views.py` | chargement des vues, correction d'éclairage pour les couleurs |
| `voxels.py` | enveloppe visuelle dessus × profil × face, couleurs par vue, regroupement k-means |
| `colors.py` | palette LDraw, couleur la plus proche |
| `bricks.py` | pavage glouton des couches en plaques, joints croisés |
| `ldraw.py` | export `.ldr` et nomenclature |
| `render.py` | aperçus isométrique et vue de dessus |

## Cahier de recherche (app)
L'accueil de l'app (http://127.0.0.1:8000) est un cahier de recherche. Pour ajouter une recherche,
créer `research/notes/NN-titre.md` avec un en-tête :
```
---
title: …
date: 2026-11-25
authors: Prénom Nom, Claude (Anthropic)
status: en cours | terminé | écarté | archivé
summary: une phrase
cover: /research/assets/image.png   (ou /thumb/imgs/<sujet>/<vue>.jpeg?w=640)
metrics: Libellé=valeur ; Autre=valeur
live: training | compare            (optionnel : suivi en direct intégré)
subject: lego_tortue                (pour live: compare)
---
```
Elle apparaît dans la navigation et sur l'accueil sans toucher au code. Images dans `research/assets/`.
Routes : `#/`, `#/note/<id>`, `#/sujet/<nom>/<modele|comparer|vues|annoter|mesures|historique>`.
