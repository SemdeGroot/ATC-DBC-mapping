"""ATC-universum (in scope) met de indicatiebronnen per ATC7.

Universum = de in-scope ATC7-codes (L/A10/A08) die in het Kompas voorkomen. Per ATC7:
- stofnaam (Kompas-titel, anders G-standaard);
- add-on-indicaties (G-standaard, autoritair): inid/inkort/insrt/indicatie_aard;
- kompas-indicaties (bullets uit de preparaattekst).

ATC7 is de gedeelde sleutel tussen beide bronnen; een stofnaam->Kompas-slug-koppeling
is dus niet nodig.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from scripts import kompas
from scripts.gstandaard import GstandaardDB


@dataclass
class Geneesmiddel:
    atc7: str
    stofnaam: str
    addon: list[dict] = field(default_factory=list)        # {inid, inkort, insrt, indicatie_aard}
    kompas_indicaties: list[str] = field(default_factory=list)


def build_universe(db: GstandaardDB | None = None, preparaten=None) -> dict[str, Geneesmiddel]:
    """Bouw {ATC7: Geneesmiddel} voor de in-scope Kompas-middelen, verrijkt met add-on."""
    db = db or GstandaardDB()
    if preparaten is None:
        preparaten = kompas.load_preparaten(alleen_scope=True)

    universe: dict[str, Geneesmiddel] = {}
    for p in preparaten:
        if not p.atc:
            continue
        g = universe.get(p.atc)
        if g is None:
            stof = p.titel or db.stofnaam_for_atc(p.atc) or p.atc
            g = Geneesmiddel(atc7=p.atc, stofnaam=stof)
            universe[p.atc] = g
        g.kompas_indicaties.extend(p.indicaties)

    for atc7, g in universe.items():
        g.addon = db.addon_indicaties_for_atc(atc7)
        g.kompas_indicaties = list(dict.fromkeys(g.kompas_indicaties))
    return universe
