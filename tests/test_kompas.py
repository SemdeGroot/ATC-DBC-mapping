"""Tests voor de Kompas-preparaattekst-parser (offline, op een fixture)."""
from scripts import kompas

_MD = """# Trastuzumab

*Geneesmiddel | overige antineoplastische middelen | L01FD01*

## Samenstelling

Iets over samenstelling.

## Indicaties

- Gemetastaseerde [borstkanker](https://x/borstkanker) (HER2-positief);
- Vroege borstkanker, adjuvant.
- Gemetastaseerd maagcarcinoom (HER2-positief).

Gerelateerde informatie [borstkanker](https://x/borstkanker)

## Doseringen

Iets over dosering.
"""


def test_parse_atc_titel_en_indicaties():
    p = kompas.parse(_MD, slug="abc")
    assert p.titel == "Trastuzumab"
    assert p.atc == "L01FD01"
    assert p.indicaties == [
        "Gemetastaseerde borstkanker (HER2-positief)",
        "Vroege borstkanker, adjuvant",
        "Gemetastaseerd maagcarcinoom (HER2-positief)",
    ]


def test_in_scope():
    assert kompas.in_scope("L01FD01")      # oncologie
    assert kompas.in_scope("A10BJ02")      # diabetes/obesitas (GLP-1)
    assert kompas.in_scope("A08AB01")      # obesitas
    assert not kompas.in_scope("C10AA01")  # statine
    assert not kompas.in_scope(None)
