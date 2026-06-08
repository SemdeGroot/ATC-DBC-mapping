"""DBC-ziektebeelden, codes en ICD-10 uit de DICA/DMA-inclusiecriteria-PDF.

Parseert de PDF regel voor regel (pdfplumber) met een kleine toestandsmachine:
per categoriekop volgen DBC-coderegels (specialisme_code, diagnose_code,
omschrijving) en/of ICD-10-regels. De gynaecologische ICD-10-lijst staat
gebundeld onderaan en wordt op ICD-prefix naar het juiste sub-carcinoom gerouteerd.

Per ziektebeeld levert `referentieprofiel()` de doeltekst voor de embedding-laag.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = _ROOT / "data" / "iknl-dbc" / "25-11-2025-Inclusiecriteria-DICA-Geneesmiddelen-DBC.pdf"

# Canonieke ziektebeelden (slug -> weergavenaam). Doel-labelset van de matching.
ZIEKTEBEELDEN = {
    "darmkanker": "darmkanker",
    "longkanker": "longkanker",
    "borstkanker": "borstkanker",
    "prostaatkanker": "prostaatkanker",
    "ovariumcarcinoom": "ovariumcarcinoom",
    "vulvacarcinoom": "vulvacarcinoom",
    "endometriumcarcinoom": "endometriumcarcinoom",
    "cervixcarcinoom": "cervixcarcinoom",
    "maag-slokdarmkanker": "maag-slokdarmkanker",
    "hoofd-halskanker": "hoofd-halskanker",
    "alvleesklierkanker": "alvleesklierkanker",
    "diabetes": "diabetes",
    "melanoom": "melanoom",
    "obesitas": "obesitas",
}

# Koppen "<naam> inclusie criteria" -> slug.
_INCLUSIE_KOP = {
    "darmkanker": "darmkanker",
    "longkanker": "longkanker",
    "borstkanker": "borstkanker",
    "prostaatkanker": "prostaatkanker",
    "maag-slokdarmkanker": "maag-slokdarmkanker",
    "hoofd-halskanker": "hoofd-halskanker",
}
# Losse koppen (eigen regel).
_LOSSE_KOP = {"alvleesklierkanker", "diabetes", "melanoom", "obesitas"}
# Gynaecologische sub-koppen (eigen regel met dubbele punt).
_GYNAE_SUB = {
    "ovariumcarcinoom": "ovariumcarcinoom",
    "vulvacarcinoom": "vulvacarcinoom",
    "endometriumcarcinoom": "endometriumcarcinoom",
    "cervixcarcinoom": "cervixcarcinoom",
}

_DBC_HEADER = "specialisme_code diagnose_code omschrijving"
_ICD_HEADER = "icd-10 code icd-10 description"

_DBC_ROW = re.compile(r"^(\d{3})\s+([A-Za-z]?\d+)\s+(.+)$")
_ICD_ROW = re.compile(r"^([A-Z]\d{1,3}(?:\.\w+)?)\s+(.+)$")
_FOOTER = re.compile(r"^Date:|page \d+ of \d+")
_INTRO = re.compile(r"^(Inclusie van|diagnose|specialisme codes|\d+\.\s)", re.IGNORECASE)


@dataclass(frozen=True)
class DbcCode:
    specialisme_code: str
    diagnose_code: str
    omschrijving: str


@dataclass(frozen=True)
class Icd10Code:
    code: str
    omschrijving: str


@dataclass
class Ziektebeeld:
    slug: str
    naam: str
    dbc_codes: list[DbcCode] = field(default_factory=list)
    icd10: list[Icd10Code] = field(default_factory=list)

    def referentieprofiel(self) -> str:
        """Doeltekst voor de embedding-laag: naam + omschrijvingen + ICD-beschrijvingen."""
        delen = [self.naam]
        delen += [c.omschrijving for c in self.dbc_codes]
        delen += [c.omschrijving for c in self.icd10]
        # dedup met behoud van volgorde
        gezien, uniek = set(), []
        for d in delen:
            d = d.strip()
            if d and d.lower() not in gezien:
                gezien.add(d.lower())
                uniek.append(d)
        return " | ".join(uniek)


def _gynae_slug_voor_icd(code: str) -> str | None:
    if code.startswith(("C51", "C52")):
        return "vulvacarcinoom"
    if code.startswith("C53"):
        return "cervixcarcinoom"
    if code.startswith(("C54", "C55")):
        return "endometriumcarcinoom"
    if code.startswith(("C56", "C57")):
        return "ovariumcarcinoom"
    return None


def load_ziektebeelden(pdf_path: Path | str = DEFAULT_PDF) -> dict[str, Ziektebeeld]:
    """Parse de PDF naar {slug: Ziektebeeld} voor alle 14 ziektebeelden."""
    zb = {slug: Ziektebeeld(slug, naam) for slug, naam in ZIEKTEBEELDEN.items()}

    huidig: str | None = None       # actieve ziektebeeld-slug
    modus: str | None = None        # 'dbc' | 'icd' | None
    gynae = False                   # binnen de gynaecologische sectie
    laatste: DbcCode | Icd10Code | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for ln in page.extract_text_lines():
                tekst = " ".join(ln["text"].split())
                if not tekst or _FOOTER.search(tekst):
                    continue
                laag = tekst.lower()

                # -- koppen --
                if laag.endswith("inclusie criteria"):
                    naam = laag[: -len("inclusie criteria")].strip()
                    if naam == "gynaecologische kanker":
                        gynae, huidig, modus, laatste = True, None, None, None
                    elif naam in _INCLUSIE_KOP:
                        gynae, huidig, modus, laatste = False, _INCLUSIE_KOP[naam], None, None
                    continue
                if laag in _LOSSE_KOP:
                    gynae, huidig, modus, laatste = False, laag, None, None
                    continue
                if laag.rstrip(":") in _GYNAE_SUB and gynae:
                    huidig, modus, laatste = _GYNAE_SUB[laag.rstrip(":")], None, None
                    continue

                # -- sectiekoppen --
                if laag == _DBC_HEADER:
                    modus, laatste = "dbc", None
                    continue
                if laag == _ICD_HEADER:
                    modus, laatste = "icd", None
                    continue
                if _INTRO.search(tekst):
                    continue

                # -- dataregels --
                if modus == "dbc":
                    m = _DBC_ROW.match(tekst)
                    if m and huidig:
                        code = DbcCode(m.group(1), m.group(2), m.group(3).strip())
                        zb[huidig].dbc_codes.append(code)
                        laatste = code
                    elif laatste is not None and isinstance(laatste, DbcCode):
                        _verleng(zb, huidig, laatste, tekst, "dbc")
                        laatste = zb[huidig].dbc_codes[-1]
                elif modus == "icd":
                    m = _ICD_ROW.match(tekst)
                    if m:
                        doel = _gynae_slug_voor_icd(m.group(1)) if gynae else huidig
                        if doel:
                            code = Icd10Code(m.group(1), m.group(2).strip())
                            zb[doel].icd10.append(code)
                            laatste = code
                    elif laatste is not None and isinstance(laatste, Icd10Code) and not gynae and huidig:
                        _verleng(zb, huidig, laatste, tekst, "icd")
                        laatste = zb[huidig].icd10[-1]

    # dedup binnen elk ziektebeeld (de PDF herhaalt enkele prostaatregels)
    for z in zb.values():
        z.dbc_codes = list(dict.fromkeys(z.dbc_codes))
        z.icd10 = list(dict.fromkeys(z.icd10))
    return zb


def _verleng(zb, slug, laatste, tekst, soort):
    """Voeg een omgebroken vervolgregel toe aan de omschrijving van het laatste item."""
    lijst = zb[slug].dbc_codes if soort == "dbc" else zb[slug].icd10
    nieuw = (
        DbcCode(laatste.specialisme_code, laatste.diagnose_code, f"{laatste.omschrijving} {tekst}".strip())
        if soort == "dbc"
        else Icd10Code(laatste.code, f"{laatste.omschrijving} {tekst}".strip())
    )
    lijst[-1] = nieuw
