"""Sets officiels modélisés en LDraw publiés sur le forum LDraw « Official Models » mais pas encore dans l'OMR.

Ce sont surtout des sets récents, en attente d'entrer dans l'OMR (même format .mpd, avec étapes, mêmes auteurs).
Ils sont rangés comme les sets OMR (data/omr/<num>/<num>[_<Alternatif>].mpd) et listés dans data/omr/forum_index.json.

    python -m brickforge.ldforum threads.json        # threads.json : liens collectés sur le forum (tid, title, links, atts)
"""

import io
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OMR = ROOT / "data" / "omr"
FORUM_INDEX = OMR / "forum_index.json"
UA = {"User-Agent": "brickforge-explorer/0.1"}
NUM_RX = re.compile(r"^\s*(\d{3,7})(?:-(\d+))?(?=[\s_.\-]|$)")


def get(url):
    for k in range(3):
        try:
            time.sleep(0.3)
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as e:  # noqa: BLE001
            print("  retry", url, e, flush=True)
            time.sleep(3)
    return None


def fname(url, name=None):
    return urllib.parse.unquote(name or urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]).strip()


def files_of(url, name, blob):
    """[(nom, octets)] : le fichier lui-même, ou les .mpd/.ldr d'une archive zip."""
    if fname(url, name).lower().endswith(".zip"):
        try:
            z = zipfile.ZipFile(io.BytesIO(blob))
        except zipfile.BadZipFile:
            return []
        return [(Path(n).name, z.read(n)) for n in z.namelist() if n.lower().endswith((".mpd", ".ldr")) and not n.startswith("__MACOSX")]
    return [(fname(url, name), blob)]


def is_ldraw(b):
    """Vrai fichier LDraw (et pas une page HTML d'erreur ou de connexion)."""
    head = b[:4000].decode("utf-8", "ignore").lstrip("\ufeff \r\n\t")
    return head.startswith(("0 ", "0\t", "1 ")) and "<html" not in head.lower()


def alt_name(fn, num, setname):
    """« 31161 - Medieval Dragon - Sea Serpent.mpd » → « Sea-Serpent » ; le modèle de la boîte → ""."""
    stem = Path(fn).stem
    rest = NUM_RX.sub("", stem).strip(" -_")
    if setname and rest.lower().startswith(setname.lower()):
        rest = rest[len(setname):].strip(" -_")
    return re.sub(r"[^A-Za-z0-9]+", "-", rest).strip("-")


def run(threads_json):
    from brickforge import omr
    from brickforge.ldlib import part_triangles

    threads = json.loads(Path(threads_json).read_text())
    have = {r["num"] for r in json.loads((OMR / "index.json").read_text())}
    db = sqlite3.connect(ROOT / "data" / "rebrickable" / "rb.sqlite")
    rb = {r[0]: r[1:] for r in db.execute("SELECT num, name, year, theme, pieces FROM sets")}

    # 1. candidats : un fichier par (set, nom de fichier) ; la publication la plus récente gagne (corrections)
    cand = defaultdict(dict)
    for t in threads:
        # les pièces jointes du forum exigent un compte : seulement les liens vers des hébergeurs publics
        for url, name in [(u, None) for u in t["links"] if "forums.ldraw.org" not in u]:
            fn = fname(url, name)
            m = NUM_RX.match(fn)
            if not m or not fn.lower().endswith((".mpd", ".ldr", ".zip")):
                continue
            num = f"{m.group(1)}-{m.group(2) or 1}"
            if num in have or num not in rb:
                continue
            cand[num][fn.lower()] = (url, name, t)
    print(len(cand), "sets candidats hors OMR", flush=True)

    out = json.loads(FORUM_INDEX.read_text()) if FORUM_INDEX.exists() else []
    done = {r["num"] for r in out}
    for num, files in sorted(cand.items()):
        if num in done:
            continue
        setname, year, theme, pieces = rb[num]
        got = []
        for url, name, t in files.values():
            blob = get(url)
            if blob:
                got += [(fn, b, t) for fn, b in files_of(url, name, blob)]
        got = [g for g in got if g[0].lower().endswith((".mpd", ".ldr")) and is_ldraw(g[1])]
        if not got:
            print("  rien de lisible", num, flush=True)
            continue
        d = OMR / num
        d.mkdir(parents=True, exist_ok=True)
        got.sort(key=lambda g: -len(g[1]))          # le plus gros fichier = modèle de la boîte (les 3-en-1 sont plus petits)
        models, used = [], set()
        for k, (fn, b, t) in enumerate(got):
            alt = "" if k == 0 else (alt_name(fn, num, setname) or f"Variante-{k}")
            stem = num if not alt else f"{num}_{alt}"
            if stem in used:
                continue
            used.add(stem)
            p = d / f"{stem}.mpd"
            p.write_bytes(b)
            try:
                main, fl = omr.parse_mpd(p)
                parts = omr.flatten(main, fl)
            except Exception as e:  # noqa: BLE001
                print("  illisible", fn, e, flush=True)
                p.unlink()
                continue
            uniq = {x["part"] for x in parts}
            missing = [u for u in uniq if not len(part_triangles(u))]
            models.append({"file": stem, "src": fn, "parts": len(parts), "missing": len(missing),
                           "thread": f"https://forums.ldraw.org/thread-{t['tid']}.html", "thread_title": t["title"]})
        if not models:
            continue
        out.append({"num": num, "name": setname, "year": year, "theme": theme, "pieces": pieces,
                    "models": len(models), "files": models, "source": "forum"})
        print(f"  {num} {setname} ({year}) : {len(models)} modèle(s), {models[0]['parts']} pièces, {models[0]['missing']} pièces inconnues", flush=True)
        FORUM_INDEX.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    FORUM_INDEX.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(len(out), "sets du forum")


if __name__ == "__main__":
    run(sys.argv[1])
