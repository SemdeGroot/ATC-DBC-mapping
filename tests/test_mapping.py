"""Tests voor het deterministische lexicon (laag 1) op echte indicatieteksten."""
import pytest

from scripts.mapping import map_text

POSITIEF = [
    ("gemetastaseerd mammacarcinoom", "borstkanker"),
    ("BC, m, HER2+, >= 3e lijn, mono (Volw.)", "borstkanker"),
    ("Palliatie bij gevorderd, castratieresistent prostaatcarcinoom", "prostaatkanker"),
    ("CRPC, m, voor chemo, combi met prednison (Volw. Man)", "prostaatkanker"),
    ("NSCLC, LA of m, EGFR+, mono (Volw.)", "longkanker"),
    ("Maligniteit pleura, mesothelioom", "longkanker"),
    ("Diabetes mellitus, geen subcutane insuline mogelijk (Volw)", "diabetes"),
    ("Morbide obesitas bij volwassenen", "obesitas"),
    ("Gevorderd endometriumcarcinoom", "endometriumcarcinoom"),
    ("Gemetastaseerd maagcarcinoom (HER2-positief)", "maag-slokdarmkanker"),
]

GEEN = [
    "non-Hodgkinlymfoom",
    "Zeer actieve, recidiverende multiple sclerose (MS)",
    "CLL (Volw.)",
    "mammalian target of rapamycine (mTOR)-remmer",  # ruis: geen borstkanker
    "endometriose",                                   # geen endometriumcarcinoom
    "Auto-immuunziekte (Volw.)",
]


@pytest.mark.parametrize("tekst,slug", POSITIEF)
def test_positieve_treffers(tekst, slug):
    assert map_text(tekst) == slug


@pytest.mark.parametrize("tekst", GEEN)
def test_geen_of_ambigue_defert(tekst):
    assert map_text(tekst) is None


def test_meerdere_treffers_defert():
    # twee ziektebeelden in een tekst -> geen harde lexicon-keuze
    assert map_text("mammacarcinoom en prostaatcarcinoom") is None
