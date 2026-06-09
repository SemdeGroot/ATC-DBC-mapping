"""Tests voor de diff tegen de oude DMA-lijst (parsing + exclusie-inversie)."""
from dataclasses import dataclass, field

import pytest

from scripts.diff_oude_lijst import (
    OUDE_LIJST_PAD,
    SHEET_NAAR_SLUG,
    diff_per_slug,
    oude_inclusie_per_slug,
    parse_oude_lijst,
)


@dataclass
class _Mid:
    atc7: str
    stofnaam: str = ""
    addon: list = field(default_factory=list)


@pytest.fixture(scope="module")
def parsed():
    return parse_oude_lijst()


def test_mapping_dekt_alle_bladen():
    import openpyxl

    wb = openpyxl.load_workbook(OUDE_LIJST_PAD, read_only=True)
    assert set(wb.sheetnames) == set(SHEET_NAAR_SLUG)
    assert len(set(SHEET_NAAR_SLUG.values())) == 14  # 1-op-1 op de 14 ziektebeelden
    wb.close()


def test_evs_only_blad(parsed):
    dm = parsed["diabetes"]
    assert not dm["heeft_exclusie"]          # DM heeft alleen een EVS-inclusie-sectie
    assert "A10BJ01" in dm["evs"]            # exenatide
    assert not dm["exclusie"]


def test_exclusie_blad(parsed):
    crc = parsed["darmkanker"]
    assert crc["heeft_exclusie"]
    assert "L01XC02" in crc["exclusie"]      # rituximab uitgesloten voor colorectaal
    assert "L01XA01" in crc["exclusie"]      # cisplatine uitgesloten -> dit is colorectaal
    # CC mapt op cervix, niet op darm: cisplatine blijft daar ingesloten
    assert "L01XA01" not in parsed["cervixcarcinoom"]["exclusie"]


def test_inversie_prefix_dekking():
    universe = {
        "A10AB01": _Mid("A10AB01", "insuline", addon=[{"x": 1}]),   # gedekt door 'A'
        "L01AA01": _Mid("L01AA01", "cyclofosfamide", addon=[{"x": 1}]),  # gedekt door 'L01AA'
        "L01XX99": _Mid("L01XX99", "testmiddel", addon=[{"x": 1}]),  # niet gedekt -> ingesloten
        "L01XX35": _Mid("L01XX35", "exact", addon=[{"x": 1}]),       # exact gedekt
    }
    parsed = {"slug": {"exclusie": {"A", "L01AA", "L01XX35"}, "evs": {}, "heeft_exclusie": True}}
    incl = oude_inclusie_per_slug(parsed, universe)["slug"]["inclusie"]
    assert incl == {"L01XX99": "add-on"}


def test_inversie_zonder_exclusie_alleen_evs():
    universe = {"A10AB01": _Mid("A10AB01", "insuline", addon=[{"x": 1}]),
                "A10BJ01": _Mid("A10BJ01", "exenatide")}
    parsed = {"dm": {"exclusie": set(), "evs": {"A10BJ01": "exenatide", "X99ZZ99": "buiten"},
                     "heeft_exclusie": False}}
    res = oude_inclusie_per_slug(parsed, universe)["dm"]
    assert res["inclusie"] == {"A10BJ01": "EVS"}   # geen inversie van add-on; herkomst EVS
    assert "X99ZZ99" in res["buiten_scope"]        # EVS-code buiten scope apart gemeld


def test_evs_wint_van_inversie():
    # Een code die zowel door de inversie als door EVS komt, krijgt herkomst 'EVS'.
    universe = {"L01XX99": _Mid("L01XX99", "x", addon=[{"x": 1}])}
    parsed = {"s": {"exclusie": {"A"}, "evs": {"L01XX99": "x"}, "heeft_exclusie": True}}
    assert oude_inclusie_per_slug(parsed, universe)["s"]["inclusie"] == {"L01XX99": "EVS"}


def test_diff_indeling():
    universe = {"L01XX99": _Mid("L01XX99", "blijft"), "L02BG03": _Mid("L02BG03", "anastrozol"),
                "L01AA01": _Mid("L01AA01", "verdwijnt")}
    oude = {"borstkanker": {"inclusie": {"L01XX99": "add-on", "L01AA01": "EVS"}, "buiten_scope": {}}}
    nieuw = {"borstkanker": {"L01XX99", "L02BG03"}}
    d = diff_per_slug(oude, nieuw, universe)["borstkanker"]
    assert d["gebleven"] == [("L01XX99", "blijft", "add-on")]
    assert d["nieuw"] == [("L02BG03", "anastrozol", "-")]   # nieuwe code: geen oude herkomst
    assert d["verwijderd"] == [("L01AA01", "verdwijnt", "EVS")]
