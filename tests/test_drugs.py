"""Integratietest voor de universum-assemblage (per ATC7, Kompas geunioneerd)."""
import pytest

from scripts import drugs


@pytest.fixture(scope="module")
def universe():
    return drugs.build_universe()


def test_universum_per_atc7(universe):
    assert len(universe) > 300  # ~331 in-scope ATC7
    assert all(atc.startswith(("L", "A10", "A08")) for atc in universe)
    assert all(atc == g.atc7 for atc, g in universe.items())


def test_trastuzumab_heeft_beide_bronnen(universe):
    g = universe["L01FD01"]
    assert "trastuzumab" in g.stofnaam.lower()
    assert g.addon, "verwacht add-on-indicaties"
    assert g.kompas_indicaties, "verwacht Kompas-indicaties"
    assert all({"inid", "inkort", "indicatie_aard"} <= set(i) for i in g.addon)


def test_meerdere_formuleringen_geunioneerd(universe):
    # L01DB01: gewone + liposomale doxorubicine vallen onder een ATC7-entry, beide titels bekend.
    g = universe["L01DB01"]
    assert len(g.titels) >= 2
    assert any("liposom" in t.lower() for t in g.titels)
