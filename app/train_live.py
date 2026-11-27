"""Suivi de l'apprentissage du remplissage (note 13) : l'état est écrit sur le Mac Studio par brickforge.fill_learn
et recopié ici toutes les 20 s par scripts/sync_fill_train.sh.

    GET /api/train-fill/status           → status.json + constructions disponibles
    GET /api/train-fill/model/{file}     → pièces d'une construction (pour la vue 3D)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "data" / "brickheadz" / "fill_train"
router = APIRouter()


@router.get("/api/train-fill/status")
def status():
    f = RUN / "status.json"
    if not f.exists():
        return {"stage": "pas encore lancé", "models": []}
    s = json.loads(f.read_text())
    s["synced"] = f.stat().st_mtime
    s["now"] = time.time()
    models = []
    for m in sorted((RUN / "models").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(m.read_text())
        except ValueError:
            continue
        models.append({"file": m.name, "name": d.get("name"), "tag": d.get("tag"), "score": d.get("score"), "sil": d.get("sil"), "n": d.get("n")})
    s["models"] = models
    return s


@router.get("/api/train-fill/model/{file}")
def model(file: str):
    f = RUN / "models" / Path(file).name
    if not f.exists():
        raise HTTPException(404, "construction inconnue")
    return json.loads(f.read_text())
