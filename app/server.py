"""Brick Forge Lab : app locale pour lancer, visualiser, corriger et mesurer.

Lancement :
    .venv/bin/python -m app.server        (puis http://127.0.0.1:8000)

Données :
    imgs/<sujet>/<vue>.jpeg                  vues sources
    imgs/<sujet>/gt_<vue>.json               vérité terrain (éditée dans l'app)
    out/runs/<sujet>/<id>/                   un lancement : segments, pièces, modèle 3D, méta
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import threading
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from brickforge import colors
from brickforge.evaluate import evaluate, load_gt

ROOT = Path(__file__).resolve().parent.parent
COMPARE_DIR = ROOT / "out" / "compare"
RESEARCH = ROOT / "research"
THUMBS = ROOT / "out" / "thumbs"
IMGS = ROOT / "imgs"
RUNS = ROOT / "out" / "runs"
STATIC = Path(__file__).resolve().parent / "static"
PY = str(ROOT / ".venv" / "bin" / "python")
VIEW_ORDER = ["photo", "concept", "dessus", "profil", "face", "dos", "dessous"]
MAIN_VIEW = "dessus"

def _local_cfg(key, default=""):
    """Réglages propres à la machine (non versionnés) : variable d'environnement, sinon fichier .brickforge.local (CLE=valeur)."""
    import os
    if os.environ.get(key):
        return os.environ[key]
    f = Path(__file__).resolve().parent.parent / ".brickforge.local"
    for line in (f.read_text().splitlines() if f.exists() else []):
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip()
    return default


REMOTE = _local_cfg("BRICKFORGE_REMOTE")                         # machine de calcul distante (utilisateur@hôte), clé SSH
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-i", str(Path.home() / ".ssh" / "id_ed25519")]
MODELS = {
    "mobile": {"label": "MobileSAM (ce PC)", "remote": False},
    "vit_h": {"label": "SAM complet (Mac Studio)", "remote": True},
}

app = FastAPI(title="Brick Forge Lab")
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
app.add_middleware(GZipMiddleware, minimum_size=2048)


# ---------------------------------------------------------------- utilitaires

def view_path(subject: str, view: str) -> Path | None:
    for ext in (".jpeg", ".jpg", ".png", ".webp"):
        p = IMGS / subject / f"{view}{ext}"
        if p.exists():
            return p
    return None


_size_cache: dict[str, tuple[int, int]] = {}


def image_size(path: Path) -> tuple[int, int]:
    key = f"{path}:{path.stat().st_mtime}"
    if key not in _size_cache:
        h, w = cv2.imread(str(path)).shape[:2]
        _size_cache[key] = (w, h)
    return _size_cache[key]


def code_version() -> str:
    h = hashlib.sha1()
    for f in sorted((ROOT / "brickforge").glob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:8]


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def run_dirs(subject: str) -> list[Path]:
    d = RUNS / subject
    return sorted([p for p in d.iterdir() if (p / "meta.json").exists()], reverse=True) if d.exists() else []


def run_summary(subject: str, rd: Path, gt: dict | None) -> dict:
    meta = read_json(rd / "meta.json", {})
    pieces = read_json(rd / "pieces.json")
    out = dict(meta)
    out["has_pieces"] = pieces is not None
    out["has_model"] = (rd / "model.json").exists()
    if pieces is not None:
        out["n_pred"] = len(pieces)
        out["kinds"] = dict(Counter(p["kind"].rstrip("?") for p in pieces))
        out["unknown"] = sum(1 for p in pieces if not p.get("part"))
        if gt and gt.get("pieces"):
            img = view_path(subject, MAIN_VIEW)
            m = evaluate(gt, pieces, image_size(img))
            m.pop("pairs", None)
            m.pop("errors", None)
            out["metrics"] = m
    model = read_json(rd / "model.json")
    if model:
        out["model_parts"] = model.get("nParts")
    return out


# ---------------------------------------------------------------- tâches de fond

JOBS: list[dict] = []
_job_lock = threading.Lock()


def _log(job, msg):
    job["log"].append(f"{datetime.now():%H:%M:%S} {msg}")
    job["step"] = msg


def _sh(job, cmd, **kw):
    _log(job, "$ " + " ".join(str(c) for c in cmd)[:160])
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    tail = [l for l in (r.stdout + r.stderr).splitlines() if "warn" not in l.lower()][-6:]
    job["log"] += tail
    if r.returncode != 0:
        raise RuntimeError(f"échec ({r.returncode}) : {' '.join(tail[-2:])}")
    return r


def _find_reusable_segments(subject: str, model: str, img: Path) -> Path | None:
    for rd in run_dirs(subject):
        meta = read_json(rd / "meta.json", {})
        seg = rd / "segments.npz"
        if meta.get("model") == model and seg.exists() and seg.stat().st_mtime > img.stat().st_mtime:
            return rd
    return None


