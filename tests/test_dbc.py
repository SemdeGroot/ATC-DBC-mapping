"""Tests voor de DBC-PDF-parser tegen de DICA/DMA-inclusiecriteria 2025."""
import pytest

from scripts.dbc import ZIEKTEBEELDEN, load_ziektebeelden


@pytest.fixture(scope="module")
def zb():
    return load_ziektebeelden()


def _heeft(z, spec, diag):
    return any(c.specialisme_code == spec and c.diagnose_code == diag for c in z.dbc_codes)


def test_alle_veertien_ziektebeelden(zb):
    assert set(zb) == set(ZIEKTEBEELDEN)
    assert len(zb) == 14


def test_dbc_codes_per_ziektebeeld(zb):
    assert len(zb["darmkanker"].dbc_codes) == 6
    assert _heeft(zb["darmkanker"], "303", "333")
    for spec, diag in (("303", "318"), ("313", "811"), ("361", "105")):
        assert _heeft(zb["borstkanker"], spec, diag)
    assert _heeft(zb["longkanker"], "322", "1305")  # mesothelioom valt onder longkanker
    assert _heeft(zb["diabetes"], "313", "221")
    assert _heeft(zb["obesitas"], "303", "342")
    assert _heeft(zb["melanoom"], "303", "350")
    assert _heeft(zb["cervixcarcinoom"], "307", "M13")


def test_prostaat_dedupliceert(zb):
    codes = zb["prostaatkanker"].dbc_codes
    assert len(codes) == len(set(codes)) == 4


def test_gynae_icd_routing_op_prefix(zb):
    assert [c.code for c in zb["vulvacarcinoom"].icd10][0] == "C51"
    assert all(c.code.startswith("C53") for c in zb["cervixcarcinoom"].icd10)
    assert all(c.code.startswith(("C54", "C55")) for c in zb["endometriumcarcinoom"].icd10)
    assert all(c.code.startswith(("C56", "C57")) for c in zb["ovariumcarcinoom"].icd10)


def test_alvleesklier_icd_en_dbc(zb):
    assert any(c.code == "C170" for c in zb["alvleesklierkanker"].icd10)
    assert _heeft(zb["alvleesklierkanker"], "313", "964")


def test_referentieprofiel_bevat_omschrijvingen(zb):
    profiel = zb["borstkanker"].referentieprofiel().lower()
    assert "borstkanker" in profiel and "mamma" in profiel
