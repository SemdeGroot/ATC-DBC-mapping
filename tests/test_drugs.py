"""Integratietest voor de universum-assemblage (G-standaard + Kompas-cache)."""
import pytest

from scripts import drugs


@pytest.fixture(scope="module")
def universe():
    return drugs.build_universe()


def test_universum_bevat_scope(universe):
    assert len(universe) > 200  # ~331 in-scope ATC7
    assert all(atc.startswith(("L", "A10", "A08")) for atc in universe)


def test_trastuzumab_heeft_beide_bronnen(universe):
    g = universe["L01FD01"]
    assert "trastuzumab" in g.stofnaam.lower()
    assert g.addon, "verwacht add-on-indicaties"
    assert g.kompas_indicaties, "verwacht Kompas-indicaties"
    assert all({"inid", "inkort", "indicatie_aard"} <= set(i) for i in g.addon)
