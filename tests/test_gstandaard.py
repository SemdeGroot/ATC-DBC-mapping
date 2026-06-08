"""Tests voor de G-standaard-parser tegen de echte uitgepakte G-standaard."""
import pytest

from scripts.gstandaard import Gstandaard

TRASTUZUMAB = "L01FD01"   # add-on, indicatie borst-/maagkanker
SIMVASTATINE = "C10AA01"  # niet-add-on referentie


@pytest.fixture(scope="module")
def g():
    return Gstandaard()


def test_layout_uit_bst001_volgt_zindex(g):
    # ATCODE in BST711 begint volgens de Z-Index-layout op positie 119 (0-based 118).
    veld = next(f for f in g._layouts["BST711T"] if f.rubriek == "ATCODE")
    assert (veld.start, veld.end) == (118, 126)


def test_trastuzumab_keten_en_addon(g):
    zis = g.zis_for_atc(TRASTUZUMAB)
    assert zis, "verwacht ZI-nummers voor trastuzumab"
    assert any(g.is_addon(zi) for zi in zis), "trastuzumab hoort add-on te zijn"
    assert g.atc_for_zi(zis[0]) == TRASTUZUMAB

    stof = g.stofnaam_for_atc(TRASTUZUMAB)
    assert stof and "trastuzumab" in stof.lower()


def test_trastuzumab_addon_indicaties(g):
    inds = g.addon_indicaties_for_atc(TRASTUZUMAB)
    assert inds, "verwacht add-on-indicatieteksten"
    tekst = " ".join(i["inkort"] for i in inds).lower()
    assert any(term in tekst for term in ("mamma", "borst", "her2", "maag"))
    assert all(i["inid"] and i["inkort"] for i in inds)


def test_niet_addon_heeft_geen_addon_indicaties(g):
    assert g.zis_for_atc(SIMVASTATINE), "verwacht ZI-nummers voor simvastatine"
    assert g.addon_indicaties_for_atc(SIMVASTATINE) == []
