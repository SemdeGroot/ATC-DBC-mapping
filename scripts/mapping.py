"""Map Farmacotherapeutisch Kompas indication entries to IKNL tumorgroepen.

The mapping is keyword based. Each IKNL tumorgroep slug lists the clinical terms
(often Latin, e.g. 'mamma') found in Kompas indication texts. Matching runs on the
heading and bullet text together, so a treatment-line bullet inherits the tumor
named in its heading. SYNONYMS use substring matching; ABBREVIATIONS use whole-word
matching because short codes like 'HL' are unsafe as substrings.

Non-oncologic indications (e.g. multiple sclerose, reumatoide artritis, ziekte van
Crohn) deliberately stay unmatched, so they remain visible instead of being forced
into a tumor group.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scripts.iknl import Tumorgroep
from scripts.kompas import IndicationEntry, KompasIndications

SYNONYMS: dict[str, list[str]] = {
    # 'mamma' alone would also match 'mammalian target of rapamycin' (mTOR).
    "borstkanker": ["mammacarcinoom", "borstkanker", "borst"],
    "longkanker": ["longcarcinoom", "longkanker", "bronchuscarcinoom"],
    "darmkanker": ["colon", "colorect", "rectumcarcinoom", "rectaal", "darmkanker", "coecum", "sigmoid", "sigmoïd"],
    "eierstokkanker": ["ovarium", "ovarieel", "eierstok", "tuba", "peritoneum", "peritoneaal"],
    # 'endometri' alone would also match endometriose and endometrioid ovarian
    # carcinoma, so the carcinoma is required explicitly.
    "baarmoederkanker": ["endometriumcarcinoom", "endometriumkanker", "baarmoederkanker", "baarmoederlichaam", "corpus uteri"],
    "baarmoederhalskanker": ["cervix", "baarmoederhals"],
    "blaaskanker": ["blaascarcinoom", "blaaskanker", "urotheel", "urineblaas"],
    "nierkanker": ["niercel", "nierkanker", "niercarcinoom"],
    "prostaatkanker": ["prostaat"],
    "zaadbalkanker": ["testis", "testikel", "zaadbal", "kiemcel", "germinoom"],
    "schildklierkanker": ["schildklier", "thyreo"],
    "huidkanker": [
        "melanoom", "basaalcel", "basocellulair", "merkelcel",
        "plaveiselcelcarcinoom van de huid", "cutaan plaveiselcel", "huidcarcinoom",
    ],
    "bot-en-wekedelenkanker": [
        "sarcoom", "sarcoma", "ewing", "weke delen", "weke-delen", "wekedelen", "gist",
        "stromale tumor", "dermatofibro", "myofibroblast",
    ],
    # 'lymf' alone would also match lymfeklier (lymph node) in solid-tumor staging,
    # so only lymphoma/lymphatic word stems are used.
    "hemato-oncologie": [
        "leukemi", "lymfoom", "lymfat", "lymfoblast", "lymfocyt", "lymfoprolifer",
        "lymfoplasma", "hodgkin", "myeloom", "kahler", "myelodysplas",
        "myeloprolifera", "myelofibros", "polycytemia", "polycythaemia", "polycythemia",
        "trombocytemie", "trombocytose", "mastocytos", "histiocytose",
        "macroglobulinemie", "waldenstrom", "waldenström", "amyloidose", "amyloïdose",
        "plasmacel", "hypereosinofiel",
    ],
    "hoofd-halskanker": [
        "hoofd-hals", "hoofd-/hals", "hoofd en hals", "hals", "larynx", "strottenhoofd",
        "farynx", "keelholte", "mondholte", "nasofar", "orofar", "hypofar", "speekselklier",
    ],
    "slokdarm-en-maagkanker": [
        "slokdarm", "oesofag", "maagcarcinoom", "maag-slokdarm", "maag,", "maag ",
        "gastro-oesofag", "ventrikelcarcinoom",
    ],
    "alvleesklierkanker": ["pancreas", "alvleesklier"],
    "leverkanker": ["levercarcinoom", "leverkanker", "hepatocellul", "hepatocarcin"],
    "hpb-tumoren": ["galweg", "galblaas", "galgang", "cholangio", "ampulla", "periampullair"],
    "hersentumoren": ["hersen", "glio", "astrocyt", "meningeoom", "centraal zenuwstelsel", "medulloblast", "ependymoom"],
    "neuro-endocriene-neoplasie": ["neuro-endocrien", "neuro-endocrine", "neuroendocrien", "carcinoid", "carcinoïd"],
    "vulvakanker": ["vulva"],
    "vaginakanker": ["vagina"],
    "kanker-bij-kinderen": ["neuroblastoom", "nefroblastoom", "wilms"],
    "primaire-tumor-onbekend": ["primaire tumor onbekend", "onbekende primaire tumor"],
}

# Short clinical abbreviations, matched on whole-word boundaries.
ABBREVIATIONS: dict[str, list[str]] = {
    "longkanker": ["sclc", "nsclc"],
    "nierkanker": ["rcc", "ncc"],
    "darmkanker": ["crc"],
    "borstkanker": ["tnbc"],
    "blaaskanker": ["mibc"],
    "schildklierkanker": ["dtc"],
    "prostaatkanker": ["crpc", "mcrpc"],
    "huidkanker": ["mcc", "cscc", "mcscc", "lacscc"],
    "hoofd-halskanker": ["scchn", "hnscc"],
    "slokdarm-en-maagkanker": ["oscc", "gejc"],
    "leverkanker": ["hcc"],
    "hersentumoren": ["cns"],
    "bot-en-wekedelenkanker": ["gist", "dfsp", "desp", "imt"],
    "hemato-oncologie": [
        "hl", "chl", "nhl", "dlbcl", "all", "aml", "cll", "cml", "cmml",
        "mcl", "mds", "mpd", "mpn", "alcl", "salcl", "ctcl", "bl", "bll", "wm",
    ],
}

_ABBREV_PATTERNS: dict[str, re.Pattern[str]] = {
    slug: re.compile(r"\b(?:" + "|".join(re.escape(abbr) for abbr in abbrevs) + r")\b")
    for slug, abbrevs in ABBREVIATIONS.items()
}

# Protein names containing a tumor word that must not be read as a diagnosis.
# 'anaplastisch lymfoomkinase' is the ALK target named in NSCLC indications.
_PROTEIN_NOISE = re.compile(r"anaplastisch[\s-]*lymfoom[\s-]*kinase")


@dataclass
class Coupling:
    context: str
    text: str
    tumorgroepen: list[str] = field(default_factory=list)


def map_text(text: str) -> list[str]:
    lowered = _PROTEIN_NOISE.sub(" ", text.lower())
    slugs = [slug for slug, keywords in SYNONYMS.items() if any(kw in lowered for kw in keywords)]
    for slug, pattern in _ABBREV_PATTERNS.items():
        if slug not in slugs and pattern.search(lowered):
            slugs.append(slug)
    return slugs


def map_entry(entry: IndicationEntry) -> list[str]:
    return map_text(f"{entry.context} {entry.text}")


def couple(indications: KompasIndications, taxonomy: list[Tumorgroep]) -> list[Coupling]:
    name_by_slug = {group.slug: group.name for group in taxonomy}
    couplings = []
    for entry in indications.entries:
        slugs = map_entry(entry)
        names = [name_by_slug.get(slug, slug) for slug in slugs]
        couplings.append(Coupling(context=entry.context, text=entry.text, tumorgroepen=names))
    return couplings
