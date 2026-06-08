"""G-standaard inlezen volgens de Z-Index-bestandsbeschrijving.

Twee lagen:
- `Gstandaard`: de Z-Index-getrouwe lezer. Veldposities komen uit BST001T (de
  rubrieken-dictionary van de G-standaard zelf): per bestand de rubrieken op
  volgnummer, met de recordpositie als cumulatieve som van de rubriekslengtes.
  Geen hardcoded posities.
- `GstandaardDB`: snelle joins over de SQLite-cache (zie build_gstandaard_db.py).

Koppelketen (productniveau -> stofniveau):
    ZI-nummer --BST004--> HPK --BST070--> GPK --BST711--> ATC-code
    GPK --BST711(GPSTNR)--> BST020 --> stofnaam
Add-on:
    ZI in BST131 = add-on; ZI --BST132--> INID --BST133--> INKORT (indicatietekst)
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

ENCODING = "latin-1"

_ROOT = Path(__file__).resolve().parent.parent
# Standaardlocatie van de uitgepakte G-standaard (79 BST-bestanden) en de SQLite-cache.
DEFAULT_DATA_DIR = _ROOT / "data" / "g-standaard" / "extracted"
DEFAULT_DB_PATH = _ROOT / "data" / "gstandaard.sqlite"

# Bootstrap-layout om BST001T zelf te lezen. Posities (0-based, half-open) volgen
# uit de zelfbeschrijving van BST001T (rubrieken MDBST/MDVNR/MDRNAM/MDRTYP/MDRLEN),
# waarbij de positie de cumulatieve som van de voorgaande rubriekslengtes is.
_B001_BESTAND = (5, 25)    # MDBST   naam van het bestand
_B001_VOLGNR = (25, 28)    # MDVNR   volgnummer (veldvolgorde)
_B001_RUBRIEK = (28, 38)   # MDRNAM  naam van de rubriek
_B001_TYPE = (98, 99)      # MDRTYP  type (A/N)
_B001_LENGTE = (99, 103)   # MDRLEN  lengte

# Mutatiecode 2 = vervallen record; overslaan zodat alleen actuele records meedoen.
_MUTKOD_VERVALLEN = "2"

# Thesaurus voor de aard van een add-on-indicatie (geregistreerd/off-label/...).
THESAURUS_INDICATIE_AARD = 1901


@dataclass(frozen=True)
class Field:
    rubriek: str
    type: str
    start: int  # 0-based
    end: int    # half-open


class Gstandaard:
    """Z-Index-getrouwe lezer van de G-standaard-BST-bestanden."""

    def __init__(self, data_dir: Path | str = DEFAULT_DATA_DIR):
        self.dir = Path(data_dir)
        if not self.dir.is_dir():
            raise FileNotFoundError(f"G-standaard-map niet gevonden: {self.dir}")
        self.layouts = self._build_layouts()

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
        layout = self.layouts[bestand]
        with open(self._path(bestand), encoding=ENCODING) as fh:
            for line in fh:
                rec = {f.rubriek: line[f.start:f.end].strip() for f in layout}
                if skip_vervallen and rec.get("MUTKOD") == _MUTKOD_VERVALLEN:
                    continue
                yield rec


class GstandaardDB:
    """Snelle joins over de SQLite-cache van de G-standaard."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        if not Path(db_path).is_file():
            raise FileNotFoundError(
                f"{db_path} ontbreekt; draai eerst: ./venv/bin/python -m scripts.build_gstandaard_db"
            )
        self.con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    def close(self) -> None:
        self.con.close()

    def atc_for_zi(self, zi: str) -> str | None:
        row = self.con.execute(
            "SELECT t.atc FROM bst004 a "
            "JOIN bst070 h ON h.hpk = a.hpk "
            "JOIN bst711 t ON t.gpk = h.gpk "
            "WHERE a.zi = ? AND t.atc <> '' AND t.atc <> 'Z' LIMIT 1",
            (zi,),
        ).fetchone()
        return row[0] if row else None

    def zis_for_atc(self, atc: str) -> list[str]:
        return [
            r[0]
            for r in self.con.execute(
                "SELECT DISTINCT a.zi FROM bst711 t "
                "JOIN bst070 h ON h.gpk = t.gpk "
                "JOIN bst004 a ON a.hpk = h.hpk "
                "WHERE t.atc = ?",
                (atc,),
            )
        ]

    def stofnaam_for_atc(self, atc: str) -> str | None:
        row = self.con.execute(
            "SELECT n.naam FROM bst711 t "
            "JOIN bst020 n ON n.nmnr = t.gpstnr "
            "WHERE t.atc = ? AND n.naam <> '' LIMIT 1",
            (atc,),
        ).fetchone()
        return row[0] if row else None

    def is_addon(self, zi: str) -> bool:
        return self.con.execute("SELECT 1 FROM bst131 WHERE zi = ? LIMIT 1", (zi,)).fetchone() is not None

    def addon_indicaties_for_atc(self, atc: str) -> list[dict]:
        """Distinct add-on-indicaties (INID, INKORT, indicatie-aard) voor een ATC.

        Gefilterd op de add-on-ZI's van de ATC; gededupliceerd op INID.
        """
        rows = self.con.execute(
            "SELECT DISTINCT i.inid, k.inkort, i.insrt FROM bst711 t "
            "JOIN bst070 h ON h.gpk = t.gpk "
            "JOIN bst004 a ON a.hpk = h.hpk "
            "JOIN bst131 ad ON ad.zi = a.zi "
            "JOIN bst132 i ON i.zi = a.zi "
            "JOIN bst133 k ON k.inid = i.inid "
            "WHERE t.atc = ?",
            (atc,),
        ).fetchall()
        aard = self.thesaurus(THESAURUS_INDICATIE_AARD)
        seen: dict[str, dict] = {}
        for inid, inkort, insrt in rows:
            if inid not in seen:
                seen[inid] = {
                    "inid": inid,
                    "inkort": inkort,
                    "insrt": insrt,
                    "indicatie_aard": aard.get(insrt, ""),
                }
        return list(seen.values())

    def thesaurus(self, nummer: int) -> dict[str, str]:
        """Thesaurusitems (BST902) voor een thesaurusnummer: itemnummer -> naam."""
        return {
            code: naam
            for code, naam in self.con.execute(
                "SELECT code, naam FROM thesaurus WHERE tsnr = ?", (str(nummer),)
            )
        }
