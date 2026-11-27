"""Explorateur des vrais sets LEGO de l'OMR LDraw (library.ldraw.org/omr).

    data/omr/index.json                 catalogue (1 472 sets : numéro, nom, thème, année, nb de modèles, vignette)
    data/omr/thumbs/<id>.png            vignettes mises en cache
    data/omr/<num>/<fichier>.mpd        modèles téléchargés à la demande (licence CCAL 2.0)
    data/omr/<num>/<fichier>.json       modèle aplati : pièces, couleurs, étapes, sous-modèles
    data/rebrickable/rb.sqlite          tous les sets LEGO (~20 000 avec pièces) + inventaires (brickforge/rebrickable.py)
    data/rebrickable/thumbs/<num>.jpg   vignettes des sets sans 3D
"""

from __future__ import annotations

import json
import re
import threading
import urllib.request
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from brickforge import omr, rebrickable

ROOT = Path(__file__).resolve().parent.parent
OMR = ROOT / "data" / "omr"
LDCONFIG = ROOT / "data" / "ldraw" / "LDConfig.ldr"
BASE = "https://library.ldraw.org"
UA = {"User-Agent": "brickforge-explorer/0.1"}

router = APIRouter()
_lock = threading.Lock()
_index: list[dict] | None = None
SUMMARY_V = 2          # à incrémenter quand le format du modèle aplati change


def _get(url: str, timeout: int = 60) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def index() -> list[dict]:
    global _index
    if _index is None:
        _index = json.loads((OMR / "index.json").read_text())
        # nombre de pièces officiel (boîte) : catalogue Rebrickable data/rebrickable/sets.csv.gz
        rb = ROOT / "data" / "rebrickable" / "sets.csv.gz"
        if rb.exists():
            import csv, gzip
            n = {r["set_num"]: int(r["num_parts"]) for r in csv.DictReader(gzip.open(rb, "rt", encoding="utf-8"))}
            for r in _index:
                if r["num"] in n:
                    r["pieces"] = n[r["num"]]
        # sets publiés sur le forum LDraw, pas encore dans l'OMR (brickforge/ldforum.py) : fichiers déjà sur disque
        fi = OMR / "forum_index.json"
        if fi.exists():
            known = {r["num"] for r in _index}
            _index += [{"id": None, "num": r["num"], "name": r["name"], "theme": r["theme"], "year": r["year"],
                        "models": r["models"], "pieces": r["pieces"], "source": "forum",
                        "thread": r["files"][0]["thread"]} for r in json.loads(fi.read_text()) if r["num"] not in known]
    return _index


def _thumb_url(r: dict) -> str:
    return f"/rb-thumb/{r['num']}.jpg" if r.get("source") == "forum" else f"/omr-thumb/{r['id']}.png?v=2"


def _set(num: str) -> dict:
    s = next((r for r in index() if r["num"] == num), None)
    if not s:
        raise HTTPException(404, f"set {num} absent de l'OMR")
    return s


def _summary(num: str, stem: str, mpd: Path) -> dict:
    """Modèle aplati, mis en cache à côté du .mpd."""
    js = mpd.with_suffix(".json")
    if js.exists() and js.stat().st_mtime >= mpd.stat().st_mtime:
        d = json.loads(js.read_text())
        if d.get("v") == SUMMARY_V:
            return d
    main, files = omr.parse_mpd(mpd)
    parts = omr.flatten(main, files)
    head = files[main]
    meta = lambda k: next((l.split(k, 1)[1].strip() for l in head if l.startswith("0 " + k)), "")
    alt = stem[len(num) + 1:].replace("-", " ") if stem.startswith(num + "_") else ""
    d = {"v": SUMMARY_V, "num": num, "file": stem, "title": alt or "Modèle principal",
         "author": meta("Author:"), "keywords": meta("!KEYWORDS"),
         "steps": max((p["step"] for p in parts), default=-1) + 1,
         "subs": [s.removeprefix(num.split("-")[0] + " - ") for s in dict.fromkeys(p["sub"] for p in parts)],
         "parts": [{"part": p["part"], "color": p["color"], "m": p["m"], "step": p["step"], "sub": p["sub"]} for p in parts]}
    js.write_text(json.dumps(d, ensure_ascii=False))
    return d


def ensure_set(num: str) -> list[Path]:
    """Télécharge (une fois) les .mpd du set depuis sa page OMR."""
    s = _set(num)
    d = _dir(num)
    have = sorted(d.glob("*.mpd")) if d.exists() else []
    if have or s.get("source") == "forum":
        return have
    with _lock:
        page = _get(f"{BASE}/omr/sets/{s['id']}").decode(errors="ignore")
        links = list(dict.fromkeys(re.findall(r'href="(https://library\.ldraw\.org/media/omr_models/\d+/[^"?]+\.mpd)', page)))
        if not links:
            raise HTTPException(502, "aucun fichier .mpd sur la page OMR de ce set")
        d.mkdir(parents=True, exist_ok=True)
        for u in links:
            (d / u.rsplit("/", 1)[1]).write_bytes(_get(u))
    return sorted(d.glob("*.mpd"))


