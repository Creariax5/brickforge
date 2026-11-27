# Cahier des charges — Photo → Modèle en briques constructible

> Nom de travail : **Brick Forge** (provisoire)
> Version : 0.1 — 24/11/2026
> Auteur : Florian Demartini

---

## 1. Contexte et vision

Il existe aujourd'hui :
- des générateurs de **mosaïques 2D** (marché saturé) ;
- des convertisseurs **3D → briques** (Brickplicator, BrickSolvr, Bricker) qui produisent un rendu « voxel » à base de briques rectangulaires ;
- des modèles de recherche (LegoGPT/BrickGPT, LEGO-Maker) stables mais limités en pièces et en esthétique ;
- des IA génératives d'image (Gemini…) capables de produire un **concept** de modèle en briques très crédible visuellement, mais sans liste de pièces, sans intérieur ni arrière, et sans garantie de constructibilité ;
- des outils de **reconnaissance de pièces en vrac** (Brickit, Brickognize).

**Vision** : à partir d'une ou plusieurs photos d'un sujet (animal, objet, véhicule…), générer un **modèle 3D en briques réelles**, d'une qualité esthétique proche des sets du commerce, avec :
- la liste exacte des pièces (référence + couleur) ;
- des instructions de montage pas à pas ;
- un panier d'achat (BrickLink / Pick a Brick) ;
- à terme, la possibilité de **construire avec ses propres pièces** (scan du vrac).

**Idée clé** : l'IA générative fait la partie artistique (stylisation) ; notre moteur fait la **rétro-ingénierie** : identification des pièces, structure interne, stabilité, instructions.

---

## 2. Objectifs et non-objectifs

### Objectifs
- O1 — Générer un modèle **constructible et stable** (aucune pièce flottante, connexions valides).
- O2 — Utiliser un **vocabulaire de pièces riche** (pentes, courbes, SNOT, tuiles, plaques rondes, pièces de détail), pas seulement des briques rectangulaires.
- O3 — Rester **fidèle au sujet** de la photo (couleurs, silhouette, traits distinctifs).
- O4 — Fournir liste de pièces, instructions et export panier.
- O5 — Temps de génération acceptable (cible MVP : < 15 min par modèle).

### Non-objectifs (V1)
- Personnages humains réalistes et visages ressemblants.
- Mécanismes fonctionnels (Technic, pièces mobiles).
- Pièces imprimées / stickers personnalisés.
- Modèles de plus de ~1500 pièces.

---

## 3. Utilisateurs cibles

| Persona | Besoin | Valeur apportée |
|---|---|---|
| Particulier / propriétaire d'animal | Avoir son chat, son chien ou sa voiture en briques | Cadeau unique, effet « wow » |
| AFOL (fan adulte) | Gagner du temps de conception, avoir une base à retoucher | Export BrickLink Studio éditable |
| Parent / enfant avec un gros vrac | Construire quelque chose de perso avec ses pièces existantes | Mode « avec mes pièces » |
| Pro (cadeaux d'entreprise, événementiel) | Modèles sur mesure à la demande | Génération rapide + kit prêt à commander |

---

## 4. Parcours utilisateur

1. **Upload** : 1 à 5 photos du sujet (+ option : choix de la taille cible : petite / moyenne / grande).
2. **Concept** : affichage rapide (< 1 min) d'un ou plusieurs **concepts visuels** générés ; l'utilisateur choisit celui qu'il préfère.
3. **Génération** : construction du modèle réel en arrière-plan, avec barre de progression.
4. **Visualisation 3D** : viewer web interactif (rotation, zoom, vue éclatée, comparaison concept / résultat).
5. **Ajustements** (V2) : taille, palette de couleurs, budget max, « simplifier ».
6. **Livrables** : liste de pièces, instructions PDF / interactives, export `.io` (BrickLink Studio) / `.ldr`, wanted list BrickLink XML.
7. **Mode « mes pièces »** (V3) : scan du vrac → modèle optimisé pour les pièces possédées → liste des pièces manquantes uniquement.

---

## 5. Périmètre fonctionnel par version

### MVP (preuve de concept)
- Upload d'une photo unique.
- Génération d'un concept visuel (API d'image générative).
- Génération multi-vues + reconstruction 3D du concept (modèle image-to-3D existant).
- Conversion en briques avec un **catalogue restreint (~50 pièces)** et contrôle de stabilité.
- Viewer 3D web + liste de pièces CSV.

### V1
- Catalogue étendu (~300–500 pièces les plus courantes, ~40 couleurs).
- Modèle de vision maison pour **identifier les pièces** sur les vues du concept.
- Remplissage automatique de l'intérieur (structure porteuse).
- Instructions pas à pas (découpage en sous-ensembles).
- Export BrickLink XML + `.ldr` / `.io`.
- Comptes utilisateurs, historique des modèles.

### V2
- Plusieurs photos en entrée (meilleure fidélité).
- Réglages : taille, budget, nombre de couleurs, niveau de détail.
- Boucle de raffinement « render-and-compare » (un modèle de vision juge la ressemblance concept / rendu).
- Estimation de prix en temps réel (API BrickLink).

