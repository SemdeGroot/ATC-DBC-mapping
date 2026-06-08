"""Tests voor de G-standaard-parser en SQLite-cache tegen de echte G-standaard."""
import pytest

from scripts import build_gstandaard_db
from scripts.gstandaard import Gstandaard, GstandaardDB

TRASTUZUMAB = "L01FD01"   # add-on, indicatie borst-/maagkanker
SIMVASTATINE = "C10AA01"  # niet-add-on referentie


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("gs") / "gstandaard.sqlite"
    build_gstandaard_db.build(db_path=path)
    return GstandaardDB(path)


def test_layout_uit_bst001_volgt_zindex():
    # ATCODE in BST711 begint volgens de Z-Index-layout op positie 119 (0-based 118).
    gs = Gstandaard()
    veld = next(f for f in gs.layouts["BST711T"] if f.rubriek == "ATCODE")
    assert (veld.start, veld.end) == (118, 126)


def test_trastuzumab_keten_en_addon(db):
    zis = db.zis_for_atc(TRASTUZUMAB)
    assert zis, "verwacht ZI-nummers voor trastuzumab"
    assert any(db.is_addon(zi) for zi in zis), "trastuzumab hoort add-on te zijn"
    assert db.atc_for_zi(zis[0]) == TRASTUZUMAB

    stof = db.stofnaam_for_atc(TRASTUZUMAB)
    assert stof and "trastuzumab" in stof.lower()


def test_trastuzumab_addon_indicaties(db):
    inds = db.addon_indicaties_for_atc(TRASTUZUMAB)
    assert inds, "verwacht add-on-indicatieteksten"
    tekst = " ".join(i["inkort"] for i in inds).lower()
    assert any(term in tekst for term in ("mamma", "borst", "her2", "maag", "bc,"))
    assert all(i["inid"] and i["inkort"] for i in inds)
    # indicatie-aard moet via thesaurus 1901 worden gelabeld.
    assert any(i["indicatie_aard"] for i in inds)


def test_niet_addon_heeft_geen_addon_indicaties(db):
    assert db.zis_for_atc(SIMVASTATINE), "verwacht ZI-nummers voor simvastatine"
    assert db.addon_indicaties_for_atc(SIMVASTATINE) == []
