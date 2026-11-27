"""Catalogue Rebrickable : tous les sets LEGO (~25 000, jusqu'aux sorties récentes) et leur inventaire de pièces.

Pas de 3D ni d'étapes ici (seulement « quelles pièces, quelles couleurs, combien ») : la 3D reste l'OMR LDraw.
Source : exports CSV publics https://rebrickable.com/downloads/ (data/rebrickable/*.csv.gz).

    python -m brickforge.rebrickable          # (re)construit data/rebrickable/rb.sqlite
"""

import csv
import gzip
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RB = ROOT / "data" / "rebrickable"
DB = RB / "rb.sqlite"
FILES = ["sets", "themes", "inventories", "inventory_parts", "inventory_minifigs", "minifigs", "colors", "parts"]


def rows(name):
    with gzip.open(RB / f"{name}.csv.gz", "rt", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def build():
    tmp = DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript("""
      CREATE TABLE sets (num TEXT PRIMARY KEY, name TEXT, year INT, theme TEXT, pieces INT, img TEXT, inv INT);
      CREATE TABLE inv (inv INT, part TEXT, color INT, qty INT, spare INT, img TEXT);
      CREATE TABLE figs (inv INT, fig TEXT, qty INT);
      CREATE TABLE minifigs (fig TEXT PRIMARY KEY, name TEXT, pieces INT, img TEXT);
      CREATE TABLE colors (id INT PRIMARY KEY, name TEXT, rgb TEXT, trans INT);
      CREATE TABLE parts (part TEXT PRIMARY KEY, name TEXT, cat INT);
    """)
    th = {r["id"]: r for r in rows("themes")}

    def path(tid):
        out = []
        while tid:
            out.append(th[tid]["name"])
            tid = th[tid]["parent_id"]
        return " > ".join(reversed(out))

    # dernier inventaire (version la plus haute) de chaque set
    inv = {}
    for r in rows("inventories"):
        if r["set_num"] not in inv or int(r["version"]) > inv[r["set_num"]][0]:
            inv[r["set_num"]] = (int(r["version"]), int(r["id"]))
    keep = set()
    sets = []
    for r in rows("sets"):
        i = inv.get(r["set_num"], (0, None))[1]
        sets.append((r["set_num"], r["name"], int(r["year"]), path(r["theme_id"]), int(r["num_parts"]), r["img_url"], i))
        if i:
            keep.add(i)
    db.executemany("INSERT INTO sets VALUES (?,?,?,?,?,?,?)", sets)
    figinv = {}
    for r in rows("inventories"):                     # inventaires des minifigs (pour compter leurs pièces si besoin)
        if r["set_num"].startswith("fig-"):
            figinv[r["set_num"]] = int(r["id"])
    db.executemany("INSERT INTO inv VALUES (?,?,?,?,?,?)",
                   ((int(r["inventory_id"]), r["part_num"], int(r["color_id"]), int(r["quantity"]), r["is_spare"] == "True", r["img_url"])
                    for r in rows("inventory_parts") if int(r["inventory_id"]) in keep))
    db.executemany("INSERT INTO figs VALUES (?,?,?)",
                   ((int(r["inventory_id"]), r["fig_num"], int(r["quantity"])) for r in rows("inventory_minifigs") if int(r["inventory_id"]) in keep))
    db.executemany("INSERT INTO minifigs VALUES (?,?,?,?)", ((r["fig_num"], r["name"], int(r["num_parts"]), r["img_url"]) for r in rows("minifigs")))
    db.executemany("INSERT INTO colors VALUES (?,?,?,?)", ((int(r["id"]), r["name"], r["rgb"], r["is_trans"] == "True") for r in rows("colors")))
    db.executemany("INSERT INTO parts VALUES (?,?,?)", ((r["part_num"], r["name"], int(r["part_cat_id"])) for r in rows("parts")))
    db.execute("CREATE INDEX inv_i ON inv(inv)")
    db.execute("CREATE INDEX figs_i ON figs(inv)")
    db.commit()
    db.close()
    tmp.replace(DB)
    return len(sets)


def connect():
    if not DB.exists():
        build()
    db = sqlite3.connect(DB, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


if __name__ == "__main__":
    print(build(), "sets ->", DB)
