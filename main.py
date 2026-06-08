"""Orkestrator: ATC7-universum -> indicaties matchen -> DBC-codes -> output.

Stappen:
1. Universum (in scope) uit Kompas + G-standaard (scripts.drugs).
2. Alle distinctieve indicatieteksten (add-on INKORT + Kompas-bullets) een keer
   classificeren naar een DBC-ziektebeeld of 'geen' (scripts.matching:
   lexicon -> embeddings -> lokale LLM). Handmatige overrides gaan voor.
3. Per ATC7 de ziektebeelden bepalen (add-on primair, Kompas aanvullend) en
   uitbreiden naar DBC-codes (scripts.dbc).
4. Wegschrijven: drug_dbc.csv (databron per ATC7) en dbc_drugs.xlsx voor de apotheker
   (tab Controle met geel-gemarkeerde te-checken koppelingen + tab per ziektebeeld).
   De LLM-verdicts worden gecachet in data/verdicts.json zodat de output (en HITL-
   correcties) zonder opnieuw te classificeren herbouwd kan worden met --reuse-verdicts.

Draaien: ./venv/bin/python main.py --model qwen2.5:3b-instruct
Opties: --no-llm, --no-embeddings, --reuse-verdicts, --limit N
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from openpyxl import Workbook

from scripts import drugs
from scripts.dbc import load_ziektebeelden
from scripts.gstandaard import DEFAULT_DB_PATH, GstandaardDB
from scripts.matching import GEEN, OLLAMA_MODEL, Matcher, Verdict

_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = _ROOT / "output"
OVERRIDES = _ROOT / "data" / "overrides.json"
VERDICTS_CACHE = _ROOT / "data" / "verdicts.json"

# Methodes waarbij de AI besliste (geel = door de apotheker te controleren); de rest
# is deterministisch/bevestigd (wit, vertrouwd).
AI_METHODEN = {"llm", "embedding"}


def _categorie(g) -> str:
    """Vergoedingscategorie van het middel: Add-on (G-standaard BST131) of EVS."""
    return "Add-on" if g.addon else "EVS"


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


def _classificeer(universe, ziektebeelden, gebruik_embeddings, gebruik_llm, model,
                  reuse) -> dict[str, Verdict]:
    teksten: list[str] = []
    for g in universe.values():
        teksten += [i["inkort"] for i in g.addon]
        teksten += g.kompas_indicaties
    teksten = list(dict.fromkeys(teksten))

    if reuse and VERDICTS_CACHE.is_file():
        cache = json.loads(VERDICTS_CACHE.read_text(encoding="utf-8"))
        verdicts = {t: Verdict(**cache[t]) if t in cache else Verdict(t, GEEN, 0.0, "geen-default")
                    for t in teksten}
        ontbreekt = sum(1 for t in teksten if t not in cache)
        print(f"  verdicts uit cache ({VERDICTS_CACHE.name}); {ontbreekt} niet in cache -> geen")
    else:
        matcher = Matcher(ziektebeelden, gebruik_embeddings=gebruik_embeddings,
                          gebruik_llm=gebruik_llm, ollama_model=model)
        print(f"  matcher: embeddings={'aan' if matcher._embedder else 'uit'} "
              f"llm={'aan' if matcher.llm else 'uit'} | {len(teksten)} distinct teksten")
        verdicts = matcher.classify_many(teksten)
        VERDICTS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        VERDICTS_CACHE.write_text(
            json.dumps({t: asdict(v) for t, v in verdicts.items()}, ensure_ascii=False, indent=1),
            encoding="utf-8")

    # Handmatige overrides (HITL) gaan altijd voor, ook bij hergebruik van de cache.
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


def _schrijf_deliverable_xlsx(universe, koppelingen, ziektebeelden, slugs):
    """De Excel voor de apotheker: tab Controle + tab per ziektebeeld + Niet gekoppeld.

    - Tab "Controle": alle koppelingen (middel x ziektebeeld). GEEL = door de AI beslist
      en te controleren; wit = automatisch (lexicon/ATC-groep) of bevestigd. De apotheker
      kijkt alleen naar de gele rijen en kan corrigeren via de dropdown in `correctie`.
    - Tab per ziektebeeld: bovenaan de DBC-codes, daaronder de medicatielijst met de
      vergoedingscategorie (Add-on/EVS); gele rijen zijn AI-beslist.
    - Tab "Niet gekoppeld": middelen zonder ziektebeeld (controle dat niets gemist is).
    """
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    GEEL = PatternFill("solid", fgColor="FFF2A8")
    TEAL = PatternFill("solid", fgColor="0E7C86")
    KOP = Font(bold=True, color="FFFFFF")
    VET = Font(bold=True)

    def _kleur_kop(ws, rij=1):
        for c in ws[rij]:
            c.font, c.fill = KOP, TEAL

    def _geel(ws):
        for c in ws[ws.max_row]:
            c.fill = GEEL

    wb = Workbook()

    # --- Tab 1: Medicatie (overzicht + controle) ---
    ws = wb.active
    ws.title = "Medicatie"
    kop = ["ziektebeeld", "atc7", "stofnaam", "categorie", "zekerheid", "methode",
           "onderbouwing", "correctie"]
    ws.append(kop)
    rijen = []
    for atc7, kopp in koppelingen.items():
        g = universe[atc7]
        for zb, info in kopp.items():
            rijen.append((info["methode"] in AI_METHODEN, zb, atc7, g.stofnaam,
                          _categorie(g), info))
    rijen.sort(key=lambda r: (not r[0], r[1], r[3]))  # te-checken (geel) eerst
    for is_ai, zb, atc7, stof, cat, info in rijen:
        ws.append([zb, atc7, stof, cat, round(info["confidence"], 2), info["methode"],
                   info["tekst"], ""])
        if is_ai:
            _geel(ws)
    _kleur_kop(ws)
    keuzes = ",".join(list(slugs) + ["geen"])
    dv = DataValidation(type="list", formula1=f'"{keuzes}"', allow_blank=True,
                        showInputMessage=True, promptTitle="Correctie",
                        prompt="Kies een ziektebeeld of 'geen'. Leeg laten = voorstel akkoord.")
    ws.add_data_validation(dv)
    dv.add(f"H2:H{ws.max_row}")
    for col, br in {"A": 20, "B": 10, "C": 26, "D": 10, "E": 10, "F": 12, "G": 60, "H": 20}.items():
        ws.column_dimensions[col].width = br
    ws.freeze_panes = "A2"

    # --- Tab per ziektebeeld ---
    for slug, z in ziektebeelden.items():
        ws = wb.create_sheet(title=slug[:31])
        ws.append(["DBC-codes"])
        ws[ws.max_row][0].font = VET
        ws.append(["specialisme_code", "diagnose_code", "omschrijving"])
        _kleur_kop(ws, ws.max_row)
        for c in z.dbc_codes:
            ws.append([c.specialisme_code, c.diagnose_code, c.omschrijving])
        ws.append([])
        ws.append(["Geneesmiddelen"])
        ws[ws.max_row][0].font = VET
        ws.append(["atc7", "stofnaam", "categorie", "zekerheid", "methode"])
        _kleur_kop(ws, ws.max_row)
        meds = sorted((a for a, k in koppelingen.items() if slug in k),
                      key=lambda a: (koppelingen[a][slug]["methode"] not in AI_METHODEN, a))
        for atc7 in meds:
            info = koppelingen[atc7][slug]
            ws.append([atc7, universe[atc7].stofnaam, _categorie(universe[atc7]),
                       round(info["confidence"], 2), info["methode"]])
            if info["methode"] in AI_METHODEN:
                _geel(ws)
        for col, br in {"A": 10, "B": 26, "C": 10, "D": 10, "E": 12}.items():
            ws.column_dimensions[col].width = br

    pad = OUTPUT_DIR / "dbc_drugs.xlsx"
    wb.save(pad)
    return pad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-embeddings", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--model", default=OLLAMA_MODEL, help="Ollama-model voor de LLM-laag")
    ap.add_argument("--reuse-verdicts", action="store_true",
                    help="laad de classificatie uit data/verdicts.json (geen LLM); alleen output herbouwen")
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
                             model=args.model, reuse=args.reuse_verdicts)

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
    p2 = _schrijf_deliverable_xlsx(universe, koppelingen, ziektebeelden, list(ziektebeelden))

    import collections
    methodes = collections.Counter(v.methode for v in verdicts.values())
    per_zb = collections.Counter(slug for k in koppelingen.values() for slug in k)
    gekoppeld = sum(1 for k in koppelingen.values() if k)
    print(f"Klaar. {gekoppeld}/{len(universe)} ATC7 gekoppeld aan >=1 ziektebeeld.")
    print(f"  verdicts per methode: {dict(methodes)}")
    print(f"  geneesmiddelen per ziektebeeld: {dict(per_zb.most_common())}")
    for p in (p1, p2):
        print(f"  -> {p}")


if __name__ == "__main__":
    main()
