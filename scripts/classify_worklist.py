"""Classificeer de werklijst met de lokale Ollama-LLM (bedoeld voor de HPC).

Leest data/worklist.json (van scripts.export_worklist) en schrijft data/verdicts.json,
incrementeel gecheckpoint en resumebaar: valt de job uit, dan pakt een herstart de rest op.
Heeft alleen Ollama + requests nodig (geen embeddings/data), dus licht op de HPC.

    python -m scripts.classify_worklist --model qwen2.5:14b-instruct
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.matching import (
    CHECKPOINT_ELKE,
    GEEN,
    OLLAMA_MODEL,
    Verdict,
    _laad_checkpoint,
    _schrijf_checkpoint,
    _vraag_llm,
)

_DATA = Path(__file__).resolve().parent.parent / "data"
WORKLIST = _DATA / "worklist.json"
VERDICTS = _DATA / "verdicts.json"


def classify(model: str = OLLAMA_MODEL) -> None:
    if not WORKLIST.is_file():
        raise SystemExit(f"{WORKLIST} ontbreekt; draai eerst export_worklist")
    wl = json.loads(WORKLIST.read_text(encoding="utf-8"))
    profielen, items = wl["profielen"], wl["teksten"]

    verdicts = _laad_checkpoint(VERDICTS)
    todo = []
    for it in items:
        t = it["tekst"]
        if t in verdicts:
            continue
        if it["geen"]:
            verdicts[t] = Verdict(t, GEEN, 1.0, "lexicon")
        elif it["lexicon"] and not it["llm"]:
            verdicts[t] = Verdict(t, it["lexicon"], 1.0, "lexicon", lexicon=it["lexicon"])
        else:
            todo.append(it)
    _schrijf_checkpoint(VERDICTS, verdicts)
    print(f"{len(items)} teksten, {len(todo)} via de LLM ({model})", flush=True)

    for i, it in enumerate(todo, 1):
        t, hint = it["tekst"], it["lexicon"]
        try:
            ant = _vraag_llm(t, [(s, profielen[s]) for s in it["kandidaten"]], hint, model)
            zb = ant.get("ziektebeeld", GEEN)
            zb = zb if zb in profielen else GEEN
            verdicts[t] = Verdict(t, zb, float(ant.get("confidence", 0.0)), "llm",
                                  str(ant.get("rationale", "")), lexicon=hint, flag=bool(hint and hint != zb))
        except Exception:
            verdicts[t] = Verdict(t, hint or GEEN, 1.0, "lexicon" if hint else "geen-default", lexicon=hint)
        if i % CHECKPOINT_ELKE == 0 or i == len(todo):
            _schrijf_checkpoint(VERDICTS, verdicts)
        if i % 50 == 0 or i == len(todo):
            print(f"  LLM {i}/{len(todo)}", flush=True)
    print(f"klaar: {len(verdicts)} verdicts -> {VERDICTS}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=OLLAMA_MODEL, help="Ollama-model (bv. qwen2.5:14b-instruct)")
    args = ap.parse_args()
    classify(args.model)