def _dir(num: str) -> Path:
    short = OMR / num.split("-")[0]
    return short if num.endswith("-1") and short.exists() else OMR / num


# ---------------------------------------------------------------- routes

@router.get("/api/omr/sets")
def omr_sets():
    out = []
    for r in index():
        d = _dir(r["num"])
        js = sorted(d.glob("*.json")) if d.exists() else []
        extra = {}
        if js:
            try:
                first = json.loads(js[0].read_text())
                extra = {"parts": len(first["parts"]), "keywords": first.get("keywords", "")}
            except (OSError, ValueError, KeyError):
                pass
        out.append({**r, "thumb": _thumb_url(r), "downloaded": bool(js) or (d.exists() and any(d.glob("*.mpd"))), **extra})
    return out


def _thumb(p: Path, urls):
    """Vignette 360 px mise en cache : première URL qui répond."""
    if not p.exists():
        import cv2
        import numpy as np
        p.parent.mkdir(parents=True, exist_ok=True)
        img = None
        for url in urls:
            if not url:
                continue
            try:
                img = cv2.imdecode(np.frombuffer(_get(url, 30), np.uint8), cv2.IMREAD_UNCHANGED)
            except OSError:
                img = None
            if img is not None:
                break
        if img is None:
            raise HTTPException(502, "vignette introuvable")
        if img.ndim == 3 and img.shape[2] == 4:          # PNG transparent → fond blanc
            a = img[:, :, 3:] / 255.0
            img = (img[:, :, :3] * a + 255 * (1 - a)).astype(np.uint8)
        s = 360 / max(img.shape[:2])
        if s < 1:
            img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/omr-thumb/{sid}.png")
def omr_thumb(sid: int):
    """Photo officielle du set (Rebrickable), sinon la vignette OMR."""
    r = next((x for x in index() if x["id"] == sid), None)
    if not r:
        raise HTTPException(404)
    return _thumb(OMR / "thumbs" / f"{sid}.jpg", (f"https://cdn.rebrickable.com/media/sets/{r['num']}.jpg", r.get("thumb")))


# ---------------------------------------------------------------- catalogue complet (Rebrickable) : 3D OMR quand elle existe, sinon inventaire

_rb = None


def rb():
    global _rb
    if _rb is None:
        _rb = rebrickable.connect()
    return _rb


@router.get("/api/sets")
def sets_catalog():
    """Tous les sets avec au moins une pièce. src = "omr" (3D + notice) ou "rb" (inventaire seulement)."""
    omr_by = {s["num"]: s for s in omr_sets()}
    out = []
    for r in rb().execute("SELECT num, name, year, theme, pieces, img FROM sets WHERE pieces > 0 AND inv IS NOT NULL"):
        o = omr_by.pop(r["num"], None)
        if o:
            out.append({**o, "name": r["name"], "theme": r["theme"], "pieces": r["pieces"], "src": "omr"})
        else:
            out.append({"num": r["num"], "name": r["name"], "year": r["year"], "theme": r["theme"], "pieces": r["pieces"],
                        "thumb": f"/rb-thumb/{r['num']}.jpg", "src": "rb"})
    out += [{**o, "src": "omr"} for o in omr_by.values()]      # sets OMR absents de Rebrickable (rare)
    return out


@router.get("/rb-thumb/{num}.jpg")
def rb_thumb(num: str):
    r = rb().execute("SELECT img FROM sets WHERE num = ?", (num,)).fetchone()
    if not r:
        raise HTTPException(404)
    safe = re.sub(r"[^\w.-]", "_", num)
    return _thumb(rebrickable.RB / "thumbs" / f"{safe}.jpg", (r["img"],))


