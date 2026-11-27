"""Bac à sable : moteur réel (points d'accroche, collisions au voxel) et import de modèles.

    GET  /api/snaps?parts=3001,22885        points d'accroche de chaque pièce (repère de la pièce)
    POST /api/sandbox-fit                   {parts, cand:{part,m}} → la pièce candidate tient-elle ? traverse-t-elle une autre pièce ?
    POST /api/sandbox-sources               (GET) modèles importables : BrickHeadz officielles, modèles du cahier
    POST /api/sandbox-import                {source: ldr|official|model, text|id} → {parts}

La vérification complète (/api/sandbox/{name}/check) appelle `check_doc` : une pièce est « au sol » si elle touche la plaque
de base (y = 0) ; elle vole si elle n'est reliée à aucune pièce au sol ; collisions = matière qui traverse (moteur buildcheck).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Body, HTTPException

ROOT = Path(__file__).resolve().parent.parent
router = APIRouter()


def _snaps(part):
    from brickforge.buildcheck import part_snaps
    out = []
    for s in part_snaps(part):
        if s["g"] not in ("M", "F"):
            continue
        out.append({"g": s["g"], "pos": [round(float(v), 3) for v in s["pos"]], "axis": [round(float(v), 4) for v in s["axis"]],
                    "slide": bool(s.get("slide"))})
    return out


@router.get("/api/snaps")
def snaps(parts: str):
    res = {}
    for p in parts.split(",")[:200]:
        p = p.strip()
        if not p:
            continue
        try:
            res[p] = _snaps(p)
        except Exception:
            res[p] = []
    return res


def _same(a, b):
    return a["part"] == b["part"] and all(abs(x - y) < 1.0 for x, y in zip(a["m"], b["m"]))


def _vol(part):
    from brickforge.buildcheck import solid
    sl = solid(part)
    return int(sl[0].sum()) if sl is not None else 0


def _clash(a, b, linked):
    """Collision pour le bac à sable : même pièce au même endroit, ou matière qui se traverse. Le seuil du moteur (30 voxels,
    réglé sur les vraies LEGO) devient relatif pour les petites pièces ; deux pièces reliées ne se traversent que de beaucoup."""
    from brickforge.buildcheck import COLL_MIN, _penetration
    if _same(a, b):
        return True
    n = _penetration(a, b) + _penetration(b, a)
    small = max(1, min(_vol(a["part"]), _vol(b["part"])))
    if linked:
        return n >= 0.5 * small
    return n >= COLL_MIN or (n >= 4 and n >= 0.15 * small)


def _placed(parts):
    return [{"part": p["part"], "color": p.get("color", 71), "m": [float(v) for v in p["m"]]} for p in parts]


@router.post("/api/sandbox-fit")
def fit(body: dict = Body(...)):
    """La pièce candidate : reliée à combien de pièces (ou à la plaque de base), et quelles pièces elle traverse."""
    from brickforge.buildcheck import PEN_LDU, _bbox_world, links_between, world_snaps
    parts = _placed(body.get("parts", []))
    cand = _placed([body["cand"]])[0]
    cb = _bbox_world(cand)
    if cb is None:
        return {"ok": False, "links": 0, "ground": False, "collisions": []}
    near = []
    for i, p in enumerate(parts):
        b = _bbox_world(p)
        if b is not None and ((np.minimum(cb[1], b[1]) - np.maximum(cb[0], b[0])) > -4).all():
            near.append(i)
    sub = [parts[i] for i in near]
    wc = world_snaps([cand])
    ws = world_snaps(sub)
    linked = {near[ws[ib][0]] for _, ib in links_between(wc, ws)} if ws and wc else set()
    coll = []
    for i in near:
        b = _bbox_world(parts[i])
        if ((np.minimum(cb[1], b[1]) - np.maximum(cb[0], b[0])) <= PEN_LDU).any():
            continue
        if _clash(cand, parts[i], i in linked):
            coll.append(body["parts"][i].get("id", i))
    linked = {i for i in linked if not _same(cand, parts[i])}
    ground = bool(abs(cb[1][1]) < 1.0)                           # le dessous de la pièce touche la plaque de base (y = 0)
    return {"ok": not coll and (bool(linked) or ground), "links": len(linked), "ground": ground, "collisions": coll}


def check_doc(parts_in):
    """Vérification complète avec le moteur réel."""
    from brickforge.buildcheck import _bbox_world, collisions, connections
    parts = _placed(parts_in)
    if not parts:
        return {"floating": [], "overlap": [], "total": 0}
    boxes = [_bbox_world(p) for p in parts]
    edges, _ = connections(parts)
    par = list(range(len(parts)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for a, b in edges:
        par[find(a)] = find(b)
    grounded = {find(i) for i, b in enumerate(boxes) if b is not None and abs(b[1][1]) < 1.0}
    floating = [i for i in range(len(parts)) if find(i) not in grounded]
    coll = collisions(parts, boxes, frozenset(edges))
    for i in range(len(parts)):                                   # doublons exacts (même pièce, même place)
        for j in range(i + 1, len(parts)):
            if _same(parts[i], parts[j]):
                coll.append((i, j, 0))
    ov = sorted({i for c in coll for i in c[:2]})
    ids = [p.get("id", i) for i, p in enumerate(parts_in)]
    return {"floating": [ids[i] for i in floating], "overlap": [ids[i] for i in ov], "total": len(parts),
            "pairs": [[ids[a], ids[b], n] for a, b, n in coll]}


# ---------------------------------------------------------------- import

def _figs():
    return json.loads((ROOT / "data" / "brickheadz" / "figures.json").read_text())


@router.get("/api/sandbox-sources")
def sources():
    off = [{"id": f"{f['num']}:{f['fig']}", "label": f"{f['set']}" + (f" ({f['fig'] + 1}/{f['nfigs']})" if f.get("nfigs", 1) > 1 else "")
            + f" · {f['num']} · {len(f['placed'])} pièces"} for f in _figs()]
    models = []
    for p in sorted((ROOT / "data" / "defi_costume").glob("v*.json")):
        d = json.loads(p.read_text())
        models.append({"id": f"defi:{p.stem}", "label": f"Défi costume {p.stem} · {len(d['placed'])} pièces"})
    for d in sorted((ROOT / "data" / "hunyuan").glob("*")):
        for name, lab in (("fill.json", "remplissage optimisé"), ("build.json", "couches")):
            f = d / name
            if f.exists():
                n = len(json.loads(f.read_text()).get("placed", []))
                models.append({"id": f"hy:{d.name}:{name}", "label": f"{d.name} · {lab} · {n} pièces"})
    return {"official": off, "models": models}


def parse_ldr(text):
    """LDraw / MPD → pièces à plat (sous-modèles dépliés, matrices composées)."""
    files, cur, main = {}, None, None
    for line in text.splitlines():
        s = line.strip()
        if s.lower().startswith("0 file "):
            cur = s[7:].strip().lower()
            files[cur] = []
            main = main or cur
            continue
        if cur is None:
            cur = main = "__main__"
            files[cur] = []
        files[cur].append(s)
    out = []

    def walk(name, M, o, color, depth):
        if depth > 8:
            return
        for s in files.get(name, []):
            t = s.split()
            if len(t) < 15 or t[0] != "1":
                continue
            c = int(t[1]) if t[1].lstrip("-").isdigit() else 16
            c = color if c == 16 else c
            v = [float(x) for x in t[2:14]]
            ref = " ".join(t[14:]).lower().replace("\\", "/")
            Ml = np.array(v[3:]).reshape(3, 3)
            ol = np.array(v[:3])
            Mw, ow = M @ Ml, M @ ol + o
            if ref in files:
                walk(ref, Mw, ow, c, depth + 1)
            else:
                part = re.sub(r"\.dat$", "", ref.split("/")[-1])
                out.append({"part": part, "color": c, "m": [round(float(x), 4) for x in list(ow) + list(Mw.flatten())]})
    walk(main, np.eye(3), np.zeros(3), 16, 0)
    return out


def _ground(parts):
    """Poser le modèle sur la plaque de base : le point le plus bas à y = 0."""
    from brickforge.buildcheck import _bbox_world
    ys = [b[1][1] for b in (_bbox_world(p) for p in parts) if b is not None]
    if not ys:
        return parts
    dy = -max(ys)
    return [{**p, "m": [p["m"][0], p["m"][1] + dy, p["m"][2]] + list(p["m"][3:])} for p in parts]


@router.post("/api/sandbox-import")
def do_import(body: dict = Body(...)):
    src = body.get("source")
    if src == "ldr":
        parts = parse_ldr(str(body.get("text", "")))
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", str(body.get("name", "import")))[:40] or "import"
    elif src == "official":
        f = next((x for x in _figs() if f"{x['num']}:{x['fig']}" == body.get("id")), None)
        if f is None:
            raise HTTPException(404, "officielle inconnue")
        parts = [{"part": p["part"], "color": p.get("color", 71), "m": p["m"]} for p in f["placed"]]
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", f"{f['set']}-{f['fig'] + 1}")[:40]
    elif src == "model":
        mid = str(body.get("id", ""))
        if mid.startswith("defi:"):
            f = ROOT / "data" / "defi_costume" / f"{mid[5:]}.json"
            name = f"defi-costume-{mid[5:]}"
        elif mid.startswith("hy:"):
            _, d, fn = mid.split(":")
            f = ROOT / "data" / "hunyuan" / Path(d).name / Path(fn).name
            name = f"{Path(d).name}-{Path(fn).stem}"
        else:
            raise HTTPException(404, "modèle inconnu")
        if not f.exists():
            raise HTTPException(404, "modèle introuvable")
        parts = [{"part": p["part"], "color": p.get("color", 71), "m": p["m"]} for p in json.loads(f.read_text())["placed"]]
    else:
        raise HTTPException(400, "source inconnue")
    if not parts:
        raise HTTPException(400, "aucune pièce trouvée")
    parts = _ground(parts)
    for i, p in enumerate(parts):
        p.update({"id": f"i{i:04d}", "src": src, "status": "ok"})
    return {"name": name.lower(), "parts": parts}
