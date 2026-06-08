"""Classificeer de werklijst met een LLM (bedoeld voor de HPC).

Leest data/worklist.json (van scripts.export_worklist) en schrijft data/verdicts.json,
incrementeel gecheckpoint en resumebaar.

Twee backends:
- `--backend vllm` (HPC, standaard): vLLM + een HuggingFace-model (bv. Qwen2.5-14B-Instruct-AWQ),
  gebatchte offline-inferentie. HuggingFace is op ALICE bereikbaar.
- `--backend ollama`: praat met een lokale Ollama-server (per tekst).

    python -m scripts.classify_worklist --backend vllm --model Qwen/Qwen2.5-14B-Instruct-AWQ
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.matching import (
    GEEN,
    OLLAMA_MODEL,
    Verdict,
    _laad_checkpoint,
    _schrijf_checkpoint,
    _vraag_llm,
    bouw_prompt,
    parse_antwoord,
    verdict_uit_antwoord,
)

_DATA = Path(__file__).resolve().parent.parent / "data"
WORKLIST = _DATA / "worklist.json"
VERDICTS = _DATA / "verdicts.json"
VLLM_MODEL = "Qwen/Qwen2.5-14B-Instruct-AWQ"


def _splits(items, verdicts, profielen):
    """Resolve lexicon/geen direct; geef de teksten terug die echt naar de LLM moeten."""
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
    return todo


def _classify_ollama(todo, profielen, verdicts, model):
    from scripts.matching import CHECKPOINT_ELKE
    for i, it in enumerate(todo, 1):
        t, hint = it["tekst"], it["lexicon"]
        try:
            ant = _vraag_llm(t, [(s, profielen[s]) for s in it["kandidaten"]], hint, model)
            verdicts[t] = verdict_uit_antwoord(t, ant, profielen, hint)
        except Exception:
            verdicts[t] = Verdict(t, hint or GEEN, 1.0, "lexicon" if hint else "geen-default", lexicon=hint)
        if i % CHECKPOINT_ELKE == 0 or i == len(todo):
            _schrijf_checkpoint(VERDICTS, verdicts)
        if i % 50 == 0 or i == len(todo):
            print(f"  LLM {i}/{len(todo)}", flush=True)


def _classify_vllm(todo, profielen, verdicts, model, chunk=256):
    from vllm import LLM, SamplingParams  # luie import (alleen op de HPC nodig)

    llm = LLM(model=model, quantization="awq", dtype="half", max_model_len=2048,
              gpu_memory_utilization=0.92, enforce_eager=True)
    sp = SamplingParams(temperature=0.0, max_tokens=200)
    for start in range(0, len(todo), chunk):
        batch = todo[start:start + chunk]
        gesprekken = [
            [{"role": "user",
              "content": bouw_prompt(it["tekst"], [(s, profielen[s]) for s in it["kandidaten"]], it["lexicon"])}]
            for it in batch
        ]
        uit = llm.chat(gesprekken, sp, use_tqdm=False)
        for it, out in zip(batch, uit):
            ant = parse_antwoord(out.outputs[0].text)
            verdicts[it["tekst"]] = verdict_uit_antwoord(it["tekst"], ant, profielen, it["lexicon"])
        _schrijf_checkpoint(VERDICTS, verdicts)
        print(f"  vLLM {min(start + chunk, len(todo))}/{len(todo)}", flush=True)


def classify(model: str, backend: str = "vllm") -> None:
    if not WORKLIST.is_file():
        raise SystemExit(f"{WORKLIST} ontbreekt; draai eerst export_worklist")
    wl = json.loads(WORKLIST.read_text(encoding="utf-8"))
    profielen, items = wl["profielen"], wl["teksten"]

    verdicts = _laad_checkpoint(VERDICTS)
    todo = _splits(items, verdicts, profielen)
    _schrijf_checkpoint(VERDICTS, verdicts)
    print(f"{len(items)} teksten, {len(todo)} via de LLM ({backend}: {model})", flush=True)

    if todo:
        (_classify_vllm if backend == "vllm" else _classify_ollama)(todo, profielen, verdicts, model)
    print(f"klaar: {len(verdicts)} verdicts -> {VERDICTS}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["vllm", "ollama"], default="vllm")
    ap.add_argument("--model", default=None, help="HF-model (vllm) of Ollama-model")
    args = ap.parse_args()
    model = args.model or (VLLM_MODEL if args.backend == "vllm" else OLLAMA_MODEL)
    classify(model, args.backend)
