#!/bin/bash
# Recopie l'état de l'apprentissage (Mac Studio → ici) toutes les 20 s, tant que le calcul tourne là-bas.
cd "$(dirname "$0")/.." || exit 1
S="ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 -i $HOME/.ssh/id_ed25519"
[ -f .brickforge.local ] && . ./.brickforge.local
M=${BRICKFORGE_REMOTE:?définir BRICKFORGE_REMOTE dans .brickforge.local}
mkdir -p data/brickheadz/fill_train
while true; do
  rsync -az -e "$S" --include status.json --include 'models/***' --include train.log --exclude '*' \
    "$M:brickforge-fill/data/brickheadz/fill_train/" data/brickheadz/fill_train/ 2>/dev/null
  grep -q '"stage": "termin' data/brickheadz/fill_train/status.json 2>/dev/null && exit 0
  sleep 20
done
