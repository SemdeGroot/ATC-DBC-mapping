"""Orkestrator: ATC7-universum -> indicaties matchen -> DBC-codes -> output.

Stappen:
1. Universum (in scope) uit Kompas + G-standaard (scripts.drugs).
2. Alle distinctieve indicatieteksten (add-on INKORT + Kompas-bullets) een keer
   classificeren naar een DBC-ziektebeeld of 'geen' (scripts.matching:
   lexicon -> embeddings -> lokale LLM). Handmatige overrides gaan voor.
3. Per ATC7 de ziektebeelden bepalen (add-on primair, Kompas aanvullend) en
   uitbreiden naar DBC-codes (scripts.dbc).
4. Wegschrijven: drug_dbc.csv (per ATC7), dbc_drugs.xlsx (tab per ziektebeeld),
   review_queue.csv (HITL, op confidence gesorteerd).

Draaien: ./venv/bin/python main.py   (opties: --no-llm, --no-embeddings, --limit N)
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from openpyxl import Workbook

from scripts import drugs
from scripts.dbc import load_ziektebeelden
from scripts.gstandaard import DEFAULT_DB_PATH, GstandaardDB
from scripts.matching import GEEN, Matcher, Verdict

_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = _ROOT / "output"
OVERRIDES = _ROOT / "data" / "overrides.json"


def _laad_overrides() -> dict[str, str]:
    """Handmatige beslissingen tekst(lowercase) -> ziektebeeld-slug (HITL)."""
    if OVERRIDES.is_file():
        return {k.lower(): v for k, v in json.loads(OVERRIDES.read_text(encoding="utf-8")).items()}
    return {}


def _classificeer(universe, ziektebeelden, gebruik_embeddings, gebruik_llm) -> dict[str, Verdict]:
    teksten: list[str] = []
    for g in universe.values():
        teksten += [i["inkort"] for i in g.addon]
        teksten += g.kompas_indicaties
    teksten = list(dict.fromkeys(teksten))

    matcher = Matcher(ziektebeelden, gebruik_embeddings=gebruik_embeddings, gebruik_llm=gebruik_llm)
    print(f"  matcher: embeddings={'aan' if matcher._embedder else 'uit'} "
          f"llm={'aan' if matcher.llm else 'uit'} | {len(teksten)} distinct teksten")
    verdicts = matcher.classify_many(teksten)

    for tekst, slug in _laad_overrides().items():
        if tekst in verdicts:
            verdicts[tekst] = Verdict(tekst, slug, 1.0, "handmatig")
    return verdicts


def _ziektebeelden_per_atc(g, verdicts) -> dict[str, dict]:
    """Per ATC7: ziektebeeld -> koppelinfo (add-on primair, Kompas aanvullend)."""
    gekoppeld: dict[str, dict] = {}
    for ind in g.addon:  # add-on eerst (autoritair)
        v = verdicts[ind["inkort"]]
        if v.ziektebeeld != GEEN and v.ziektebeeld not in gekoppeld:
            gekoppeld[v.ziektebeeld] = {
                "bron": "add-on", "indicatie_aard": ind["indicatie_aard"],
                "confidence": v.score, "methode": v.methode, "tekst": ind["inkort"],
            }
    for bullet in g.kompas_indicaties:  # Kompas vult aan
        v = verdicts[bullet]
        if v.ziektebeeld != GEEN and v.ziektebeeld not in gekoppeld:
            gekoppeld[v.ziektebeeld] = {
                "bron": "kompas", "indicatie_aard": "",
                "confidence": v.score, "methode": v.methode, "tekst": bullet,
            }
    return gekoppeld


def _schrijf_drug_dbc(universe, koppelingen, ziektebeelden):
    pad = OUTPUT_DIR / "drug_dbc.csv"
    with open(pad, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["atc7", "stofnaam", "bron", "indicatie_aard", "ziektebeeld",
                    "specialisme_code", "diagnose_code", "omschrijving", "confidence", "methode"])
        for atc7, g in sorted(universe.items()):
            for slug, info in sorted(koppelingen[atc7].items()):
                for code in ziektebeelden[slug].dbc_codes:
                    w.writerow([atc7, g.stofnaam, info["bron"], info["indicatie_aard"], slug,
                                code.specialisme_code, code.diagnose_code, code.omschrijving,
                                f"{info['confidence']:.2f}", info["methode"]])
    return pad


def _schrijf_dbc_drugs_xlsx(universe, koppelingen, ziektebeelden):
    pad = OUTPUT_DIR / "dbc_drugs.xlsx"
    wb = Workbook()
    samenvatting = wb.active
    samenvatting.title = "samenvatting"
    samenvatting.append(["ziektebeeld", "aantal_dbc_codes", "aantal_geneesmiddelen"])

    for slug, z in ziektebeelden.items():
        meds = sorted(atc7 for atc7, kopp in koppelingen.items() if slug in kopp)
        samenvatting.append([slug, len(z.dbc_codes), len(meds)])

        ws = wb.create_sheet(title=slug[:31])
        ws.append(["DBC-codes"])
        ws.append(["specialisme_code", "diagnose_code", "omschrijving"])
        for c in z.dbc_codes:
            ws.append([c.specialisme_code, c.diagnose_code, c.omschrijving])
        ws.append([])
        ws.append(["Geneesmiddelen"])
        ws.append(["atc7", "stofnaam", "bron", "indicatie_aard", "confidence", "methode"])
        for atc7 in meds:
            info = koppelingen[atc7][slug]
            ws.append([atc7, universe[atc7].stofnaam, info["bron"], info["indicatie_aard"],
                       round(info["confidence"], 2), info["methode"]])
    wb.save(pad)
    return pad


def _schrijf_review_queue(universe, verdicts):
    """Niet-lexicon-verdicts voor de HITL, op confidence oplopend (onzeker eerst)."""
    voorbeeld: dict[str, tuple[str, str, str]] = {}  # tekst -> (bron, atc7, stofnaam)
    for atc7, g in universe.items():
        for ind in g.addon:
            voorbeeld.setdefault(ind["inkort"], ("add-on", atc7, g.stofnaam))
        for b in g.kompas_indicaties:
            voorbeeld.setdefault(b, ("kompas", atc7, g.stofnaam))

    rijen = sorted((v for v in verdicts.values() if v.methode != "lexicon"), key=lambda v: v.score)
    pad = OUTPUT_DIR / "review_queue.csv"
    with open(pad, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["confidence", "methode", "voorgesteld_ziektebeeld", "indicatietekst",
                    "bron", "voorbeeld_atc7", "voorbeeld_stofnaam", "rationale"])
        for v in rijen:
            bron, atc7, stof = voorbeeld.get(v.tekst, ("", "", ""))
            w.writerow([f"{v.score:.2f}", v.methode, v.ziektebeeld, v.tekst, bron, atc7, stof, v.rationale])
    return pad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-embeddings", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="beperk universum (test)")
    args = ap.parse_args()

    if not DEFAULT_DB_PATH.is_file():
        raise SystemExit("Bouw eerst de SQLite-cache: ./venv/bin/python -m scripts.build_gstandaard_db")

    print("Universum opbouwen...")
    db = GstandaardDB()
    universe = drugs.build_universe(db=db)
    if args.limit:
        universe = dict(list(universe.items())[: args.limit])
    print(f"  {len(universe)} ATC7 in scope")

    ziektebeelden = load_ziektebeelden()
    print("Indicaties classificeren...")
    verdicts = _classificeer(universe, ziektebeelden,
                             gebruik_embeddings=not args.no_embeddings, gebruik_llm=not args.no_llm)

    koppelingen = {atc7: _ziektebeelden_per_atc(g, verdicts) for atc7, g in universe.items()}

    OUTPUT_DIR.mkdir(exist_ok=True)
    p1 = _schrijf_drug_dbc(universe, koppelingen, ziektebeelden)
    p2 = _schrijf_dbc_drugs_xlsx(universe, koppelingen, ziektebeelden)
    p3 = _schrijf_review_queue(universe, verdicts)
    gekoppeld = sum(1 for k in koppelingen.values() if k)
    print(f"Klaar. {gekoppeld}/{len(universe)} ATC7 gekoppeld aan >=1 ziektebeeld.")
    for p in (p1, p2, p3):
        print(f"  -> {p}")


if __name__ == "__main__":
    main()
