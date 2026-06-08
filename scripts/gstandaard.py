"""G-standaard inlezen volgens de Z-Index-bestandsbeschrijving.

De veldposities worden afgeleid uit BST001T (de rubrieken-dictionary van de
G-standaard zelf): per bestand de rubrieken gesorteerd op volgnummer, met de
recordpositie als cumulatieve som van de rubriekslengtes. Zo volgt de parser
exact wat Z-Index beschrijft, zonder hardcoded posities.

Koppelketen (productniveau -> stofniveau):
    ZI-nummer --BST004--> HPK --BST070--> GPK --BST711--> ATC-code
    GPK --BST711(GPSTNR)--> BST020 --> stofnaam
Add-on:
    ZI in BST131 = add-on; ZI --BST132--> INID --BST133--> INKORT (indicatietekst)
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

ENCODING = "latin-1"

# Standaardlocatie van de uitgepakte G-standaard (79 BST-bestanden).
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "g-standaard" / "extracted"

# Bootstrap-layout om BST001T zelf te lezen. Posities (0-based, half-open) volgen
# uit de zelfbeschrijving van BST001T (rubrieken MDBST/MDVNR/MDRNAM/MDRTYP/MDRLEN),
# waarbij de positie de cumulatieve som van de voorgaande rubriekslengtes is.
_B001_BESTAND = (5, 25)    # MDBST   naam van het bestand
_B001_VOLGNR = (25, 28)    # MDVNR   volgnummer (veldvolgorde)
_B001_RUBRIEK = (28, 38)   # MDRNAM  naam van de rubriek
_B001_TYPE = (98, 99)      # MDRTYP  type (A/N)
_B001_LENGTE = (99, 103)   # MDRLEN  lengte

# Mutatiecode: 2 = vervallen record; die slaan we over zodat alleen actuele
# records meedoen.
_MUTKOD_VERVALLEN = "2"


@dataclass(frozen=True)
class Field:
    rubriek: str
    type: str
    start: int  # 0-based
    end: int    # half-open


class Gstandaard:
    """Leest de G-standaard-BST-bestanden volgens de BST001T-rubriekdefinitie."""

    def __init__(self, data_dir: Path | str = DEFAULT_DATA_DIR):
        self.dir = Path(data_dir)
        if not self.dir.is_dir():
            raise FileNotFoundError(f"G-standaard-map niet gevonden: {self.dir}")
        self._layouts = self._build_layouts()

    # -- bestandstoegang -------------------------------------------------

    def _path(self, bestand: str) -> Path:
        """Pad naar een BST-bestand, hoofdletterongevoelig (bv. 'BST711T')."""
        direct = self.dir / bestand
        if direct.is_file():
            return direct
        target = bestand.upper()
        for f in self.dir.iterdir():
            if f.name.upper() == target:
                return f
        raise FileNotFoundError(f"BST-bestand {bestand} niet in {self.dir}")

    def _build_layouts(self) -> dict[str, list[Field]]:
        """Bouw per bestand de veld-layout uit BST001T (cumulatieve posities)."""
        raw: dict[str, list[tuple[int, str, str, int]]] = {}
        with open(self._path("BST001T"), encoding=ENCODING) as fh:
            for line in fh:
                bestand = line[_B001_BESTAND[0]:_B001_BESTAND[1]].strip()
                if not bestand:
                    continue
                volgnr = int(line[_B001_VOLGNR[0]:_B001_VOLGNR[1]])
                rubriek = line[_B001_RUBRIEK[0]:_B001_RUBRIEK[1]].strip()
                typ = line[_B001_TYPE[0]:_B001_TYPE[1]]
                lengte = int(line[_B001_LENGTE[0]:_B001_LENGTE[1]])
                raw.setdefault(bestand, []).append((volgnr, rubriek, typ, lengte))

        layouts: dict[str, list[Field]] = {}
        for bestand, fields in raw.items():
            fields.sort()  # op volgnummer = fysieke veldvolgorde
            pos = 0
            built: list[Field] = []
            for _volgnr, rubriek, typ, lengte in fields:
                built.append(Field(rubriek, typ, pos, pos + lengte))
                pos += lengte
            layouts[bestand] = built
        return layouts

    def records(self, bestand: str, skip_vervallen: bool = True):
        """Yield elk record als dict {rubriekcode: waarde} (waarden gestript)."""
        layout = self._layouts[bestand]
        with open(self._path(bestand), encoding=ENCODING) as fh:
            for line in fh:
                rec = {f.rubriek: line[f.start:f.end].strip() for f in layout}
                if skip_vervallen and rec.get("MUTKOD") == _MUTKOD_VERVALLEN:
                    continue
                yield rec

    # -- koppellookups (lui opgebouwd, een keer) -------------------------

    @cached_property
    def _zi_to_hpk(self) -> dict[str, str]:
        # In BST004 heet het ZI-nummer ATKODE (artikelkode); HPKODE is het handelsproduct.
        return {r["ATKODE"]: r["HPKODE"] for r in self.records("BST004T") if r["HPKODE"]}

    @cached_property
    def _hpk_to_gpk(self) -> dict[str, str]:
        return {r["HPKODE"]: r["GPKODE"] for r in self.records("BST070T") if r["GPKODE"]}

    @cached_property
    def _gpk_info(self) -> dict[str, tuple[str, str]]:
        """GPK -> (ATC-code, naamnummer GPK-stofnaam)."""
        return {
            r["GPKODE"]: (r["ATCODE"], r["GPSTNR"])
            for r in self.records("BST711T")
            if r["GPKODE"]
        }

    @cached_property
    def _naam(self) -> dict[str, str]:
        return {r["NMNR"]: r["NMNAAM"] for r in self.records("BST020T")}

    @cached_property
    def _addon_zis(self) -> set[str]:
        return {r["ZINR"] for r in self.records("BST131T") if r["ZINR"]}

    @cached_property
    def _inid_to_inkort(self) -> dict[str, str]:
        return {r["INID"]: r["INKORT"] for r in self.records("BST133T") if r["INID"]}

    @cached_property
    def _zi_to_indicaties(self) -> dict[str, list[tuple[str, str]]]:
        """ZI -> lijst van (INID, INSRT) uit BST132."""
        out: dict[str, list[tuple[str, str]]] = {}
        for r in self.records("BST132T"):
            zi, inid = r["ZINR"], r["INID"]
            if zi and inid:
                out.setdefault(zi, []).append((inid, r["INSRT"]))
        return out

    @cached_property
    def _indicatie_aard(self) -> dict[str, str]:
        """INSRT-code -> label (geregistreerd/off-label/...), thesaurus 1901."""
        return self.thesaurus(1901)

    @cached_property
    def _atc_to_zis(self) -> dict[str, list[str]]:
        """ATC-code -> lijst ZI-nummers (geinverteerde productketen)."""
        out: dict[str, list[str]] = {}
        for zi, hpk in self._zi_to_hpk.items():
            gpk = self._hpk_to_gpk.get(hpk)
            if not gpk:
                continue
            info = self._gpk_info.get(gpk)
            if not info:
                continue
            atc = info[0]
            if atc and atc != "Z":
                out.setdefault(atc, []).append(zi)
        return out

    # -- publieke API ----------------------------------------------------

    def atc_for_zi(self, zi: str) -> str | None:
        hpk = self._zi_to_hpk.get(zi)
        gpk = self._hpk_to_gpk.get(hpk) if hpk else None
        info = self._gpk_info.get(gpk) if gpk else None
        return info[0] if info and info[0] and info[0] != "Z" else None

    def zis_for_atc(self, atc: str) -> list[str]:
        return self._atc_to_zis.get(atc, [])

    def stofnaam_for_atc(self, atc: str) -> str | None:
        """Stofnaam via een GPK van deze ATC (GPSTNR -> BST020)."""
        for zi in self.zis_for_atc(atc):
            gpk = self._hpk_to_gpk.get(self._zi_to_hpk.get(zi, ""), "")
            info = self._gpk_info.get(gpk)
            if info and info[1]:
                naam = self._naam.get(info[1])
                if naam:
                    return naam
        return None

    def is_addon(self, zi: str) -> bool:
        return zi in self._addon_zis

    def addon_indicaties_for_atc(self, atc: str) -> list[dict]:
        """Distinct add-on-indicaties voor een ATC.

        Per indicatie: INID, de INKORT-tekst en de INSRT-code (type indicatie).
        Gefilterd op de add-on-ZI's van de ATC; gededupliceerd op INID.
        """
        seen: dict[str, dict] = {}
        for zi in self.zis_for_atc(atc):
            if not self.is_addon(zi):
                continue
            for inid, insrt in self._zi_to_indicaties.get(zi, []):
                if inid in seen:
                    continue
                tekst = self._inid_to_inkort.get(inid)
                if tekst:
                    seen[inid] = {
                        "inid": inid,
                        "inkort": tekst,
                        "insrt": insrt,
                        "indicatie_aard": self._indicatie_aard.get(insrt, ""),
                    }
        return list(seen.values())

    def thesaurus(self, nummer: int) -> dict[str, str]:
        """Thesaurusitems (BST902) voor een thesaurusnummer: itemnummer -> naam."""
        nr = str(nummer)
        out: dict[str, str] = {}
        for r in self.records("BST902T"):
            if r.get("TSNR") == nr and r.get("TSITNR"):
                out[r["TSITNR"]] = r.get("THNM50") or r.get("THNM25") or r.get("THNM15", "")
        return out
