---
title: Chèvre : photo seule, puis concept Gemini
date: 2026-11-25
authors: Florian DEMARTINI, Claude (Anthropic)
status: terminé
summary: Deux conceptions pièce par pièce de la même chèvre, l'une d'après la photo, l'autre d'après le concept et la liste de pièces de Gemini.
cover: /thumb/imgs/lego_chevre_v2/concept.jpeg?w=640
tags: conception, Gemini
metrics: v1 (photo)=79 pièces ; v2 (concept)=105 pièces ; v3 (mélange)=104 pièces
subject: lego_chevre_v2
---

## v1 : d'après la photo seule
Corps en briques, pattes en briques rondes, taches noires, collier, cornes, herbe. Reconnaissable mais carré (`designs/chevre_v1.py`).

## v2 : d'après le concept Gemini et sa liste de pièces
- **Flancs SNOT** : briques à tenons latéraux (11211) habillées de plaques 1×2 montées sur le côté, qui portent les taches.
- **Pattes** en cônes et plaques rondes (sabot noir, pâturon blanc, canon noir), comme sur le concept.
- Collier de plaques rondes orange et grises, cornes 53451, touffe d'herbe 32607.

La notice de Gemini contient des incohérences (4 briques 1×2 en ligne annoncées comme 6 tenons, une pince 4085d qui n'existe pas sous ce numéro) : on suit l'image, et on garde ses pièces quand elles sont réalistes.

## v3 : proportions de la v1, détails de la v2
Avis de Florian : la v2 est plus détaillée, mais **la v1 respecte bien mieux les dimensions**. Le concept Gemini est
stylisé (corps court et haut, grandes pattes, petit cou) et la v2 en a hérité. La v3 garde les dimensions de la v1
(corps 4×8, pattes de 9 plaques) avec les détails de la v2, toutes fixations légales.

## Ce qu'on retient
**Les proportions se prennent sur la photo, les détails sur le concept.** La liste de pièces de Gemini est utile : elle donne les bonnes familles (SNOT, cônes, plaques rondes, cornes) et facilite beaucoup la conception. Ses quantités et sa notice ne sont pas fiables.

Ouvrir le modèle : [v1](#/sujet/lego_chevre_v1/modele) · [v2](#/sujet/lego_chevre_v2/modele) · [v3](#/sujet/lego_chevre_v3/modele).
