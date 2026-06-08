"""ATC-universum (in scope), per ATC7 (de werkzame stof).

ATC7 is de sleutel: de DBC-toepassing gebruikt uiteindelijk de stof, niet de
formulering. Alle Kompas-pagina's van een ATC7 worden samengevoegd (union) en de
add-on-indicaties horen bij de ATC7. Een gevolg: verschillende formuleringen onder
dezelfde ATC7 (bv. gewone en liposomale doxorubicine) delen indicaties - een bewuste
limitatie, niet erg omdat de koppeling op stofniveau bedoeld is. De off-label add-on-
indicaties worden in de output geflagd zodat ze herkenbaar blijven.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from scripts import kompas
from scripts.gstandaard import GstandaardDB


@dataclass
class Geneesmiddel:
    atc7: str
    stofnaam: str
    titels: list[str] = field(default_factory=list)        # Kompas-paginatitels onder deze ATC7
    addon: list[dict] = field(default_factory=list)        # {inid, inkort, insrt, indicatie_aard}
    kompas_indicaties: list[str] = field(default_factory=list)


def build_universe(db: GstandaardDB | None = None, preparaten=None) -> dict[str, Geneesmiddel]:
    """Bouw {ATC7: Geneesmiddel} voor de in-scope middelen (Kompas geunioneerd)."""
    db = db or GstandaardDB()
    if preparaten is None:
        preparaten = kompas.load_preparaten(alleen_scope=True)

    universe: dict[str, Geneesmiddel] = {}
    for p in preparaten:
        if not p.atc:
            continue
        g = universe.get(p.atc)
        if g is None:
            stof = db.stofnaam_for_atc(p.atc) or p.titel or p.atc
            g = Geneesmiddel(atc7=p.atc, stofnaam=stof)
            universe[p.atc] = g
        g.kompas_indicaties.extend(p.indicaties)
        if p.titel:
            g.titels.append(p.titel)

    for atc7, g in universe.items():
        g.addon = db.addon_indicaties_for_atc(atc7)
        g.kompas_indicaties = list(dict.fromkeys(g.kompas_indicaties))
        g.titels = list(dict.fromkeys(g.titels))
    return universe
