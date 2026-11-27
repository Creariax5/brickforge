"""Optimiseur de remplissage en direct : lance brickforge.fill dans un fil d'exécution et diffuse chaque pièce posée.

    POST /api/fill/run   {src, lam, ratio, relax, passes, plates}  → {job}
    GET  /api/fill/sources                                          → cibles disponibles (maillages Hunyuan3D, BrickHeadz officielles)
    GET  /api/fill/job/{job}?since=n                                → nouveaux événements (pièces, couches) + état
    GET  /api/fill/job/{job}/target                                 → cases de surface de la cible (pour l'afficher en transparence)
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Body, HTTPException

ROOT = Path(__file__).resolve().parent.parent
HY = ROOT / "data" / "hunyuan"
router = APIRouter()
JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


@router.get("/api/fill/sources")
def sources():
    out = []
    for d in sorted(HY.glob("*")) if HY.exists() else []:
        if (d / "textured.glb").exists():
            out.append({"id": d.name, "label": f"{d.name} · maillage Hunyuan3D", "kind": "mesh"})
    figs = json.loads((ROOT / "data" / "brickheadz" / "figures.json").read_text())
    for f in figs:
        out.append({"id": f"{f['num']}:{f['fig']}", "label": f"{f['set']}" + (f" ({f['fig'] + 1}/{f['nfigs']})" if f.get("nfigs", 1) > 1 else "")
                    + f" · officielle {f['num']}", "kind": "official"})
    return out


def _target(src: str, plates: float | None):
    from brickforge import fill as F
    if (HY / src / "textured.glb").exists():
        from brickforge.from_mesh import load
        d = HY / src
        yaw, pl = 0, 27.0
        for name in ("fill.json", "build.json"):
            if (d / name).exists():
                info = json.loads((d / name).read_text())
                yaw = info.get("yaw", yaw)
                pl = info.get("plates", pl)
        return F.target_from_mesh(load(d / "textured.glb"), yaw, plates or pl)
    figs = json.loads((ROOT / "data" / "brickheadz" / "figures.json").read_text())
    num, fig = src.split(":")
    f = next((x for x in figs if x["num"] == num and x["fig"] == int(fig)), None)
    if f is None:
        raise HTTPException(404, "cible inconnue")
    return F.target_from_placed(f["placed"])


def _run(job):
    from brickforge import fill as F
    try:
        lib = F.library()
        T = job["T"]

        def ev(e):
            if e["t"] == "place_raw":
                out = {"t": "place", "part": e["part"], "m": e["m"], "pass": e["pass"], "level": e["level"], "gain": round(e["gain"], 1), "side": True}
                with _LOCK:
                    job["events"].append(out)
                return
            if e["t"] == "place":
                p = e["piece"]
                pl = F.to_placed([p], lib)[0]
                out = {"t": "place", "part": pl["part"], "m": pl["m"], "pass": e["pass"], "level": e["level"], "gain": round(e["gain"], 1)}
            else:
                out = e
            with _LOCK:
                job["events"].append(out)

        a = job["args"]
        t0 = time.time()
        placed, occ, info = F.solve(T, a["lam"], a["ratio"], relax=a["relax"], snot=a.get("snot", True), on_event=ev)
        pieces = placed
        from brickforge import buildcheck
        chk = buildcheck.check(placed) if placed else {"floating": [], "collisions": []}
        with _LOCK:
            job["events"].append({"t": "done", "pieces": len(pieces), "sil": F.silhouettes(T, occ), "seconds": round(time.time() - t0, 1),
                                  "floating": len(chk["floating"]), "collisions": len(chk["collisions"])})
            job["done"] = True
    except Exception as ex:                                     # visible dans la page
        with _LOCK:
            job["events"].append({"t": "error", "msg": f"{type(ex).__name__}: {ex}"})
            job["done"] = True


@router.post("/api/fill/run")
def run(body: dict = Body(...)):
    from brickforge import fill as F
    src = str(body.get("src", ""))
    args = {"lam": float(body.get("lam", 2.0)), "ratio": float(body.get("ratio", 0.6)),
            "relax": float(body.get("relax", 0.5)), "passes": int(body.get("passes", 3)),
            "snot": bool(body.get("snot", True))}
    T = _target(src, body.get("plates"))
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "src": src, "args": args, "T": T, "events": [], "done": False, "started": time.time()}
    with _LOCK:
        for k in [k for k, j in JOBS.items() if j["done"] and time.time() - j["started"] > 3600]:
            del JOBS[k]
        JOBS[jid] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return {"job": jid, "grid": {"cx": F.CX, "cy": F.CY, "c0": F.C0, "n": F.N, "ny": F.NY}}


@router.get("/api/fill/job/{jid}")
def job_events(jid: str, since: int = 0):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "calcul inconnu")
    with _LOCK:
        ev = job["events"][since:]
        n = len(job["events"])
    return {"events": ev, "next": n, "done": job["done"]}


@router.get("/api/fill/job/{jid}/target")
def job_target(jid: str):
    from brickforge import fill as F
    from scipy import ndimage
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "calcul inconnu")
    T = job["T"]
    surf = T & ~ndimage.binary_erosion(T)
    idx = np.argwhere(surf)
    return {"cells": idx.tolist(), "cx": F.CX, "cy": F.CY, "c0": F.C0, "total": int(T.sum())}
