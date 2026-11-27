---
title: Le squelette commun des BrickHeadz
date: 2026-11-27
authors: Florian DEMARTINI, Claude (Anthropic)
status: en cours
cover: /research/assets/16-cover.jpg
summary: Ce qui ne change presque jamais d'une BrickHeadz à l'autre, vu en 3D. En volume, le gabarit est très stable (83 % de la matière d'une figurine est commune à 70 % des figurines) ; en pièces, presque rien n'est exactement au même endroit, sauf le noyau de tête en briques à tenons latéraux.
tags: brickheadz, gabarit, données
metrics: volume commun à ≥ 70 % des figurines = 83 % d'une figurine ; pièces exactes dans ≥ 50 % = 9 ; noyau de tête 22885 = 98 % des figurines
---

## La question
Plutôt que de partir d'une officielle entière et de la modifier, trouver **la structure qui ne change presque jamais** entre les 101 figurines : le squelette commun, sur lequel on construira ensuite le reste.

## Comment on mesure
Les têtes ne sont pas à la même hauteur (de 4,5 à 24 plates selon le personnage). On aligne donc **le corps sur le socle** et **la tête sur sa propre base**, repérée par le premier étage de briques 22885, la pièce clé du noyau de tête. Ensuite, pour chaque case et pour chaque pièce, on compte dans combien de figurines elle est présente.
- **En volume** : une case de ½ tenon × ½ plate compte pleine si plus de la moitié de son volume l'est (vraie forme des pièces).
- **En pièces** : même pièce (impressions et couleurs ignorées), même position (à 4 LDU près), même orientation (sauf pièces symétriques).

## Ce qu'on voit
À gauche, le squelette en volume. À droite, les pièces exactement à la même place. Le curseur règle le seuil : présent dans au moins x % des figurines. La couleur va du clair (rare) au foncé (toujours). [Ouvrir en grand](/research/assets/16-skeleton.html)

<iframe src="/research/assets/16-skeleton.html" style="width:100%;height:560px;border:1px solid var(--line);border-radius:10px" loading="lazy" title="Squelette commun des BrickHeadz"></iframe>

| Seuil | Cases communes (volume) | Part d'une figurine typique (4 950 cases) | Pièces exactement à la même place |
|---|---|---|---|
| ≥ 90 % des figurines | 2 106 | 43 % | 0 |
| ≥ 70 % | 4 123 | **83 %** | 0 |
| ≥ 50 % | 4 473 | 90 % | 9 |
| ≥ 30 % | 5 167 | — | 31 |

**1. La forme du squelette ne change presque pas.** La tête cubique, le corps, les jambes courtes et le socle occupent presque toujours les mêmes cases. Ce qui varie, ce sont les bords de la tête, le dessus (cheveux, chapeau, oreilles), les bras et les accessoires.

**2. Les pièces qui le construisent changent beaucoup.** Même pour des personnages de forme identique, les concepteurs n'utilisent pas les mêmes pièces aux mêmes places : seulement 9 pièces exactes sont dans plus de la moitié des figurines. Une figurine typique n'a que 5 % de ses pièces dans ce squelette exact.

**3. Un noyau constant existe quand même : la tête.** À 30 %, on voit apparaître :
- le **cube de tête** en briques 1 × 2 × 1⅔ à tenons latéraux (22885) sur 2 à 3 étages, autour d'une colonne de briques 2 × 2 (3003). C'est sur ses tenons latéraux que s'accrochent la face et les côtés en plaques (SNOT) ;
- les **yeux** (tuiles rondes 1 × 1) à la même place ;
- les **bras** à clip, de chaque côté du corps ;
- le **socle** : une plaque 6 × 6 avec ses tuiles.

Ces pièces exactes **ne forment pas une figurine montable à elles seules** : le lien entre le corps et la tête change d'une figurine à l'autre.

## Ce qu'on en tire
Ton intuition est juste : on ne part pas d'une officielle entière. On garde ce qui est vraiment constant, et on construit le reste :
1. **un gabarit en volume** : les cases communes servent de forme de base, que la cible (maillage Hunyuan) vient déformer ;
2. **le noyau de tête en 22885** comme pièce imposée : c'est lui qui donne les tenons latéraux pour les faces en plaques, la finesse d'½ tenon que nos méthodes n'atteignaient pas (note 15) ;
3. **le reste** (corps, jambes, faces, cheveux, accessoires) construit par notre optimiseur autour de ce noyau.

## Fichiers
- Calcul : `brickforge/skeleton.py` ; résumé : `data/brickheadz/skeleton.json`.
- Vue 3D : `research/assets/16-skeleton.html` (données `16-skeleton.json`).
