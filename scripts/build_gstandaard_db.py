"""Bouw een read-only SQLite-cache van de G-standaard voor snelle joins.

Leest de relevante BST-bestanden via de Z-Index-layout (scripts.gstandaard.Gstandaard)
en schrijft ze met ruime indexen naar data/gstandaard.sqlite. Eenmalig draaien:

    ./venv/bin/python -m scripts.build_gstandaard_db
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.gstandaard import (
    DEFAULT_DATA_DIR,
    DEFAULT_DB_PATH,
    THESAURUS_INDICATIE_AARD,
    Gstandaard,
)

_BATCH = 5000

# tabel -> (kolommen, bronbestand, rubrieken in dezelfde volgorde als de kolommen)
_TABLES = {
    "bst004": (["zi", "hpk"], "BST004T", ["ATKODE", "HPKODE"]),
    "bst070": (["hpk", "gpk"], "BST070T", ["HPKODE", "GPKODE"]),
    "bst711": (["gpk", "atc", "gpstnr"], "BST711T", ["GPKODE", "ATCODE", "GPSTNR"]),
    "bst020": (["nmnr", "naam"], "BST020T", ["NMNR", "NMNAAM"]),
    "bst131": (["zi"], "BST131T", ["ZINR"]),
    "bst132": (["zi", "inid", "insrt"], "BST132T", ["ZINR", "INID", "INSRT"]),
    "bst133": (["inid", "inkort"], "BST133T", ["INID", "INKORT"]),
}

# Ruime indexset voor een read-only DB: enkelvoudig + covering-composieten op
# elke join-richting die de queries in GstandaardDB raken.
_INDEXES = [
    ("ix_bst004_zi", "bst004", "(zi)"),
    ("ix_bst004_hpk", "bst004", "(hpk)"),
    ("ix_bst004_hpk_zi", "bst004", "(hpk, zi)"),
    ("ix_bst070_hpk", "bst070", "(hpk)"),
    ("ix_bst070_gpk", "bst070", "(gpk)"),
    ("ix_bst070_gpk_hpk", "bst070", "(gpk, hpk)"),
    ("ix_bst711_gpk", "bst711", "(gpk)"),
    ("ix_bst711_atc", "bst711", "(atc)"),
    ("ix_bst711_gpstnr", "bst711", "(gpstnr)"),
    ("ix_bst711_atc_gpk", "bst711", "(atc, gpk, gpstnr)"),
    ("ix_bst020_nmnr", "bst020", "(nmnr)"),
    ("ix_bst020_naam", "bst020", "(naam)"),
    ("ix_bst131_zi", "bst131", "(zi)"),
    ("ix_bst132_zi", "bst132", "(zi)"),
    ("ix_bst132_inid", "bst132", "(inid)"),
    ("ix_bst132_zi_inid", "bst132", "(zi, inid, insrt)"),
    ("ix_bst133_inid", "bst133", "(inid)"),
    ("ix_thesaurus_tsnr", "thesaurus", "(tsnr)"),
    ("ix_thesaurus_tsnr_code", "thesaurus", "(tsnr, code)"),
]


def _create_table(con: sqlite3.Connection, table: str, cols: list[str]) -> None:
    con.execute(f"DROP TABLE IF EXISTS {table}")
    coldefs = ", ".join(f"{c} TEXT" for c in cols)
    con.execute(f"CREATE TABLE {table} ({coldefs})")


def _fill_table(con: sqlite3.Connection, gs: Gstandaard, table: str, cols, bestand, rubrieken) -> int:
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    batch, total = [], 0
    for rec in gs.records(bestand):
        batch.append(tuple(rec[r] for r in rubrieken))
        if len(batch) >= _BATCH:
            con.executemany(sql, batch)
            total += len(batch)
            batch.clear()
    if batch:
        con.executemany(sql, batch)
        total += len(batch)
    return total


def _fill_thesaurus(con: sqlite3.Connection, gs: Gstandaard) -> int:
    con.execute("DROP TABLE IF EXISTS thesaurus")
    con.execute("CREATE TABLE thesaurus (tsnr TEXT, code TEXT, naam TEXT)")
    sql = "INSERT INTO thesaurus (tsnr, code, naam) VALUES (?, ?, ?)"
    batch, total = [], 0
    for r in gs.records("BST902T"):
        naam = r.get("THNM50") or r.get("THNM25") or r.get("THNM15") or ""
        batch.append((r["TSNR"], r["TSITNR"], naam))
        if len(batch) >= _BATCH:
            con.executemany(sql, batch)
            total += len(batch)
            batch.clear()
    if batch:
        con.executemany(sql, batch)
        total += len(batch)
    return total


def build(db_path: Path | str = DEFAULT_DB_PATH, data_dir: Path | str = DEFAULT_DATA_DIR) -> None:
    gs = Gstandaard(data_dir)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode = OFF")
        con.execute("PRAGMA synchronous = OFF")
        for table, (cols, bestand, rubrieken) in _TABLES.items():
            _create_table(con, table, cols)
            n = _fill_table(con, gs, table, cols, bestand, rubrieken)
            print(f"  {table:10} {n:>8} records uit {bestand}")
        n = _fill_thesaurus(con, gs)
        print(f"  {'thesaurus':10} {n:>8} records uit BST902T")

        for name, table, cols in _INDEXES:
            con.execute(f"CREATE INDEX {name} ON {table} {cols}")
        print(f"  {len(_INDEXES)} indexen aangemaakt")

        con.commit()
        con.execute("ANALYZE")
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()

    aard = "geverifieerd" if db_path.exists() else "ONTBREEKT"
    print(f"Klaar: {db_path} ({db_path.stat().st_size // 1024 // 1024} MB, {aard})")


if __name__ == "__main__":
    print("G-standaard -> SQLite")
    build()