@router.get("/api/rb/set/{num}")
def rb_set(num: str):
    """Inventaire officiel d'un set : pièces (référence, couleur, quantité, photo), pièces de rechange à part, minifigs."""
    db = rb()
    s = db.execute("SELECT * FROM sets WHERE num = ?", (num,)).fetchone()
    if not s:
        raise HTTPException(404, f"set {num} inconnu")
    parts = [dict(r) for r in db.execute("""
        SELECT i.part, p.name, i.color, c.name AS cname, c.rgb, c.trans, SUM(i.qty) AS qty, i.spare, MAX(i.img) AS img
        FROM inv i LEFT JOIN parts p ON p.part = i.part LEFT JOIN colors c ON c.id = i.color
        WHERE i.inv = ? GROUP BY i.part, i.color, i.spare ORDER BY qty DESC, i.part""", (s["inv"],))]
    figs = [dict(r) for r in db.execute("""
        SELECT f.fig, f.qty, m.name, m.pieces, m.img FROM figs f LEFT JOIN minifigs m ON m.fig = f.fig WHERE f.inv = ?""", (s["inv"],))]
    main = [p for p in parts if not p["spare"]]
    return {"num": s["num"], "name": s["name"], "year": s["year"], "theme": s["theme"], "pieces": s["pieces"], "img": s["img"],
            "thumb": f"/rb-thumb/{s['num']}.jpg", "parts": main, "spares": [p for p in parts if p["spare"]], "minifigs": figs,
            "unique": len({p["part"] for p in main}), "colors": len({p["color"] for p in main}),
            "count": sum(p["qty"] for p in main), "omr": any(x["num"] == num for x in index())}


@router.get("/api/omr/set/{num}")
def omr_set(num: str):
    s = _set(num)
    models = []
    for mpd in ensure_set(num):
        m = _summary(num, mpd.stem, mpd)
        cnt = Counter(p["part"] for p in m["parts"])
        models.append({"file": mpd.stem, "title": m["title"], "author": m["author"], "keywords": m["keywords"],
                       "parts": len(m["parts"]), "unique": len(cnt), "steps": m["steps"], "subs": m["subs"],
                       "colors": len({p["color"] for p in m["parts"]})})
    return {**s, "thumb": _thumb_url(s), "models": models}


@router.get("/api/omr/set/{num}/model/{stem}")
def omr_model(num: str, stem: str):
    mpd = _dir(num) / f"{stem}.mpd"
    if not mpd.exists():
        ensure_set(num)
    if not mpd.exists():
        raise HTTPException(404)
    return _summary(num, stem, mpd)


@router.get("/api/omr/set/{num}/model/{stem}.mpd")
def omr_mpd(num: str, stem: str):
    mpd = _dir(num) / f"{stem}.mpd"
    if not mpd.exists():
        raise HTTPException(404)
    return FileResponse(mpd, filename=mpd.name)


@router.post("/api/omr/set/{num}/model/{stem}/subject")
def omr_to_subject(num: str, stem: str):
    """Copie le modèle en sujet Brick Forge (assembleur, comparaison) avec la photo officielle."""
    mpd = _dir(num) / f"{stem}.mpd"
    if not mpd.exists():
        raise HTTPException(404)
    s = _set(num)
    name = "lego_omr_" + re.sub(r"[^a-z0-9]+", "_", f"{num.split('-')[0]} {s['name']}".lower()).strip("_")[:40]
    if stem.startswith(num + "_"):        # modèle alternatif (3-en-1…)
        name += "_" + re.sub(r"[^a-z0-9]+", "_", stem[len(num) + 1:].lower()).strip("_")
    photo = f"https://cdn.rebrickable.com/media/sets/{num}.jpg"
    try:
        omr.import_set(mpd, name, photo)
    except OSError:
        omr.import_set(mpd, name, None)
    return {"subject": name}


_ldcolors: dict | None = None


@router.get("/api/ldcolors")
def ldcolors():
    """Toutes les couleurs LDraw (code → hex, alpha) lues dans LDConfig.ldr."""
    global _ldcolors
    if _ldcolors is None:
        _ldcolors = {}
        for l in LDCONFIG.read_text(errors="ignore").splitlines():
            m = re.match(r"0 !COLOUR (\S+)\s+CODE\s+(\d+)\s+VALUE\s+#([0-9A-Fa-f]{6})(.*)", l)
            if m:
                a = re.search(r"ALPHA\s+(\d+)", m.group(4))
                _ldcolors[int(m.group(2))] = {"name": m.group(1).replace("_", " "), "hex": "#" + m.group(3),
                                              "alpha": int(a.group(1)) / 255 if a else 1}
    return _ldcolors


# ---------------------------------------------------------------- rendu photoréaliste (Blender Cycles)

import hashlib  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402

RENDERS = ROOT / "out" / "renders"
BLENDER = next((str(p) for p in (Path.home() / ".local" / "bin" / "blender", Path("/usr/bin/blender")) if p.exists()), "blender")
QUALITY = {"apercu": {"width": 960, "samples": 40}, "hd": {"width": 1920, "samples": 160}}
_render_lock = threading.Lock()
_rate = {"k": 0.5}          # secondes par (échantillon × mégapixel), recalibré après chaque rendu (Blender 5 n'affiche pas l'avancement)


def _estimate(parts: int, q: dict) -> float:
    mp = q["width"] * q["width"] / 1.6 / 1e6
    return 4 + parts * 0.012 + q["samples"] * mp * _rate["k"]
_jobs: dict[str, dict] = {}