### V3
- Scan du vrac de l'utilisateur (reconnaissance de pièces en vrac).
- Génération contrainte par l'inventaire possédé.
- Galerie communautaire, partage, remix.

---

## 6. Architecture technique

### 6.1 Pipeline global

```
Photo(s)
  │
  ▼
[1] Prétraitement ─ détourage du sujet, normalisation
  │
  ▼
[2] Génération du concept ─ IA image (style « set officiel »)
  │
  ▼
[3] Multi-vues ─ face / profil / dos / dessus, cohérentes
  │
  ▼
[4] Reconstruction 3D ─ mesh texturé du concept (image-to-3D)
  │
  ▼
[5] Identification des pièces ─ modèle de vision maison
  │      (segmentation + ID pièce + couleur + pose)
  ▼
[6] Moteur d'assemblage
  │      ├─ recalage sur la grille et les connexions réelles (catalogue LDraw)
  │      ├─ comblement des zones non identifiées (voxels → briques)
  │      ├─ structure interne porteuse
  │      └─ contrôle de stabilité (graphe de connexions + physique)
  ▼
[7] Raffinement ─ render-and-compare vs concept (V2)
  │
  ▼
[8] Instructions ─ ordre de montage, sous-ensembles, rendu des étapes
  │
  ▼
[9] Livrables ─ viewer 3D, BOM, PDF, exports, panier
```

### 6.2 Détail des modules

**[2] Concept** : API d'image générative (Gemini ou équivalent). Prompt maîtrisé + images de référence de style. Il faut vérifier les CGU pour un usage commercial.

**[3]-[4] Multi-vues et 3D** : modèles open source existants (famille TRELLIS, Hunyuan3D…) ou API (Tripo, Meshy). Aucun entraînement prévu ici.

**[5] Modèle de vision** : voir §7.

**[6] Moteur d'assemblage** : cœur propriétaire du produit.
- Représentation : grille discrète (unité = 1 tenon × 1 plaque), pièces avec points de connexion typés (tenon, tube, clip, barre, SNOT).
- Source de vérité géométrique : **bibliothèque LDraw**.
- Recalage : les pièces détectées sont projetées sur la grille et les connexions valides les plus proches.
- Comblement : voxelisation des zones restantes, puis fusion en plus grandes briques (heuristique gloutonne, puis optimisation).
- Stabilité : graphe de connexions connexe, pas de porte-à-faux excessif, analyse de forces simplifiée (inspirée de LegoGPT/StableLego).
- Objectif d'optimisation : ressemblance visuelle (prioritaire), nombre de pièces, coût, robustesse.

**[8] Instructions** : ordre de montage calculé par couches et sous-ensembles (tête, corps, queue…), avec la contrainte « chaque pièce est posable au moment où elle apparaît ». Rendu des étapes avec Blender ou LDView.

### 6.3 Stack proposée

