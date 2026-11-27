# Règles du dépôt Brick Forge

Le projet : **photo → concept → modèle en briques montable**.
- Objectif 1 : une BrickHeadz depuis une image.
- Objectif 2 : n'importe quel objet.

Les méthodes de l'objectif 1 doivent rester **universelles**. Ce qui est propre à un format (squelette BrickHeadz, modules) est un a priori qu'on branche, jamais codé en dur dans la chaîne. Voir `research/notes/18-objectifs.md`.

## 1. Cahier de recherche

- **Une recherche = une note** : `research/notes/NN-titre-court.md`, numérotée à la suite. On ne réutilise jamais un numéro.
- **En-tête obligatoire** :
  ```
  ---
  title: …
  date: AAAA-MM-JJ                       (date de création)
  authors: Prénom Nom, Claude (Anthropic)
  status: en cours | terminé | écarté | archivé
  summary: une phrase
  cover: /research/assets/NN-cover.jpg    (toujours une image de présentation)
  tags: …
  metrics: Libellé=valeur ; Autre=valeur
  ---
  ```
- **Auteurs.** Toute personne ou IA qui a écrit une part réelle de la recherche (code, mesures, texte) est citée. L'humain qui dirige la recherche est cité en premier. Une IA est citée avec son éditeur, par exemple « Claude (Anthropic) ».
- **Structure du texte** : objectif, méthode, résultats chiffrés, ce qui ne marche pas, prochaine étape.
- **Honnêteté.**
  - Une méthode qui échoue reste dans le cahier, avec le statut `écarté` et la raison.
  - On ne réécrit pas un résultat après coup. Une correction devient une nouvelle version ou une nouvelle note.
  - Un « one shot » reste tel quel.
- **Visuel d'abord.** Chaque résultat important a sa vue (image, page 3D dans `research/assets/`). Les fichiers d'une note sont préfixés par son numéro (`17-defi.html`, `17-cover.jpg`).
- **Langue** : français.

## 2. Mesures

- **Référence.**
  - Quand elle existe, la référence est la **vraie LEGO** (le modèle officiel), pas un maillage généré.
  - Les images Gemini sont une **inspiration** : elles contiennent des pièces et des accroches impossibles. On ne les utilise jamais comme cible de mesure.
- **Mesure principale** : le volume (IoU au voxel, demi-tenon × plate, sans tolérance). Toute autre mesure est donnée en plus, jamais à la place.
- **Constructibilité.** Un modèle n'est présenté comme réussi que si le moteur (`brickforge/buildcheck.py`) confirme deux choses : rien ne vole, et aucune collision. Les pièces doivent être de vraies pièces LDraw.
- **Échantillon fixe.** Les comparaisons de méthodes se font sur le même échantillon (les 12 formes de la note 15), qu'on ne change pas en cours de route.

## 3. Code

- Le code Python est dans `brickforge/` (bibliothèque) et `app/` (Brick Forge Lab). Les conceptions pièce par pièce sont dans `designs/`.
- Chaque module a une docstring en tête : son rôle et la commande pour le lancer.
- Les calculs longs (entraînement, image → 3D) tournent en tâche de fond ou sur une machine distante. L'app suit leur avancement en direct.
- Les versions des fichiers statiques sont incrémentées dans `index.html` (`?v=N`) quand ils changent.

## 4. Ce qui ne va jamais dans le dépôt

- **Secrets.** Jamais de jeton, de clé d'API, de mot de passe ou de fichier `.env`. Les accès se font par clé SSH ou par un `login` de l'outil concerné. Un secret commité par erreur doit être **révoqué** : le retirer de l'historique ne suffit pas.
- **Données et poids** : `data/`, `out/`, `.venv/`, modèles `*.pt`, `*.safetensors` (voir `.gitignore`). Elles se téléchargent ou se régénèrent avec les scripts.
- **Contenus sous licence restrictive.**
  - Rien qui ne soit pas redistribuable : photos officielles LEGO, poids de modèles sous licence non commerciale (RMBG-2.0, DINOv3).
  - Les données LDraw et OMR sont citées avec leur licence quand on en publie des dérivés.
- **Fichiers lourds** (plus de 10 Mo) : seulement s'ils sont indispensables à une note.

## 5. Git

- `main` doit toujours être dans un état qui se lance. Les gros changements passent par une branche et une pull request.
- **Messages de commit** : en français, à l'impératif, courts (« Ajoute la note 18 », « Corrige le recalage miroir »).
- Un commit écrit avec une IA porte la ligne `Co-Authored-By:` correspondante.
