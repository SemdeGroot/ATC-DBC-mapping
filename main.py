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
from scripts.matching import GEEN, OLLAMA_MODEL, Matcher, Verdict

_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = _ROOT / "output"
OVERRIDES = _ROOT / "data" / "overrides.json"


def _atc_groep_ziektebeelden(atc7: str) -> list[str]:
    """Directe ATC-groep-regel voor diabetes/obesitas (geen tekst-matching nodig).

    De ATC-groep is hier zelf de diagnose, exact volgens de ATC-indeling: A10 =
    geneesmiddelen bij diabetes (inclusief de GLP-1's in A10BJ), A08 = antiobesitas.
    Oncologie (L) valt hier bewust buiten: die ATC-groep zegt niets over de tumor,
    dus die loopt door de matching-engine.
    """
    if atc7.startswith("A08"):
        return ["obesitas"]
    if atc7.startswith("A10"):
        return ["diabetes"]
    return []


def _laad_overrides() -> dict[str, str]:
    """Handmatige beslissingen tekst(lowercase) -> ziektebeeld-slug (HITL)."""
    if OVERRIDES.is_file():
        return {k.lower(): v for k, v in json.loads(OVERRIDES.read_text(encoding="utf-8")).items()}
    return {}


def _classificeer(universe, ziektebeelden, gebruik_embeddings, gebruik_llm, model) -> dict[str, Verdict]:
    teksten: list[str] = []
    for g in universe.values():
        teksten += [i["inkort"] for i in g.addon]
        teksten += g.kompas_indicaties
    teksten = list(dict.fromkeys(teksten))

    matcher = Matcher(ziektebeelden, gebruik_embeddings=gebruik_embeddings,
                      gebruik_llm=gebruik_llm, ollama_model=model)
    print(f"  matcher: embeddings={'aan' if matcher._embedder else 'uit'} "
          f"llm={'aan' if matcher.llm else 'uit'} | {len(teksten)} distinct teksten")
    verdicts = matcher.classify_many(teksten)

    for tekst, slug in _laad_overrides().items():
        if tekst in verdicts:
            verdicts[tekst] = Verdict(tekst, slug, 1.0, "handmatig")
    return verdicts


def _ziektebeelden_per_atc(g, verdicts) -> dict[str, dict]:
    """Per ATC7: ziektebeeld -> koppelinfo (add-on primair, Kompas aanvullend).

    Bij meerdere indicaties op hetzelfde ziektebeeld wordt de indicatie met de
    hoogste confidence als herkomst bewaard (de koppeling zelf verandert daar niet van).
    """
    gekoppeld: dict[str, dict] = {}
    addon_zbs: set[str] = set()
    for ind in g.addon:  # add-on eerst (autoritair)
        v = verdicts[ind["inkort"]]
        if v.ziektebeeld == GEEN:
            continue
        addon_zbs.add(v.ziektebeeld)
        best = gekoppeld.get(v.ziektebeeld)
        if best is None or v.score > best["confidence"]:
            gekoppeld[v.ziektebeeld] = {
                "bron": "add-on", "indicatie_aard": ind["indicatie_aard"],
                "confidence": v.score, "methode": v.methode, "tekst": ind["inkort"],
            }
    for bullet in g.kompas_indicaties:  # Kompas vult ziektebeelden aan die add-on niet leverde
        v = verdicts[bullet]
        if v.ziektebeeld == GEEN or v.ziektebeeld in addon_zbs:
            continue
        best = gekoppeld.get(v.ziektebeeld)
        if best is None or v.score > best["confidence"]:
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


