"""Bouw de werklijst voor de LLM-classificatie (lokaal).

Splitst de zware GPU-stap (de LLM) af van de data-zware stap. Lokaal draaien we
embeddings (BGE-M3) en het lexicon en schrijven we per indicatietekst de lexicon-
suggestie, een 'geen'-vlag (hemato-vangnet) en de embedding-kandidaten naar
data/worklist.json. Dat kleine bestand gaat mee naar de HPC, waar alleen de LLM hoeft
te draaien (scripts.classify_worklist). Daarna haal je data/verdicts.json terug en
bouwt main.py --reuse-verdicts de output.

    ./venv/bin/python -m scripts.export_worklist [--verify-lexicon]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import drugs, mapping
from scripts.dbc import load_ziektebeelden
from scripts.matching import Matcher

WORKLIST = Path(__file__).resolve().parent.parent / "data" / "worklist.json"


def export(verifieer_lexicon: bool = False) -> None:
    universe = drugs.build_universe()
    # Alleen de oncologie-ATC's gaan door de engine; A10/A08 zijn direct (geen tekst-matching).
    via_engine = {a: g for a, g in universe.items() if not (a.startswith("A08") or a.startswith("A10"))}
    teksten = []
    for g in via_engine.values():
        teksten += [i["inkort"] for i in g.addon]
        teksten += g.kompas_indicaties
    teksten = list(dict.fromkeys(teksten))

    matcher = Matcher(load_ziektebeelden(), gebruik_embeddings=True, gebruik_llm=False)
    kand = matcher._kandidaten_batch(teksten)

    items = []
    for t in teksten:
        hint = mapping.map_text(t) or ""
        geen = (not hint) and mapping.forceer_geen(t)
        naar_llm = (not hint or verifieer_lexicon) and not geen
        items.append({"tekst": t, "lexicon": hint, "geen": geen, "llm": naar_llm,
                      "kandidaten": [s for s, _ in kand[t]]})

    WORKLIST.parent.mkdir(parents=True, exist_ok=True)
    WORKLIST.write_text(
        json.dumps({"profielen": matcher.kort, "teksten": items}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"{len(items)} teksten -> {WORKLIST}  ({sum(i['llm'] for i in items)} naar de LLM)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-lexicon", action="store_true",
                    help="stuur ook lexicon-treffers naar de LLM (alleen met een sterk model)")
    args = ap.parse_args()
    export(verifieer_lexicon=args.verify_lexicon)
