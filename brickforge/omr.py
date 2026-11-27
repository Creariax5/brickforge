"""Import d'un vrai set LEGO depuis l'OMR LDraw (fichier .mpd) vers un sujet Brick Forge.

Le .mpd contient le modèle principal, ses sous-modèles (« 0 FILE … .ldr ») et parfois des pièces
embarquées (« 0 FILE … .dat »). On aplatit tout en une liste de pièces dans le repère du modèle,
en gardant pour chaque pièce l'étape de la notice (`step`, ordre global) et le sous-modèle (`sub`).

    python -m brickforge.omr data/omr/31088/31088-1.mpd lego_omr_31088 [--photo URL]
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import numpy as np

from .ldlib import LDRAW

ROOT = Path(__file__).resolve().parent.parent
EMBED = LDRAW / "omr_parts"          # pièces embarquées dans les .mpd (ajouté aux chemins de ldlib)


def _key(name: str) -> str:
    return name.strip().replace("\\", "/").lower()


def _safe(name: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "_", _key(name))


def parse_mpd(path: Path) -> tuple[str, dict[str, list[str]]]:
    files, cur, order = {}, None, []
    text = path.read_text(errors="ignore")
    if not any(l.startswith("0 FILE ") for l in text.splitlines()):   # .ldr simple, sans sous-modèles
        text = f"0 FILE {path.stem}.ldr\n" + text
    for line in text.splitlines():
        line = line.rstrip("\r")
        if line.startswith("0 FILE "):
            cur = _key(line[7:])
            files[cur] = []
            order.append(cur)
        elif cur is not None:
            files[cur].append(line)
    return order[0], files


def _write_embedded(files: dict[str, list[str]]) -> dict[str, str]:
    """Écrit les pièces embarquées (.dat) dans data/ldraw/omr_parts ; renvoie nom MPD → identifiant."""
    EMBED.mkdir(parents=True, exist_ok=True)
    ids = {n: _safe(n)[:-4] for n in files if n.endswith(".dat")}
    for n, lines in files.items():
        if not n.endswith(".dat"):
            continue
        out = []
        for l in lines:
            tok = l.split()
            if tok and tok[0] == "1" and len(tok) >= 15 and _key(" ".join(tok[14:])) in ids:
                l = " ".join(tok[:14] + [ids[_key(" ".join(tok[14:]))] + ".dat"])
            out.append(l)
        (EMBED / (ids[n] + ".dat")).write_text("\n".join(out) + "\n")
    return ids


def flatten(main: str, files: dict[str, list[str]]) -> list[dict]:
    embedded = _write_embedded(files)
    parts: list[dict] = []
    step = [0]

    def walk(name: str, R: np.ndarray, t: np.ndarray, color: int, sub: str):
        lines = files[name]
        had = False
        for l in lines:
            tok = l.split()
            if not tok:
                continue
            if tok[0] == "0" and len(tok) > 1 and tok[1] in ("STEP", "ROTSTEP"):
                if had:
                    step[0] += 1
                had = False
                continue
            if tok[0] != "1" or len(tok) < 15:
                continue
            c = int(tok[1])
            c = color if c == 16 else c
            pos = np.array(list(map(float, tok[2:5])))
            m = np.array(list(map(float, tok[5:14]))).reshape(3, 3)
            ref = _key(" ".join(tok[14:]))
            Rw, tw = R @ m, R @ pos + t
            if ref in files and not ref.endswith(".dat"):
                if had:                       # le sous-modèle se construit à part, avant d'être posé
                    step[0] += 1
                walk(ref, Rw, tw, c, ref.removesuffix(".ldr"))
                had = True                    # sa pose compte dans l'étape courante du parent
                continue
            part = embedded.get(ref) or ref.removesuffix(".dat")
            parts.append({"part": part, "color": c, "m": [*map(float, np.round(tw, 3)), *map(float, np.round(Rw.ravel(), 6))],
                          "step": step[0], "sub": sub})
            had = True
        if had:
            step[0] += 1

    walk(main, np.eye(3), np.zeros(3), 16, main.removesuffix(".ldr"))
    for i, p in enumerate(parts):
        p["id"] = f"o{i + 1}"
        p["src"] = "omr"
        p["status"] = "ok"
    return parts


def import_set(mpd: Path, subject: str, photo: str | None = None) -> dict:
    main, files = parse_mpd(mpd)
    parts = flatten(main, files)
    d = ROOT / "imgs" / subject
    d.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    head = "\n".join(files[main][:12])
    asm = {"subject": subject, "source": f"OMR LDraw · {mpd.name}", "created": now, "updated": now,
           "license": "CCAL 2.0 (LDraw OMR)", "author": next((l[10:].strip() for l in files[main] if l.startswith("0 Author:")), ""),
           "steps": max((p["step"] for p in parts), default=-1) + 1, "parts": parts}
    (d / "assemblage.json").write_text(json.dumps(asm, ensure_ascii=False, indent=1))
    if photo:
        import urllib.request
        req = urllib.request.Request(photo, headers={"User-Agent": "brickforge/0.1"})
        (d / ("photo" + Path(photo).suffix)).write_bytes(urllib.request.urlopen(req, timeout=30).read())
    return asm


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mpd", type=Path)
    ap.add_argument("subject")
    ap.add_argument("--photo")
    a = ap.parse_args()
    asm = import_set(a.mpd, a.subject, a.photo)
    from collections import Counter
    print(f"{len(asm['parts'])} pièces, {asm['steps']} étapes, {len(set(p['sub'] for p in asm['parts']))} sous-modèles")
    print(Counter(p["part"] for p in asm["parts"]).most_common(8))