def _schrijf_review_xlsx(universe, verdicts, slugs):
    """HITL-werklijst: een rij per indicatietekst met een dropdown-correctiekolom.

    Leeg laten = het voorstel accepteren. Een correctie invullen (uit de dropdown)
    en daarna `python -m scripts.apply_review` draaien zet 'm in data/overrides.json.
    Gesorteerd op confidence oplopend (onzeker bovenaan); lexicon-treffers onderaan.
    """
    from openpyxl.worksheet.datavalidation import DataValidation

    voorbeeld: dict[str, tuple[str, str, str]] = {}  # tekst -> (bron, atc7, stofnaam)
    for atc7, g in universe.items():
        for ind in g.addon:
            voorbeeld.setdefault(ind["inkort"], ("add-on", atc7, g.stofnaam))
        for b in g.kompas_indicaties:
            voorbeeld.setdefault(b, ("kompas", atc7, g.stofnaam))

    rijen = sorted(verdicts.values(), key=lambda v: (v.methode == "lexicon", v.score))
    wb = Workbook()
    ws = wb.active
    ws.title = "review"
    kop = ["indicatietekst", "voorstel", "correctie", "confidence", "methode",
           "rationale", "bron", "voorbeeld_atc7", "voorbeeld_stofnaam"]
    ws.append(kop)
    for v in rijen:
        bron, atc7, stof = voorbeeld.get(v.tekst, ("", "", ""))
        ws.append([v.tekst, v.ziektebeeld, "", round(v.score, 2), v.methode,
                   v.rationale, bron, atc7, stof])

    from openpyxl.styles import Font, PatternFill

    # Dropdown met de 14 ziektebeelden + "geen" op de correctie-kolom, met hint-popup.
    keuzes = ",".join(list(slugs) + ["geen"])
    dv = DataValidation(type="list", formula1=f'"{keuzes}"', allow_blank=True,
                        showDropDown=False, showInputMessage=True,
                        promptTitle="Correctie",
                        prompt="Kies een ziektebeeld of 'geen'. Leeg laten = voorstel akkoord.")
    ws.add_data_validation(dv)
    dv.add(f"C2:C{ws.max_row}")

    # Opmaak zodat de apotheker direct ziet waar te corrigeren.
    kopfill = PatternFill("solid", fgColor="0E7C86")
    for ci in range(1, len(kop) + 1):
        c = ws.cell(1, ci)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = kopfill
    corrfill = PatternFill("solid", fgColor="FBE7DA")
    for r in range(2, ws.max_row + 1):
        ws.cell(r, 3).fill = corrfill
    for col, breedte in {"A": 70, "B": 20, "C": 20, "D": 11, "E": 12,
                         "F": 50, "G": 9, "H": 13, "I": 22}.items():
        ws.column_dimensions[col].width = breedte
    ws.freeze_panes = "A2"

    pad = OUTPUT_DIR / "review.xlsx"
    wb.save(pad)
    return pad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-embeddings", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--model", default=OLLAMA_MODEL, help="Ollama-model voor de LLM-laag")
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

    # Diabetes/obesitas (A10/A08) direct per ATC-groep; alleen oncologie (L) via de engine.
    direct = {a: g for a, g in universe.items() if _atc_groep_ziektebeelden(a)}
    via_engine = {a: g for a, g in universe.items() if not _atc_groep_ziektebeelden(a)}
    print(f"  {len(direct)} ATC7 direct via ATC-groep (diabetes/obesitas), "
          f"{len(via_engine)} via de matching-engine (oncologie)")

    print("Indicaties classificeren...")
    verdicts = _classificeer(via_engine, ziektebeelden,
                             gebruik_embeddings=not args.no_embeddings, gebruik_llm=not args.no_llm,
                             model=args.model)

    koppelingen: dict[str, dict] = {}
    for atc7, g in universe.items():
        groep = _atc_groep_ziektebeelden(atc7)
        if groep:
            koppelingen[atc7] = {
                zb: {"bron": "atc-groep", "indicatie_aard": "", "confidence": 1.0,
                     "methode": "atc-groep", "tekst": ""}
                for zb in groep
            }
        else:
            koppelingen[atc7] = _ziektebeelden_per_atc(g, verdicts)

    OUTPUT_DIR.mkdir(exist_ok=True)
    p1 = _schrijf_drug_dbc(universe, koppelingen, ziektebeelden)
    p2 = _schrijf_dbc_drugs_xlsx(universe, koppelingen, ziektebeelden)
    p3 = _schrijf_review_xlsx(universe, verdicts, list(ziektebeelden))

    import collections
    methodes = collections.Counter(v.methode for v in verdicts.values())
    per_zb = collections.Counter(slug for k in koppelingen.values() for slug in k)
    gekoppeld = sum(1 for k in koppelingen.values() if k)
    print(f"Klaar. {gekoppeld}/{len(universe)} ATC7 gekoppeld aan >=1 ziektebeeld.")
    print(f"  verdicts per methode: {dict(methodes)}")
    print(f"  geneesmiddelen per ziektebeeld: {dict(per_zb.most_common())}")
    for p in (p1, p2, p3):
        print(f"  -> {p}")


if __name__ == "__main__":
    main()
