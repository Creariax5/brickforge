# Techniques et pièces LEGO — référence pour les prompts et le catalogue

> Objectif double :
> 1. Nommer des pièces et techniques **concrètes** dans le prompt Gemini pour éviter les pièces inventées.
> 2. Servir de base au **catalogue MVP** (~50 pièces) du moteur d'assemblage : ce que le concept utilise = ce qu'on doit savoir identifier et poser.

---

## 1. Techniques de construction

| Technique | Principe | Usage typique (animaux, objets) | Pièces clés |
|---|---|---|---|
| **Empilement classique** | Tenons vers le haut, joints décalés entre couches | Corps, volumes pleins, structure interne | Briques 1×1 → 2×8, plaques |
| **Empilement de plaques** | 3 plaques = 1 brique : réglage fin de la hauteur | Profils précis, transitions | Plaques 1×1 → 4×8 |
| **Finition lisse (studless / tiling)** | Tuiles par-dessus les tenons | Dos, dessus de tête, surfaces « peau » | Tuiles 1×1, 1×2, 1×4, 2×2 |
| **Pentes** | Surfaces inclinées droites | Toits, épaules, museaux anguleux | Pentes 45° 2×1 / 2×2, 33° 3×1, 65° 2×1 |
| **Pentes inversées** | Pentes tournées vers le bas | Ventre, mâchoire, dessous de tête | Pente inversée 45° 2×1 / 2×2 |
| **Pentes courbes** | Courbes douces, rendu organique | **Technique n°1 pour les animaux** : dos, cuisses, joues | Pente courbe 1×2, 1×3, 1×4, 2×2, 2×4, double courbe |
| **Wedges (biseaux)** | Plaques/briques en angle dans le plan horizontal | Têtes effilées, oreilles, ailes, becs | Wedge plate 2×2, 2×3, 2×4, 3×3 (gauche/droite) |
| **Formes rondes** | Cercles, dômes, cylindres | Yeux, nez, pattes, troncs | Plaque ronde 1×1 / 2×2, tuile ronde 1×1 / 2×2, brique ronde 1×1 / 2×2, dôme, cône, macaroni, quarts de rond |
| **SNOT** (Studs Not On Top) | Tenons orientés sur le côté → construire latéralement | Visages, flancs, détails de côté | Brique 1×1 tenon latéral (1 ou 4 côtés), brique 1×4 tenons latéraux, « headlight brick », brackets 1×2-1×2, 1×2-2×2, inversés |
| **Décalage d'un demi-tenon** | Centrer un élément entre deux tenons | Yeux, nez centrés, symétrie sur largeur paire/impaire | Jumper plate 1×2 (1 tenon central), tuile 2×2 avec tenon central |
| **Clip et barre** | Liaison articulée à angle libre | Queues, cornes, pattes fines, angles non orthogonaux | Plaque avec clip, plaque avec barre, barre 1L/3L/4L, clip vertical |
| **Charnières** | Rotation autour d'un axe | Cou, mâchoire, inclinaison de sous-ensembles | Charnière plaque 1×2, click hinge (à crans), charnière brique |
| **Rotules (ball joints)** | Orientation libre, pose réglable | Membres orientables, tête | Plaque avec rotule / avec cupule |
| **Plateau tournant** | Rotation dans le plan horizontal | Tourner la tête, orienter un sous-ensemble | Turntable 2×2 |
| **Connexions Technic** | Axes et goupilles | Liaison robuste de sous-ensembles, cous longs | Brique Technic 1×2 avec trou, goupille, axe, poutre |
| **Sous-ensembles orientés** | Un bloc construit à part puis fixé sous un angle | Tête, pattes, queue | Combine SNOT + charnières/clips |
| **Détails et greebling** | Petites pièces pour la texture | Yeux, griffes, dents, grilles | Tuile ronde imprimée œil, dents/griffes, tuile grille, plaque avec dent |

---

## 2. Pièces récurrentes des petits animaux (style Creator 3-en-1)

Base de départ pour le **catalogue MVP** :

- **Structure** : briques 1×1, 1×2, 1×4, 2×2, 2×4 ; plaques 1×1, 1×2, 1×4, 2×2, 2×4.
- **Formes** : pente courbe 1×2, 2×2, 1×4 ; pente 45° 2×1, 2×2 ; pente inversée 45° 2×1 ; wedge plate 2×2 G/D, 2×3 G/D.
- **Finition** : tuile 1×1, 1×2, 2×2 ; tuile ronde 1×1 ; plaque ronde 1×1, 2×2.
- **SNOT** : brique 1×1 tenon latéral, headlight brick, bracket 1×2-1×2, bracket 1×2-1×2 inversé.
- **Liaisons** : jumper plate 1×2, plaque avec clip, plaque avec barre, barre 3L, charnière plaque 1×2, click hinge.
- **Détails** : tuile ronde 1×1 œil (ou plaque ronde 1×1 noire), dent / griffe.

→ ~40 pièces. Couleurs : 8 à 10 au départ (noir, blanc, gris clair/foncé, marron, marron foncé, beige, rouge, jaune, bleu, vert).

---

## 3. Prompts Gemini (à tester)

> **Mise à jour** : le prompt de référence est celui de Florian (« Fait une image de cette image en lego… Un petit set 80 a 100 pieces… avec des vraies pieces »), nettement meilleur que les variantes courtes. Hypothèse : la contrainte de taille (« petit set de N pièces ») est le facteur principal contre les pièces inventées. Les variantes ci-dessous sont à tester en partant de ce prompt, en ne changeant qu'un élément à la fois.

Cause probable des pièces inventées : Gemini **sculpte des formes sur mesure** au lieu de les approximer avec des pièces standard. Deux leviers :
1. ancrer le style sur des **sets officiels** (Creator 3-en-1), dont le vocabulaire de pièces est standard ;
2. interdire explicitement les pièces sur mesure.

### Variante A — courte
> Fais le sujet principal de cette photo en modèle LEGO, comme un set LEGO Creator 3-en-1 officiel. Uniquement des pièces LEGO standard qui existent, aucune pièce moulée sur mesure. Fond blanc.

### Variante B — pièces nommées
> Fais le sujet principal de cette photo en modèle LEGO, comme un set LEGO Creator 3-en-1 officiel. Uniquement des pièces LEGO standard qui existent, aucune pièce moulée sur mesure : briques, plaques, pentes, pentes inversées, curved slopes, wedge plates, tuiles, pièces rondes, SNOT (bricks with studs on side, brackets), clips et barres, charnières. Fond blanc.

### Protocole A/B
- Même photo, 3 générations par variante (+ 3 avec le prompt actuel comme référence).
- Mesurer : part de pièces qui semblent inventées, variété des pièces, nombre de pièces estimé.
- Attention au compromis observé : **un prompt plus long = plus d'erreurs**. Si B n'apporte rien de plus que A, garder A.
