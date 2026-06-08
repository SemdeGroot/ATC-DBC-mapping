"""Laag 1 van de matching: deterministisch lexicon indicatietekst -> DBC-ziektebeeld.

Hoge-precisie keyword-/afkortingstabel. `map_text()` levert alleen een ziektebeeld
als precies een ziektebeeld matcht; bij geen of meerdere treffers geeft het None terug
en bepalen de embedding- en LLM-laag (en de HITL) de uitkomst. "Geen" wordt hier dus
nooit hard geclaimd - alleen positieve, eenduidige treffers.

De slugs komen uit scripts.dbc.ZIEKTEBEELDEN.
"""
from __future__ import annotations

import re

# Eiwit-/doelwitnamen die een tumorwoord bevatten maar geen diagnose zijn; weghalen
# voor het matchen (bv. "mammalian target" -> mamma, "anaplastisch lymfoomkinase" -> lymfoom).
NOISE = (
    "mammalian target",
    "anaplastisch lymfoomkinase",
    "epidermale groeifactorreceptor",
)

# Ziektebeeld -> substring-keywords (lowercase). Specifiek gekozen om niet-onco en
# verkeerde tumoren niet mee te nemen (bv. "endometrium" niet "endometri" i.v.m. endometriose).
SYNONYMS: dict[str, tuple[str, ...]] = {
    "borstkanker": ("borstkanker", "mammacarcinoom", "mammacarc", "mamma tumor", "mamma,"),
    "prostaatkanker": ("prostaatkanker", "prostaatcarcinoom", "prostaatcarc", "castratieresistent", "castratie-resistent"),
    "longkanker": (
        "longkanker", "longcarcinoom", "niet-kleincellig", "kleincellig long",
        "bronchuscarcinoom", "mesothelioom", "thymoom", "pleuracarcinoom",
        "niet-kleincellige long", "kleincellige long",
    ),
    "darmkanker": (
        "darmkanker", "colorectaal", "colorectale", "coloncarcinoom", "colorectaalcarcinoom",
        "rectumcarcinoom", "coloncarc", "hnpcc",
    ),
    "maag-slokdarmkanker": (
        "maagcarcinoom", "slokdarmcarcinoom", "oesofaguscarcinoom", "oesofagus/cardia",
        "maag-slokdarm", "gastro-oesofageale", "slokdarmkanker", "maagkanker",
        "oesofaguskanker", "cardiacarcinoom",
    ),
    "hoofd-halskanker": (
        "hoofd-hals", "hoofd-halskanker", "larynxcarcinoom", "farynxcarcinoom",
        "orofarynx", "hypofarynx", "nasofarynx", "cavum oris", "speekselklier",
        "plaveiselcelcarcinoom van het hoofd", "hals-",
    ),
    "alvleesklierkanker": ("alvleesklierkanker", "pancreascarcinoom", "pancreaskanker", "alvleeskliercarcinoom"),
    "melanoom": ("melanoom", "melanoma"),
    "ovariumcarcinoom": ("ovariumcarcinoom", "ovariumcarc", "eierstokkanker", "epitheliaal ovarium", "tubacarcinoom"),
    "cervixcarcinoom": ("cervixcarcinoom", "cervixcarc", "baarmoederhalskanker"),
    "endometriumcarcinoom": ("endometriumcarcinoom", "endometriumkanker", "baarmoederkanker", "endometriumcarc"),
    "vulvacarcinoom": ("vulvacarcinoom", "vulvacarc", "vaginacarcinoom"),
    "diabetes": ("diabetes mellitus", "type 2-diabetes", "type 1-diabetes", "diabetes type"),
    "obesitas": ("obesitas", "morbide obesitas", "chronisch gewichtsbeheer", "gewichtsbeheersing", "overgewicht"),
}

# Ziektebeeld -> afkortingen (woordgrens, hoofdletterongevoelig). De add-on INKORT-teksten
# leunen sterk op deze afkortingen (bv. "BC, m, HER2+", "NSCLC, LA of m", "CRPC").
ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    # NB: HER2 is geen borstkanker-marker per se (ook HER2+ maagcarcinoom); niet opnemen.
    "borstkanker": ("BC", "EBC", "MBC"),
    "prostaatkanker": ("CRPC", "mCRPC", "nmCRPC", "mHSPC"),
    "longkanker": ("NSCLC", "SCLC"),
    "darmkanker": ("CRC", "mCRC"),
    "maag-slokdarmkanker": ("GEJ",),
    "hoofd-halskanker": ("SCCHN", "HNSCC"),
}


def _normaliseer(tekst: str) -> str:
    laag = tekst.lower()
    for ruis in NOISE:
        laag = laag.replace(ruis, " ")
    return laag


def kandidaten(tekst: str) -> set[str]:
    """Alle ziektebeeld-slugs waarvan een keyword of afkorting in de tekst voorkomt."""
    laag = _normaliseer(tekst)
    gevonden: set[str] = set()
    for slug, kws in SYNONYMS.items():
        if any(kw in laag for kw in kws):
            gevonden.add(slug)
    for slug, toks in ABBREVIATIONS.items():
        if any(re.search(rf"\b{tok}\b", tekst, re.IGNORECASE) for tok in toks):
            gevonden.add(slug)
    return gevonden


def map_text(tekst: str) -> str | None:
    """Geef het ziektebeeld terug als precies een ziektebeeld matcht, anders None."""
    gevonden = kandidaten(tekst)
    return next(iter(gevonden)) if len(gevonden) == 1 else None