| Couche | Choix |
|---|---|
| Front | Next.js + Three.js (viewer 3D, chargement LDraw) |
| API | Python (FastAPI) |
| Jobs longs | File de tâches (Celery/RQ + Redis) |
| GPU inférence | Workers GPU cloud (RunPod / Vast.ai / Lambda), autoscaling |
| Rendu | Blender headless (+ addon d'import LDraw) |
| Stockage | S3-compatible (photos, meshes, modèles) + PostgreSQL |
| ML | PyTorch, backbone pré-entraîné (DINOv2 ou équivalent), Mask2Former / YOLO-seg |

---

## 7. Modèle de vision (identification des pièces)

### 7.1 Tâche
À partir d'une image (vue du concept), produire pour chaque pièce visible :
- un masque de segmentation ;
- la référence de pièce (ID LDraw / BrickLink) ;
- la couleur ;
- la pose 3D (position + orientation), affinée ensuite par render-and-compare.

### 7.2 Données (100 % synthétiques au départ)
- **Source** : bibliothèque LDraw (~20 000 pièces modélisées, gratuite).
- **Générateur de scènes** : script Blender qui assemble des pièces connectées (aléatoirement ou à partir de modèles existants Rebrickable/OMR).
- **Domain randomization** : caméra, éclairage, matériaux (brillance, usure), fonds, flou, bruit.
- **Annotations automatiques** : masque, ID pièce, couleur et pose, connus par construction.
- **Domaine cible** : ajout de rendus stylisés proches des images générées, puis fine-tuning sur quelques centaines d'images de concept annotées.
- **Volumes** :
  - prototype : 50 pièces, ~20 000 images ;
  - V1 : 300–500 pièces, 200 000–500 000 images.
- **Jeu de test** : ~200 images de concepts générés, annotées à la main. C'est **la métrique de référence**.

### 7.3 Modèle
- Backbone pré-entraîné + tête de segmentation d'instances.
- Classification de la couleur séparée (~40–60 classes).
- Pose : estimation grossière, puis **render-and-compare** (rendu de la pièce candidate, comparaison à l'image, ajustement).
- Contraintes de grille en post-traitement pour corriger les erreurs.

### 7.4 Infrastructure et coûts estimés

| Poste | Estimation |
|---|---|
| Machine | 1× RTX 4090/5090 (24–32 Go) suffisante ; A100/H100 en cloud pour accélérer |
| Rendu des données | ~0,5–2 s/image (Eevee), 1 à 4 jours GPU pour 200 000 images, parallélisable |
| Entraînement | 1 à 3 jours de fine-tuning par itération |
| Budget cloud V1 | quelques centaines d'euros |

### 7.5 Raccourci de prototypage
Pour l'identification de pièces isolées, l'API **Brickognize** peut servir à valider le pipeline avant d'avoir le modèle maison. Il faut vérifier ses conditions d'usage commercial.

---

## 8. Exigences non fonctionnelles

- **Performance** : concept < 1 min ; modèle complet < 15 min (MVP), < 5 min (cible).
- **Scalabilité** : jobs asynchrones, workers GPU à la demande.
- **Coût unitaire** : coût de calcul par modèle < 0,50 € (cible).
- **Confidentialité** : photos supprimables, non utilisées pour l'entraînement sans consentement (RGPD).
- **Disponibilité** : 99 % (hors maintenance).
- **Compatibilité** : viewer sur desktop et mobile (WebGL).

---

## 9. Contraintes juridiques

- **Marque LEGO®** : ne pas utiliser « LEGO » dans le nom du produit ni le logo. Communiquer en « briques compatibles » avec la mention « LEGO® est une marque du groupe LEGO, qui ne sponsorise ni n'approuve ce service ».
- **Propriété intellectuelle des sujets** : refuser ou avertir pour les personnages sous licence (Disney, Marvel…).
- **CGU des API tierces** : IA d'image, Brickognize, BrickLink, Rebrickable. Vérifier l'usage commercial et le droit d'utiliser les sorties.
- **LDraw** : licence de la bibliothèque (CC BY), à respecter et créditer.

---

## 10. Critères d'acceptation et KPI

| Critère | Cible MVP | Cible V1 |
|---|---|---|
| Modèles stables (simulation) | ≥ 95 % | ≥ 98 % |
| Modèles réellement construits avec succès (test physique) | 3/5 | 9/10 |
| Précision d'identification des pièces (jeu de test concepts) | — | ≥ 80 % top-1 |
| Ressemblance jugée « bonne ou très bonne » (panel utilisateurs) | ≥ 50 % | ≥ 75 % |
| Part de pièces « non rectangulaires » dans un modèle | ≥ 20 % | ≥ 40 % |
| Temps de génération | < 15 min | < 5 min |

---

## 11. Roadmap indicative

| Phase | Durée | Livrable |
|---|---|---|
| 0. Exploration | 2 semaines | Tests manuels : concept, multi-vues, 3D, voxelisation naïve |
| 1. Générateur de données | 3 semaines | Script Blender + LDraw, 20 000 images annotées, 50 pièces |
| 2. Modèle v0 | 2–3 semaines | Segmentation + ID sur 50 pièces, mesuré sur concepts |
| 3. Moteur d'assemblage v0 | 4 semaines | Recalage grille + comblement + stabilité |
| 4. MVP web | 3 semaines | Upload → viewer 3D → liste de pièces |
| 5. Test physique | 1 semaine | Construction réelle de 5 modèles |
| 6. V1 | 2–3 mois | 500 pièces, instructions, exports, comptes |

---

## 12. Risques

| Risque | Impact | Mitigation |
|---|---|---|
| Écart entre rendus synthétiques et images générées | Élevé | Rendus stylisés, fine-tuning sur concepts annotés, évaluation précoce |
| Incohérence entre vues générées (dos inventé) | Moyen | Génération multi-vues conditionnée, priorité à la face avant, arrière simplifié |
| Pièces « hallucinées » ou inexistantes dans le concept | Moyen | Recalage sur le catalogue réel, substitution par la pièce la plus proche |
| Instabilité physique malgré la simulation | Moyen | Marges de sécurité, tests physiques réguliers |
| Combinatoire du moteur d'assemblage trop lente | Élevé | Heuristiques gloutonnes puis optimisation locale, catalogue restreint au départ |
| Dépendance à des API tierces (coût, CGU) | Moyen | Abstraction des fournisseurs, alternatives open source |
| Juridique (marque, licences) | Moyen | Naming neutre, disclaimers, filtrage des sujets sous licence |

---

## 13. Modèle économique (pistes)

- Freemium : concept et aperçu 3D gratuits, liste de pièces et instructions payantes (à l'unité).
- Abonnement pour les AFOL (générations illimitées, export Studio).
- Commission d'affiliation sur les paniers BrickLink / revendeurs.
- Offre B2B (cadeaux d'entreprise, événementiel) : kit physique livré.

---

## 14. Questions ouvertes

- Cadre du projet : EIP, side project, startup (Pépite) ?
- Taille cible par défaut des modèles (nombre de pièces) ?
- Fournisseur d'IA d'image pour les concepts, et ses conditions d'usage commercial ?
- Faut-il livrer des kits physiques à terme, ou rester 100 % numérique ?
- Nom définitif du produit, avec vérification de disponibilité (INPI, domaine) ?