def _run_render(rid: str, job_path: Path):
    st = _jobs[rid]
    with _render_lock:                      # un rendu à la fois (mémoire et processeur)
        st.update(state="rendu", t0=time.time(), eta=_estimate(st["parts"], st["q"]))
        p = subprocess.Popen([BLENDER, "-b", "--factory-startup", "-P", str(ROOT / "brickforge" / "blender_render.py"), "--", str(job_path)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
        log = []
        for line in p.stdout:
            log.append(line)
            m = re.search(r"Sample (\d+)/(\d+)", line)
            if m:
                st["progress"] = int(m.group(1)) / max(1, int(m.group(2)))
            elif line.startswith("BF parts"):
                st["stage"] = "éclairage et rendu"
        p.wait()
        out = RENDERS / f"{rid}.png"
        if p.returncode == 0 and out.exists():
            dt = time.time() - st["t0"]
            q = st["q"]
            mp = q["width"] * q["width"] / 1.6 / 1e6
            _rate["k"] = max(0.05, (dt - 4 - st["parts"] * 0.012) / (q["samples"] * mp))
            st.update(state="terminé", progress=1, url=f"/renders/{rid}.png?t={int(time.time())}", seconds=round(dt))
        else:
            st.update(state="erreur", error="".join(log[-15:]))


@router.post("/api/render")
def start_render(body: dict = Body(...)):
    """Lance un rendu Cycles : body = {parts: [{part, color, m}], camera: {pos, target, fov, aspect}, quality, name}."""
    parts = [{"part": p["part"], "color": int(p["color"]), "m": [float(v) for v in p["m"]]} for p in body["parts"][:6000]]
    if not parts:
        raise HTTPException(400, "aucune pièce à rendre")
    q = QUALITY.get(body.get("quality"), QUALITY["apercu"])
    cam = body["camera"]
    key = json.dumps([parts, cam, q], sort_keys=True)
    rid = re.sub(r"[^a-z0-9_-]+", "-", (body.get("name") or "rendu").lower())[:40] + "-" + hashlib.sha1(key.encode()).hexdigest()[:10]
    if rid in _jobs and _jobs[rid]["state"] != "erreur":          # même scène : on réutilise
        return {"id": rid, **{k: v for k, v in _jobs[rid].items() if k not in ("t0", "q")}}
    if (RENDERS / f"{rid}.png").exists():
        return {"id": rid, "state": "terminé", "progress": 1, "url": f"/renders/{rid}.png"}
    RENDERS.mkdir(parents=True, exist_ok=True)
    job = RENDERS / f"{rid}.json"
    job.write_text(json.dumps({"parts": parts, "camera": cam, "out": str(RENDERS / f"{rid}.png"), **q}))
    _jobs[rid] = {"state": "attente", "progress": 0, "stage": "préparation des pièces (biseaux)", "parts": len(parts), "quality": body.get("quality", "apercu"), "q": q}
    threading.Thread(target=_run_render, args=(rid, job), daemon=True).start()
    return {"id": rid, **_jobs[rid]}


@router.get("/api/render/{rid}")
def render_status(rid: str):
    if rid not in _jobs:
        if (RENDERS / f"{rid}.png").exists():
            return {"id": rid, "state": "terminé", "progress": 1, "url": f"/renders/{rid}.png"}
        raise HTTPException(404)
    st = _jobs[rid]
    out = {k: v for k, v in st.items() if k not in ("t0", "q")}
    if st["state"] == "rendu":
        el = time.time() - st["t0"]
        out["progress"] = min(0.97, el / st["eta"])
        out["remaining"] = max(0, round(st["eta"] - el))
    return {"id": rid, **out}


@router.get("/renders/{name}")
def render_file(name: str):
    p = RENDERS / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@router.post("/api/scene-glb")
def scene_glb(body: dict = Body(...)):
    """Modèle biseauté exporté par Blender en glTF, pour le rendu progressif du navigateur (mis en cache)."""
    parts = [{"part": p["part"], "color": int(p["color"]), "m": [float(v) for v in p["m"]]} for p in body["parts"][:6000]]
    if not parts:
        raise HTTPException(400, "aucune pièce")
    key = hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]
    out = RENDERS / f"scene-{key}.glb"
    if not out.exists():
        RENDERS.mkdir(parents=True, exist_ok=True)
        job = RENDERS / f"scene-{key}.json"
        job.write_text(json.dumps({"parts": parts, "glb": str(out)}))
        with _render_lock:
            r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(ROOT / "brickforge" / "blender_render.py"), "--", str(job)],
                               capture_output=True, text=True, cwd=ROOT, timeout=900)
        if not out.exists():
            raise HTTPException(500, "export Blender échoué : " + (r.stdout + r.stderr)[-400:])
    return {"url": f"/renders/{out.name}", "bytes": out.stat().st_size}

