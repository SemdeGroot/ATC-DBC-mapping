"""Integriteit: geen lege join-sleutels en faithful ZI->ATC-attributie."""
import sqlite3

import pytest

from scripts.gstandaard import DEFAULT_DB_PATH, GstandaardDB


@pytest.fixture(scope="module")
def con():
    if not DEFAULT_DB_PATH.is_file():
        pytest.skip("data/gstandaard.sqlite ontbreekt; draai build_gstandaard_db")
    return sqlite3.connect(DEFAULT_DB_PATH)


@pytest.mark.parametrize("tabel,kolom", [
    ("bst711", "gpk"), ("bst070", "gpk"), ("bst070", "hpk"),
    ("bst004", "hpk"), ("bst004", "zi"), ("bst132", "zi"), ("bst132", "inid"),
    ("bst131", "zi"), ("bst133", "inid"), ("bst020", "nmnr"),
])
def test_geen_lege_join_sleutels(con, tabel, kolom):
    n = con.execute(f"SELECT count(*) FROM {tabel} WHERE {kolom} = '' OR {kolom} IS NULL").fetchone()[0]
    assert n == 0


def test_zi_atc_faithful():
    # Elke ZI van trastuzumab moet terug naar L01FD01 mappen (geen kruisverwijzing).
    db = GstandaardDB()
    zis = db.zis_for_atc("L01FD01")
    assert zis
    assert all(db.atc_for_zi(zi) == "L01FD01" for zi in zis)