def _run_job(job):
    subject, model, reuse = job["subject"], job["model"], job["reuse"]
    rid = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{model}"
    rd = RUNS / subject / rid
    rd.mkdir(parents=True, exist_ok=True)
    meta = {"id": rid, "subject": subject, "model": model, "model_label": MODELS[model]["label"],
            "label": job.get("label") or "", "created": datetime.now().isoformat(timespec="seconds"),
            "code": code_version(), "status": "en cours", "timings": {}}
    (rd / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    job["run"] = rid
    img = view_path(subject, MAIN_VIEW)
    try:
        if img is None:
            raise RuntimeError(f"pas de vue « {MAIN_VIEW} » pour {subject}")
        # 1. Découpage
        t0 = time.time()
        prev = _find_reusable_segments(subject, model, img) if reuse else None
        if prev is not None and prev != rd:
            _log(job, f"découpage réutilisé depuis {prev.name}")
            shutil.copy(prev / "segments.npz", rd / "segments.npz")
            if (prev / "segments.jpg").exists():
                shutil.copy(prev / "segments.jpg", rd / "segments.jpg")
            meta["segments_from"] = prev.name
        elif MODELS[model]["remote"]:
            _log(job, "envoi du code et des images au Mac Studio")
            rsh = " ".join(SSH)
            _sh(job, ["rsync", "-az", "-e", rsh, "--exclude", "__pycache__", str(ROOT / "brickforge"),
                      f"{REMOTE}:brickforge/"])
            _sh(job, ["rsync", "-az", "-e", rsh, str(IMGS / subject), f"{REMOTE}:brickforge/imgs/"])
            _log(job, "découpage SAM complet sur le Mac Studio")
            rel = f"imgs/{subject}/{img.name}"
            _sh(job, SSH + [REMOTE, f"cd ~/brickforge && PYTORCH_ENABLE_MPS_FALLBACK=1 env/bin/python -m "
                                    f"brickforge.segment {rel} --model {model} --points 64 --out runs/{rid} --name segments"],
                timeout=3600)
            _sh(job, ["rsync", "-az", "-e", rsh, f"{REMOTE}:brickforge/runs/{rid}/", str(rd) + "/"])
        else:
            _log(job, "découpage MobileSAM sur ce PC (mémoire limitée à 3 Go)")
            _sh(job, ["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=3G", "-p", "MemorySwapMax=0",
                      PY, "-m", "brickforge.segment", str(img), "--model", model, "--out", str(rd), "--name", "segments"],
                cwd=ROOT, timeout=3600)
        meta["timings"]["decoupage_s"] = round(time.time() - t0)

        # 2. Reconnaissance des pièces
        t0 = time.time()
        _log(job, "reconnaissance des pièces")
        _sh(job, [PY, "-c", f"from pathlib import Path; from brickforge.identify import identify; "
                            f"identify(Path({str(img)!r}), Path({str(rd / 'segments.npz')!r}), Path({str(rd)!r}), stem='pieces')"],
            cwd=ROOT, timeout=1800)
        meta["timings"]["reconnaissance_s"] = round(time.time() - t0)

        # 3. Modèle 3D (pipeline voxels actuel)
        if all(view_path(subject, v) for v in ("dessus", "profil", "face")):
            t0 = time.time()
            _log(job, "modèle 3D")
            _sh(job, [PY, "-m", "app.model3d", subject, str(rd / "model.json")], cwd=ROOT, timeout=1800)
            meta["timings"]["modele_s"] = round(time.time() - t0)
        meta["status"] = "terminé"
        job["status"] = "terminé"
        _log(job, "terminé")
    except Exception as e:  # noqa: BLE001
        meta["status"] = "échec"
        meta["error"] = str(e)
        job["status"] = "échec"
        _log(job, f"ÉCHEC : {e}")
        job["log"] += traceback.format_exc().splitlines()[-4:]
    finally:
        (rd / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        job["ended"] = time.time()


def _worker():
    while True:
        job = None
        with _job_lock:
            for j in JOBS:
                if j["status"] == "en attente":
                    job = j
                    j["status"] = "en cours"
                    j["started"] = time.time()
                    break
        if job:
            _run_job(job)
        else:
            time.sleep(0.5)


threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------- API

@app.get("/api/subjects")
def subjects():
    out = []
    for d in sorted(p for p in IMGS.iterdir() if p.is_dir()):
        views = [v for v in VIEW_ORDER if view_path(d.name, v)]
        gt = load_gt(d / f"gt_{MAIN_VIEW}.json")
        runs = run_dirs(d.name)
        out.append({"name": d.name, "views": views,
                    "thumb": f"/thumb/imgs/{d.name}/{view_path(d.name, views[0]).name}?w=160" if views else None,
                    "gt_pieces": len(gt["pieces"]) if gt else 0,
                    "gt_verified": sum(1 for p in gt["pieces"] if p.get("verified")) if gt else 0,
                    "n_runs": len(runs), "can_run": MAIN_VIEW in views})
    return out


@app.get("/api/subjects/{subject}")
def subject(subject: str):
    d = IMGS / subject
    if not d.is_dir():
        raise HTTPException(404, "sujet inconnu")
    gt = load_gt(d / f"gt_{MAIN_VIEW}.json")
    views = []
    for v in VIEW_ORDER:
        p = view_path(subject, v)
        if p:
            w, h = image_size(p)
            views.append({"name": v, "url": f"/imgs/{subject}/{p.name}", "thumb": f"/thumb/imgs/{subject}/{p.name}?w=720",
                          "w": w, "h": h})
    runs = []
    for rd in run_dirs(subject):            # résumé léger ; les scores SAM se calculent dans l'archive
        meta = read_json(rd / "meta.json", {})
        runs.append({**meta, "has_pieces": (rd / "pieces.json").exists(), "has_model": (rd / "model.json").exists()})
    return {"name": subject, "views": views, "main_view": MAIN_VIEW, "runs": runs,
            "has_assembly": (d / ASSEMBLY).exists(), "has_compare": (COMPARE_DIR / subject / "scores.json").exists()}


@app.get("/api/subjects/{subject}/runs/{rid}/pieces")
def run_pieces(subject: str, rid: str):
    p = read_json(RUNS / subject / rid / "pieces.json")
    if p is None:
        raise HTTPException(404, "pas de pièces pour ce lancement")
    gt = load_gt(IMGS / subject / f"gt_{MAIN_VIEW}.json")
    ev = evaluate(gt, p, image_size(view_path(subject, MAIN_VIEW))) if gt and gt.get("pieces") else None
    return {"pieces": p, "eval": ev}


@app.get("/api/subjects/{subject}/runs/{rid}/model")
def run_model(subject: str, rid: str):
    m = read_json(RUNS / subject / rid / "model.json")
    if m is None:
        raise HTTPException(404, "pas de modèle 3D pour ce lancement")
    return m


@app.delete("/api/subjects/{subject}/runs/{rid}")
def delete_run(subject: str, rid: str):
    rd = RUNS / subject / rid
    if not (rd / "meta.json").exists():
        raise HTTPException(404, "lancement inconnu")
    shutil.rmtree(rd)
    return {"ok": True}


@app.patch("/api/subjects/{subject}/runs/{rid}")
def label_run(subject: str, rid: str, body: dict = Body(...)):
    mp = RUNS / subject / rid / "meta.json"
    meta = read_json(mp)
    if meta is None:
        raise HTTPException(404, "lancement inconnu")
    meta["label"] = str(body.get("label", ""))[:80]
    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return meta


@app.get("/api/subjects/{subject}/gt")
def get_gt(subject: str):
    return load_gt(IMGS / subject / f"gt_{MAIN_VIEW}.json") or {"view": MAIN_VIEW, "pieces": []}


@app.put("/api/subjects/{subject}/gt")
def put_gt(subject: str, doc: dict = Body(...)):
    path = IMGS / subject / f"gt_{MAIN_VIEW}.json"
    if path.exists():  # une sauvegarde de la version précédente, au cas où
        shutil.copy(path, path.with_suffix(".json.bak"))
    doc["view"] = MAIN_VIEW
    doc["updated"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    return {"ok": True, "updated": doc["updated"]}


@app.post("/api/subjects/{subject}/gt/from-run/{rid}")
def gt_from_run(subject: str, rid: str, force: bool = False):
    path = IMGS / subject / f"gt_{MAIN_VIEW}.json"
    if path.exists() and not force:
        raise HTTPException(409, "une vérité terrain existe déjà")
    from brickforge.evaluate import dir_label
    pieces = read_json(RUNS / subject / rid / "pieces.json") or []
    gt = {"view": MAIN_VIEW, "source_run": rid, "pieces": [
        {"id": f"g{i + 1}", "polygon": p["polygon"], "kind": p["kind"].rstrip("?"), "part": p.get("part"),
         "color": p.get("color"), "size": p.get("size"), "dir": dir_label(p.get("slope_dir")), "verified": False}
        for i, p in enumerate(pieces)]}
    return put_gt(subject, gt)


@app.post("/api/runs")
def start_run(body: dict = Body(...)):
    subject, model = body.get("subject"), body.get("model", "mobile")
    if model not in MODELS or not view_path(subject or "", MAIN_VIEW):
        raise HTTPException(400, "sujet ou modèle invalide")
    job = {"id": len(JOBS) + 1, "subject": subject, "model": model, "reuse": bool(body.get("reuse", True)),
           "label": body.get("label", ""), "status": "en attente", "log": [], "step": "en attente",
           "created": time.time()}
    with _job_lock:
        JOBS.append(job)
    return job


@app.get("/api/jobs")
def jobs():
    now = time.time()
    return [{**{k: v for k, v in j.items() if k != "log"}, "log": j["log"][-12:],
             "elapsed": round((j.get("ended") or now) - j.get("started", now))} for j in JOBS[-10:]][::-1]


@app.get("/api/runs")
def all_runs():
    out = []
    for d in sorted(p for p in IMGS.iterdir() if p.is_dir()):
        gt = load_gt(d / f"gt_{MAIN_VIEW}.json")
        out += [run_summary(d.name, rd, gt) for rd in run_dirs(d.name)]
    return sorted(out, key=lambda r: r.get("created", ""), reverse=True)


@app.get("/api/catalog")
def catalog():
    from app.catalog import CATALOG
    return {"parts": CATALOG, "colors": [{"code": c, "name": n, "hex": "#" + h} for c, n, h in colors.PALETTE + colors.DISPLAY_ONLY]}


# ---------------------------------------------------------------- assemblage 3D

ASSEMBLY = "assemblage.json"
_mesh_cache: dict[str, dict] = {}


@app.get("/api/parts/{part}")
def part_geometry(part: str):
    """Géométrie LDraw d'une pièce (triangles et arêtes en float32 base64, repère LDraw)."""
    import base64
    from brickforge.ldlib import part_mesh
    if part not in _mesh_cache:
        try:
            m = part_mesh(part)
        except FileNotFoundError:
            raise HTTPException(404, f"pièce {part} introuvable dans la bibliothèque LDraw")
        _mesh_cache[part] = {**{k: v for k, v in m.items() if k not in ("tris", "edges")},
                             "tris": base64.b64encode(m["tris"].tobytes()).decode(),
                             "edges": base64.b64encode(m["edges"].tobytes()).decode()}
    return _mesh_cache[part]


@app.get("/api/subjects/{subject}/assembly")
def get_assembly(subject: str):
    a = read_json(IMGS / subject / ASSEMBLY)
    if a is None:
        raise HTTPException(404, "pas encore d'assemblage")
    return a


@app.put("/api/subjects/{subject}/assembly")
def put_assembly(subject: str, doc: dict = Body(...)):
    path = IMGS / subject / ASSEMBLY
    if path.exists():
        shutil.copy(path, path.with_suffix(".json.bak"))
    doc["updated"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(doc, ensure_ascii=False))
    return {"ok": True, "updated": doc["updated"]}


@app.post("/api/subjects/{subject}/assembly/from-run/{rid}")
def assembly_from_run(subject: str, rid: str, force: bool = False):
    path = IMGS / subject / ASSEMBLY
    if path.exists() and not force:
        raise HTTPException(409, "un assemblage existe déjà")
    pieces = read_json(RUNS / subject / rid / "pieces.json")
    if pieces is None:
        raise HTTPException(404, "pas de pièces pour ce lancement")
    if not all(view_path(subject, v) for v in ("dessus", "profil", "face")):
        raise HTTPException(400, "il faut les vues dessus, profil et face")
    from brickforge.assemble import build_assembly
    a = build_assembly(IMGS / subject, pieces)
    a.update({"subject": subject, "source_run": rid, "created": datetime.now().isoformat(timespec="seconds")})
    return put_assembly(subject, a) | {"n": len(a["parts"])}


@app.get("/api/subjects/{subject}/assembly.ldr")
def assembly_ldr(subject: str):
    from fastapi.responses import Response
    from brickforge.assemble import to_ldr
    a = get_assembly(subject)
    a["parts"] = [p for p in a["parts"] if not p.get("hidden")]
    return Response(to_ldr(a, subject), media_type="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{subject}.ldr"'})


# ---------------------------------------------------------------- comparaison rendu / Gemini

COMPARE = ROOT / "out" / "compare"
_compare_running: dict[str, str] = {}


@app.post("/api/subjects/{subject}/compare")
def run_compare(subject: str, refit: bool = False):
    if not (IMGS / subject / ASSEMBLY).exists():
        raise HTTPException(400, "pas d'assemblage pour ce sujet")
    if _compare_running.get(subject) == "en cours":
        return {"status": "en cours"}
    _compare_running[subject] = "en cours"

    def work():
        try:
            from brickforge.compare import compare
            compare(IMGS / subject, refit=refit, log=lambda m: None)
            _compare_running[subject] = "terminé"
        except Exception as e:  # noqa: BLE001
            _compare_running[subject] = f"échec : {e}"
    threading.Thread(target=work, daemon=True).start()
    return {"status": "en cours"}


@app.get("/api/subjects/{subject}/compare")
def get_compare(subject: str):
    doc = read_json(COMPARE / subject / "scores.json") or {}
    hist = []
    hp = COMPARE / subject / "history.jsonl"
    if hp.exists():
        hist = [json.loads(l) for l in hp.read_text().splitlines() if l.strip()][-30:]
    return {**doc, "status": _compare_running.get(subject, ""), "history": hist}


# ---------------------------------------------------------------- entraînement (Mac Studio)

RBASE = "~/brickforge"
TRAIN_RUN = "runs/segment/pieces_v1"
SYNTH_CACHE = ROOT / "out" / "synth_cache"
_status_cache: dict = {"t": 0, "data": None}


def _remote(cmd: str, timeout=20, binary=False):
    r = subprocess.run(SSH + [REMOTE, cmd], capture_output=True, timeout=timeout)
    if r.returncode != 0 and not r.stdout:
        raise HTTPException(502, "Mac Studio injoignable : " + r.stderr.decode(errors="ignore")[-200:])
    return r.stdout if binary else r.stdout.decode(errors="ignore")


def _parse_progress(lines):
    """Dernière ligne de progression d'Ultralytics : entraînement d'une passe ou validation."""
    import re
    tr = re.compile(r"^\s*(\d+)/(\d+)\s+([\d.]+)G\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+[\d.]+\s+(\d+)\s+(\d+):\s+(\d+)%.*?(\d+)/(\d+)\s+([\d.]+)(it/s|s/it)\s+([\d:]+)<([\d:]+)")
    va = re.compile(r"Class\s+Images.*?:\s+(\d+)%.*?(\d+)/(\d+)\s+([\d.]+)(it/s|s/it)\s+([\d:]+)<([\d:]+)")
    for l in reversed(lines):
        m = tr.search(l)
        if m:
            g = m.groups()
            rate = float(g[12]) if g[13] == "it/s" else 1 / max(float(g[12]), 1e-6)
            return {"stage": "entraînement", "epoch": int(g[0]), "epochs": int(g[1]), "gpu_gb": float(g[2]),
                    "box_loss": float(g[3]), "seg_loss": float(g[4]), "cls_loss": float(g[5]), "dfl_loss": float(g[6]),
                    "instances": int(g[7]), "pct": int(g[9]), "step": int(g[10]), "steps": int(g[11]),
                    "rate": rate, "elapsed": g[14], "remaining": g[15]}
        m = va.search(l)
        if m:
            g = m.groups()
            return {"stage": "validation", "pct": int(g[0]), "step": int(g[1]), "steps": int(g[2]), "remaining": g[6]}
    return None


def _secs(t):
    parts = [int(x) for x in t.split(":")]
    v = 0
    for x in parts:
        v = v * 60 + x
    return v


@app.get("/api/train/status")
def train_status():
    import re
    if time.time() - _status_cache["t"] < 3 and _status_cache["data"]:
        return _status_cache["data"]
    script = (
        f"cd {RBASE}; echo IMAGES $(ls out/synth/images 2>/dev/null | wc -l); "
        "echo GEN $(pgrep -f '[b]rickforge.synth' | wc -l); "
        "echo TRAINPROC $(( $(pgrep -f '[t]rain_detector' | wc -l) + $(pgrep -f '[r]esume_train' | wc -l) + $(pgrep -f '[c]ontinue_train' | wc -l) )); "
        "for f in logs/synth_*.log; do tail -n1 $f; done 2>/dev/null | grep scène | sed 's/^/SCENE /'; "
        "for r in $(cat current_runs.txt 2>/dev/null || echo pieces_v1); do echo \"---RUN $r $(grep '^epochs:' runs/segment/$r/args.yaml 2>/dev/null | awk '{print $2}') $(grep '^batch:' runs/segment/$r/args.yaml 2>/dev/null | awk '{print $2}')\"; "
        "cat runs/segment/$r/results.csv 2>/dev/null; done; "
        "LAST=$( (cat current_runs.txt 2>/dev/null || echo pieces_v1) | tail -1); "
        "echo '---LOG'; tail -c 4000 logs/train.log 2>/dev/null | LC_ALL=C tr '\\r' '\\n' | grep -v '^\\s*$' | tail -14; "
        "echo \"---PLOTS $LAST\"; ls runs/segment/$LAST 2>/dev/null | grep -E '[.](png|jpg)$'; "
        "echo '---MEM'; memory_pressure 2>/dev/null | tail -1"
    )
    out = _remote(script)
    head, _, rest = out.partition("---RUN")
    runs_part, _, rest = ("---RUN" + rest).partition("---LOG")
    log, _, rest = rest.partition("---PLOTS")
    plots_part, _, mem = rest.partition("---MEM")
    info = {"images": 0, "gen_procs": 0, "train_procs": 0, "scenes": []}
    for line in head.splitlines():
        if line.startswith("IMAGES"):
            info["images"] = int(line.split()[1])
        elif line.startswith("GEN"):
            info["gen_procs"] = int(line.split()[1])
        elif line.startswith("TRAINPROC"):
            info["train_procs"] = int(line.split()[1])
        elif line.startswith("SCENE"):
            try:
                info["scenes"].append(int(line.split()[2].split("/")[0]))
            except (IndexError, ValueError):
                pass
    # historique : tronçons d'entraînement mis bout à bout (numérotation continue des passes)
    epochs, segments, total = [], [], 0
    for block in runs_part.split("---RUN")[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        hdr = lines[0].split()
        name = hdr[0]
        n_ep = int(hdr[1]) if len(hdr) > 1 and hdr[1].isdigit() else 0
        batch = hdr[2] if len(hdr) > 2 else "?"
        rows = [l for l in lines[1:] if l.strip()]
        start_ep = len(epochs)
        if len(rows) > 1:
            keys = [k.strip() for k in rows[0].split(",")]
            prev_t = 0.0
            for l in rows[1:]:
                vals = [v.strip() for v in l.split(",")]
                try:
                    e = {k: float(v) for k, v in zip(keys, vals)}
                except ValueError:
                    continue
                e["epoch_time"] = e.get("time", 0) - prev_t
                prev_t = e.get("time", 0)
                e["epoch"] = len(epochs) + 1
                e["run"] = name
                epochs.append(e)
        segments.append({"run": name, "batch": batch, "start": start_ep, "done": len(epochs) - start_ep, "planned": n_ep})
    clean = [re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\[K", "", l).strip() for l in log.strip().splitlines()]
    clean = [l for l in clean if l]
    live = _parse_progress(clean)
    if segments:
        if not segments[-1]["planned"] and live and live.get("epochs"):
            segments[-1]["planned"] = live["epochs"]        # args.yaml pas encore écrit : on lit la ligne de progression
        total = sum(sg["done"] for sg in segments[:-1]) + segments[-1]["planned"]
    offset = sum(sg["done"] for sg in segments[:-1]) if segments else 0
    if live and live.get("epoch"):
        live["global_epoch"] = offset + live["epoch"]
    running = info["train_procs"] > 0
    # temps restant estimé : fin de la passe en cours + passes restantes × durée moyenne récente
    eta = None
    if running and live and epochs:
        recent = [e["epoch_time"] for e in epochs[-3:] if e["epoch_time"] > 0 and e["run"] == segments[-1]["run"]]
        per_epoch = sum(recent) / len(recent) if recent else None
        if per_epoch is None and live.get("steps") and live.get("rate"):
            per_epoch = live["steps"] / live["rate"] * 1.15
        cur = live.get("global_epoch") or (len(epochs) + 1)
        left_this = _secs(live.get("remaining", "0")) if live.get("stage") == "entraînement" else 0
        if per_epoch:
            eta = int(left_this + max(0, total - cur) * per_epoch + (per_epoch * 0.12 if live.get("stage") == "entraînement" else 0))
    plots_lines = plots_part.strip().splitlines()
    last_run = plots_lines[0].strip() if plots_lines else "pieces_v1"
    mem_free = None
    m = re.search(r"(\d+)%", mem or "")
    if m:
        mem_free = int(m.group(1))
    info.update({"scenes_done": sum(info["scenes"]), "scenes_total": 12 * 150, "images_total": 12 * 150 * 4,
                 "log": clean[-8:], "epochs": epochs, "epochs_total": total or 30, "segments": segments,
                 "live": live if running else None, "eta_s": eta, "mem_free_pct": mem_free,
                 "current_epoch": (live.get("global_epoch") if running and live and live.get("global_epoch") else len(epochs)),
                 "plots_run": last_run, "plots": [p for p in plots_lines[1:] if p.strip()],
                 "phase": "génération" if info["gen_procs"] else ("entraînement" if running else
                          ("terminé" if epochs else "en attente"))})
    if _status_cache.get("data") and info["images"] < _status_cache["data"].get("images", 0):
        _status_cache["gen"] = None
    _status_cache.update(t=time.time(), data=info)
    return info


@app.get("/api/train/samples")
def train_samples(n: int = 24, seed: int = 0):
    out = _remote(f"cd {RBASE}/out/synth/images && ls | awk 'BEGIN{{srand({seed or int(time.time())})}} {{print rand()\" \"$0}}' | sort | head -{min(n, 60)} | cut -d' ' -f2")
    _fetch_gen()
    return {"gen": _status_cache["gen"], "ids": [f[:-4] for f in out.split() if f.endswith(".jpg")]}


def _fetch_gen():
    if not _status_cache.get("gen"):
        _status_cache["gen"] = _remote(f"stat -f %m {RBASE}/out/synth/classes.txt").strip() or "x"
    return _status_cache["gen"]


def _fetch(rel: str) -> Path:
    """Cache local des fichiers du Mac Studio. Le cache est rangé par lot de génération (date de
    classes.txt), pour qu'une nouvelle génération ne montre jamais d'anciennes images du même nom."""
    if rel.startswith("out/synth/"):
        dest = SYNTH_CACHE / _fetch_gen() / rel
    else:
        dest = SYNTH_CACHE / rel
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = _remote(f"cat {RBASE}/{rel}", binary=True)
        if not data:
            raise HTTPException(404, "fichier introuvable sur le Mac Studio")
        dest.write_bytes(data)
    return dest


@app.get("/api/train/sample/{sid}")
def train_sample(sid: str):
    if not all(c.isalnum() or c == "_" for c in sid):
        raise HTTPException(400, "identifiant invalide")
    labels = _fetch(f"out/synth/labels/{sid}.txt").read_text()
    meta = json.loads(_fetch(f"out/synth/meta/{sid}.json").read_text())
    from brickforge.synth import CLASSES
    from app.catalog import CATALOG
    names = {c["part"]: c["name"] for c in CATALOG}
    from app.catalog import _title
    objs = []
    for line, o in zip(labels.splitlines(), meta["objects"]):
        t = line.split()
        part = CLASSES[int(t[0])]
        nm = names.get(part)
        objs.append({"part": part, "name": nm if nm and nm != part else _title(part), "color": o["color"],
                     "color_name": colors.NAMES.get(o["color"], str(o["color"])), "area": o["area"],
                     "poly": [[float(t[i]), float(t[i + 1])] for i in range(1, len(t), 2)]})
    return {"id": sid, "image": f"/api/train/file/out/synth/images/{sid}.jpg?g={_fetch_gen()}", "objects": objs, "camera": meta["camera"]}


_pred_cache: dict = {}


@app.post("/api/train/predict")
def train_predict(body: dict = Body(...)):
    """Prédictions du détecteur (dernier état de l'entraînement) sur des images du Mac Studio.
    body : {"images": ["out/synth/images/<id>.jpg" | "imgs/<sujet>/<vue>.jpeg"], "imgsz": 640}"""
    import shlex
    imgs = [i for i in body.get("images", []) if ".." not in i and (i.startswith("out/synth/images/") or i.startswith("imgs/"))]
    if not imgs:
        raise HTTPException(400, "aucune image")
    imgsz = int(body.get("imgsz", 640))
    st = train_status()
    epoch = len((st.get("epochs") or []))
    todo = [i for i in imgs if (epoch, imgsz, i) not in _pred_cache]
    if todo and st.get("phase") == "entraînement":
        # la mémoire du Mac est partagée CPU/GPU : une analyse pendant l'entraînement l'a fait planter
        raise HTTPException(409, "Entraînement en cours sur le Mac Studio : les analyses sont possibles à la fin "
                                 "(les résultats déjà calculés restent affichés).")
    if todo:
        subjects = {i.split("/")[1] for i in todo if i.startswith("imgs/")}
        for sname in subjects:              # les vues Gemini doivent être présentes sur le Mac Studio
            subprocess.run(["rsync", "-az", "-e", " ".join(SSH), str(IMGS / sname) + "/", f"{REMOTE}:brickforge/imgs/{sname}/"],
                           capture_output=True, timeout=60)
        weights = f"runs/segment/{st.get('plots_run') or 'pieces_v1'}/weights/last.pt"
        out = _remote(f"cd {RBASE} && env/bin/python -m brickforge.predict --weights {weights} --imgsz {imgsz} "
                      + " ".join(shlex.quote(i) for i in todo) + " 2>/dev/null", timeout=180)
        try:
            res = json.loads(out[out.index("["):])
        except ValueError:
            raise HTTPException(502, "le modèle n'a pas répondu (pas encore de poids ?)")
        for rel, r in zip(todo, res):
            _pred_cache[(epoch, imgsz, rel)] = r
    return {"epoch": epoch, "results": [{**_pred_cache[(epoch, imgsz, i)], "path": i} for i in imgs]}


@app.get("/api/train/file/{rel:path}")
def train_file(rel: str):
    if ".." in rel or not (rel.startswith("out/synth/images/") or rel.startswith("runs/segment/")):
        raise HTTPException(400, "chemin refusé")
    if rel.startswith("runs/segment/"):              # courbes et aperçus : ils changent pendant l'entraînement
        dest = SYNTH_CACHE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_remote(f"cat {RBASE}/{rel}", binary=True))
        return FileResponse(dest)
    return FileResponse(_fetch(rel), headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------- cahier de recherche

def _note(path: Path, html=False) -> dict:
    text = path.read_text()
    meta, body = {}, text
    if text.startswith("---"):
        head, _, body = text[3:].partition("\n---")
        for line in head.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    metrics = []
    for item in meta.get("metrics", "").split(";"):
        k, _, v = item.partition("=")
        if k.strip():
            metrics.append({"label": k.strip(), "value": v.strip()})
    out = {"id": path.stem, "title": meta.get("title", path.stem), "date": meta.get("date", ""),
           "status": meta.get("status", ""), "summary": meta.get("summary", ""), "cover": meta.get("cover", ""),
           "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()], "metrics": metrics,
           "live": meta.get("live", ""), "subject": meta.get("subject", ""),
           "authors": [a.strip() for a in meta.get("authors", "").split(",") if a.strip()],
           "updated": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="minutes")}
    if html:
        import markdown
        out["html"] = markdown.markdown(body, extensions=["tables", "fenced_code"])
    return out


@app.get("/api/journal")
def journal():
    notes = [_note(p) for p in sorted((RESEARCH / "notes").glob("*.md"))]
    return notes[::-1]                                   # le plus récent d'abord


@app.get("/api/journal/{nid}")
def journal_note(nid: str):
    p = RESEARCH / "notes" / f"{nid}.md"
    if not p.exists() or "/" in nid:
        raise HTTPException(404, "entrée inconnue")
    return _note(p, html=True)


_BH = {}


def _bh_data():
    """Figurines BrickHeadz officielles + constructions couche par couche (rechargées si le fichier change)."""
    d = ROOT / "data" / "brickheadz"
    fb = d / "layer_builds.json"
    mt = fb.stat().st_mtime if fb.exists() else 0
    if _BH.get("mt") != mt:
        figs = json.loads((d / "figures.json").read_text())
        ev = {r["key"]: r for r in json.loads((d / "layer_eval.json").read_text())["rows"]} if (d / "layer_eval.json").exists() else {}
        _BH.update(mt=mt, figs={f"{f['num']}#{f['fig']}": f for f in figs}, ev=ev,
                   builds=json.loads(fb.read_text()) if fb.exists() else {})
    return _BH


@app.get("/api/bh/gallery")
def bh_gallery():
    B = _bh_data()
    out = []
    for k, f in B["figs"].items():
        r = B["ev"].get(k, {})
        out.append({"key": k, "set": f["set"], "num": f["num"], "fig": f["fig"], "nfigs": f.get("nfigs", 1), "year": f.get("year"),
                    "parts": len(f["placed"]), "built": k in B["builds"],
                    "m3d": r.get("3d"), "mfiche": r.get("fiche")})
    return out


@app.get("/api/bh/model/{num}/{fig}")
def bh_model(num: str, fig: int):
    B = _bh_data()
    k = f"{num}#{fig}"
    if k not in B["figs"]:
        raise HTTPException(404, "figurine inconnue")
    strip = lambda pl: [{"part": p["part"], "color": p["color"], "m": p["m"]} for p in pl]
    b = B["builds"].get(k, {})
    return {"key": k, "set": B["figs"][k]["set"], "officiel": strip(B["figs"][k]["placed"]),
            "3d": strip(b.get("3d", [])), "fiche": strip(b.get("fiche", []))}


@app.get("/api/i3d")
def i3d_list():
    """Résultats image → 3D (Hunyuan3D…) → LEGO : un dossier par image dans data/hunyuan."""
    out = []
    base = ROOT / "data" / "hunyuan"
    for d in sorted(base.glob("*")) if base.exists() else []:
        b = d / "build.json"
        if not (d / "textured.glb").exists():
            continue
        info = json.loads(b.read_text()) if b.exists() else {}
        img = next((p.name for p in (d / "preprocessed.png", d / "input.jpg", d / "input.png", d / "input.jpeg") if p.exists()), None)
        out.append({"name": d.name, "img": f"/i3d/{d.name}/{img}" if img else None, "glb": f"/i3d/{d.name}/textured.glb",
                    "built": b.exists(), "ref": info.get("ref"), "yaw": info.get("yaw", 0), "parts": info.get("parts"), "metrics": info.get("metrics_vs_ref"),
                    "floating": info.get("floating"), "collisions": info.get("collisions"),
                    "fill": _fill_info(d / "fill.json")})
    return out


def _fill_info(p):
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return {k: d.get(k) for k in ("parts", "silhouettes", "vs_ref", "floating", "collisions", "part_counts")}


@app.get("/api/i3d/{name}/lego")
def i3d_lego(name: str, kind: str = "couches"):
    b = ROOT / "data" / "hunyuan" / name / ("fill.json" if kind == "fill" else "build.json")
    if "/" in name or not b.exists():
        raise HTTPException(404, "pas encore construit")
    d = json.loads(b.read_text())
    if kind == "fill":
        bj = ROOT / "data" / "hunyuan" / name / "build.json"
        d["ref"] = json.loads(bj.read_text()).get("ref") if bj.exists() else None
    ref = None
    if d.get("ref"):
        num, fig = d["ref"].split(":")
        f = _bh_data()["figs"].get(f"{num}#{fig}")
        ref = [{"part": p["part"], "color": p["color"], "m": p["m"]} for p in f["placed"]] if f else None
    return {"lego": d["placed"], "ref": ref}


@app.get("/api/overview")
def overview():
    """Chiffres de la page d'accueil (locaux uniquement : pas d'appel au Mac Studio)."""
    subjects = [d.name for d in IMGS.iterdir() if d.is_dir()]
    parts, best = 0, None
    for sname in subjects:
        a = read_json(IMGS / sname / ASSEMBLY)
        if a:
            parts += len(a.get("parts", []))
        sc = read_json(COMPARE_DIR / sname / "scores.json")
        if sc and sc.get("summary"):
            v = sc["summary"]["silhouette"]
            if best is None or v > best["value"]:
                best = {"value": v, "subject": sname}
    notes = list((RESEARCH / "notes").glob("*.md"))
    return {"subjects": len(subjects), "notes": len(notes), "parts_placed": parts, "best_silhouette": best,
            "catalog": len(__import__("app.catalog", fromlist=["CATALOG"]).CATALOG)}


@app.get("/thumb/{rel:path}")
def thumb(rel: str, w: int = 480):
    """Miniature JPEG mise en cache (les photos originales font 2 Mo)."""
    src = (ROOT / rel).resolve()
    if ".." in rel or not any(str(src).startswith(str((ROOT / d).resolve())) for d in ("imgs", "research", "out")):
        raise HTTPException(400, "chemin refusé")
    if not src.exists():
        raise HTTPException(404, "image introuvable")
    w = max(32, min(w, 1600))
    dest = THUMBS / f"{rel.replace('/', '__')}_{w}.jpg"
    if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
        img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise HTTPException(415, "format non lu")
        if img.ndim == 3 and img.shape[2] == 4:
            a = img[..., 3:] / 255.0
            img = (img[..., :3] * a + 255 * (1 - a)).astype("uint8")
        k = w / img.shape[1]
        if k < 1:
            img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        THUMBS.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), img, [cv2.IMWRITE_JPEG_QUALITY, 84])
    return FileResponse(dest, headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------- bac à sable (créations libres)

SANDBOX = ROOT / "creations"


def _sb_path(name: str) -> Path:
    if not name or not all(c.isalnum() or c in "-_" for c in name) or len(name) > 60:
        raise HTTPException(400, "nom invalide (lettres, chiffres, - et _)")
    return SANDBOX / f"{name}.json"


@app.get("/api/sandbox")
def sandbox_list():
    SANDBOX.mkdir(exist_ok=True)
    out = []
    for f in sorted(SANDBOX.glob("*.json"), key=lambda f: -f.stat().st_mtime):
        d = read_json(f, {})
        out.append({"name": f.stem, "parts": len(d.get("parts", [])), "updated": d.get("updated", "")})
    return out


@app.get("/api/sandbox/{name}")
def sandbox_get(name: str):
    p = _sb_path(name)
    return read_json(p, {"name": name, "parts": []})


@app.put("/api/sandbox/{name}")
def sandbox_put(name: str, doc: dict = Body(...)):
    p = _sb_path(name)
    SANDBOX.mkdir(exist_ok=True)
    doc["name"] = name
    doc["updated"] = datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps(doc, ensure_ascii=False))
    return {"ok": True, "updated": doc["updated"]}


@app.post("/api/sandbox/{name}/rename")
def sandbox_rename(name: str, body: dict = Body(...)):
    src, dst = _sb_path(name), _sb_path(str(body.get("to", "")))
    if dst.exists():
        raise HTTPException(409, "ce nom existe déjà")
    src.rename(dst)
    return {"ok": True}


@app.post("/api/sandbox/{name}/check")
def sandbox_check(name: str, doc: dict = Body(...)):
    """Vérification avec le moteur réel (points d'accroche, collisions au voxel) : voir app/sandbox_api.py."""
    from app.sandbox_api import check_doc
    return check_doc(doc.get("parts", []))


@app.get("/api/sandbox-ldr/{name}")
def sandbox_ldr(name: str):
    from fastapi.responses import Response
    from brickforge.assemble import to_ldr
    d = sandbox_get(name)
    return Response(to_ldr(d, name), media_type="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{name}.ldr"'})


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/parts-batch")
def parts_batch(parts: list[str] = Body(...)):
    """Géométries de plusieurs pièces en une requête (même format que /api/parts/{part}) ; null si inconnue."""
    out = {}
    for p in parts[:3000]:
        try:
            out[p] = part_geometry(p)
        except HTTPException:
            out[p] = None
    return out


from app.explorer import router as explorer_router  # noqa: E402
app.include_router(explorer_router)
from app.fill_live import router as fill_router  # noqa: E402
app.include_router(fill_router)
from app.train_live import router as train_fill_router  # noqa: E402
app.include_router(train_fill_router)
from app.sandbox_api import router as sandbox_router  # noqa: E402
app.include_router(sandbox_router)

app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/research", StaticFiles(directory=ROOT / "research"), name="research")
(ROOT / "data" / "hunyuan").mkdir(parents=True, exist_ok=True)
app.mount("/i3d", StaticFiles(directory=ROOT / "data" / "hunyuan"), name="i3d")
app.mount("/imgs", StaticFiles(directory=IMGS), name="imgs")
RUNS.mkdir(parents=True, exist_ok=True)
app.mount("/runs", StaticFiles(directory=RUNS), name="runs")
(ROOT / "out" / "compare").mkdir(parents=True, exist_ok=True)
app.mount("/compare", StaticFiles(directory=ROOT / "out" / "compare"), name="compare")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
