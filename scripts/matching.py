"""Hybride matching: indicatietekst -> DBC-ziektebeeld of 'geen'.

Werkwijze met LLM aan:
- embeddings (BGE-M3) leveren de top-k kandidaat-ziektebeelden;
- het lexicon (scripts.mapping) levert een suggestie als hint;
- de lokale LLM (Ollama) neemt de EINDbeslissing en mag de lexicon-hint corrigeren.
  Waar de LLM van de lexicon-hint afwijkt, wordt `flag=True` gezet (te controleren).

Zonder LLM degradeert het netjes: lexicon-treffer wint, anders een cosine-drempel.

Checkpointing: `classify_many(checkpoint_path=...)` laadt bestaande verdicts, doet alleen
de ontbrekende teksten en schrijft incrementeel weg - zo is een lange run resumebaar.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from scripts import mapping

GEEN = "geen"
EMBED_MODEL = "BAAI/bge-m3"
# Lokaal draait 3B comfortabel op 6 GB VRAM; op de HPC (11 GB) kan qwen2.5:14b-instruct.
OLLAMA_MODEL = "qwen2.5:3b-instruct"
OLLAMA_URL = "http://localhost:11434/api/generate"
NUM_CTX = 2048
TOP_K = 4
EMBED_DREMPEL = 0.55       # fallback-drempel als de LLM niet beschikbaar is
CHECKPOINT_ELKE = 25       # verdicts.json om de N classificaties wegschrijven


@dataclass
class Verdict:
    tekst: str
    ziektebeeld: str           # slug of 'geen'
    score: float               # cosine (embedding) of LLM-confidence
    methode: str               # lexicon | embedding | llm | geen-default
    rationale: str = ""
    lexicon: str = ""          # lexicon-suggestie (ter info/controle)
    flag: bool = False         # LLM week af van de lexicon-suggestie -> controleren


class _Embedder:
    """Luie BGE-M3-wrapper; embeddings genormaliseerd zodat dot == cosine."""

    def __init__(self, model_name: str = EMBED_MODEL):
        from sentence_transformers import SentenceTransformer  # luie import

        self.model = SentenceTransformer(model_name)

    def encode(self, teksten: list[str]):
        return self.model.encode(teksten, normalize_embeddings=True, show_progress_bar=False)


def _ollama_beschikbaar() -> bool:
    try:
        requests.get("http://localhost:11434/api/tags", timeout=2).raise_for_status()
        return True
    except Exception:
        return False


def _vraag_llm(tekst: str, kandidaten: list[tuple[str, str]], hint: str, model: str) -> dict:
    """Laat de LLM kiezen uit de kandidaat-ziektebeelden of 'geen'. Retour: dict-JSON."""
    opties = "\n".join(f"- {slug}: {profiel}" for slug, profiel in kandidaten)
    hint_regel = (
        f"Een trefwoordsysteem suggereert: {hint}. Controleer dit; het kan fout zijn "
        f"(bv. door een uitgesloten woord of een verkeerde tumor).\n\n" if hint else ""
    )
    prompt = (
        "Je classificeert een Nederlandse geneesmiddel-indicatie naar precies een "
        "DBC-ziektebeeld, of naar 'geen' als de indicatie niet bij een van de opties hoort "
        "(bv. hematologische kanker, auto-immuunziekte, of een tumor die niet in de lijst staat).\n\n"
        f"Indicatie: \"{tekst}\"\n\n"
        f"{hint_regel}"
        f"Opties (ziektebeeld: omschrijving):\n{opties}\n- geen\n\n"
        "Antwoord uitsluitend met JSON: "
        '{"ziektebeeld": "<slug of geen>", "confidence": <0..1>, "rationale": "<een zin>"}'
    )
    resp = requests.post(
        OLLAMA_URL,
        json={"model": model, "prompt": prompt, "stream": False, "format": "json",
              "options": {"temperature": 0, "num_ctx": NUM_CTX}},
        timeout=120,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["response"])


def _laad_checkpoint(pad) -> dict[str, Verdict]:
    if pad and Path(pad).is_file():
        ruw = json.loads(Path(pad).read_text(encoding="utf-8"))
        return {t: Verdict(**v) for t, v in ruw.items()}
    return {}


def _schrijf_checkpoint(pad, verdicts: dict[str, Verdict]) -> None:
    Path(pad).parent.mkdir(parents=True, exist_ok=True)
    Path(pad).write_text(
        json.dumps({t: asdict(v) for t, v in verdicts.items()}, ensure_ascii=False, indent=1),
        encoding="utf-8")


class Matcher:
    def __init__(self, ziektebeelden: dict, gebruik_embeddings: bool = True,
                 gebruik_llm: bool = True, ollama_model: str = OLLAMA_MODEL,
                 verifieer_lexicon: bool = False):
        # verifieer_lexicon: laat de LLM OOK de lexicon-treffers herbeoordelen (en flaggen
        # bij afwijking). Alleen zinvol met een sterk model (bv. 14B); een zwak model (3B)
        # verwerpt dan correcte lexicon-treffers. Default uit: lexicon-treffers vertrouwen,
        # LLM alleen voor de niet-lexicon-teksten.
        self.verifieer_lexicon = verifieer_lexicon
        self.slugs = list(ziektebeelden)
        self.profielen = {s: z.referentieprofiel() for s, z in ziektebeelden.items()}
        self.kort = {
            s: (z.naam + ": " + "; ".join(dict.fromkeys(c.omschrijving for c in z.dbc_codes)))[:300]
            for s, z in ziektebeelden.items()
        }
        self.ollama_model = ollama_model
        self._embedder = _Embedder() if gebruik_embeddings else None
        self._profiel_emb = (
            self._embedder.encode([self.profielen[s] for s in self.slugs])
            if self._embedder else None
        )
        self.llm = gebruik_llm and _ollama_beschikbaar()

    def _kandidaten_batch(self, teksten: list[str]) -> dict[str, list[tuple[str, float]]]:
        """Top-k ziektebeelden per tekst op cosine-similarity (gebatcht)."""
        import numpy as np

        if not self._embedder:  # geen embeddings: geef alle slugs als kandidaten
            return {t: [(s, 0.0) for s in self.slugs] for t in teksten}
        embs = np.asarray(self._embedder.encode(teksten))
        scores = embs @ np.asarray(self._profiel_emb).T
        out: dict[str, list[tuple[str, float]]] = {}
        for i, t in enumerate(teksten):
            idx = scores[i].argsort()[::-1][:TOP_K]
            out[t] = [(self.slugs[j], float(scores[i][j])) for j in idx]
        return out

    def _beslis_llm(self, tekst: str, kand: list[tuple[str, float]]) -> Verdict:
        """LLM beslist (met lexicon-hint); flag bij afwijking. Valt terug bij een fout."""
        hint = mapping.map_text(tekst) or ""
        try:
            antwoord = _vraag_llm(tekst, [(s, self.kort[s]) for s, _ in kand], hint, self.ollama_model)
            zb = antwoord.get("ziektebeeld", GEEN)
            zb = zb if zb in self.slugs else GEEN
            return Verdict(tekst, zb, float(antwoord.get("confidence", 0.0)), "llm",
                           str(antwoord.get("rationale", "")), lexicon=hint, flag=bool(hint and hint != zb))
        except Exception:
            if hint:
                return Verdict(tekst, hint, 1.0, "lexicon", lexicon=hint)
            top_slug, top_score = kand[0]
            return (Verdict(tekst, top_slug, top_score, "embedding")
                    if top_score >= EMBED_DREMPEL else Verdict(tekst, GEEN, top_score, "geen-default"))

    def _beslis_zonder_llm(self, tekst: str, kand) -> Verdict:
        hint = mapping.map_text(tekst)
        if hint:
            return Verdict(tekst, hint, 1.0, "lexicon", lexicon=hint)
        if mapping.forceer_geen(tekst):
            return Verdict(tekst, GEEN, 1.0, "lexicon")
        if not self._embedder or not kand:
            return Verdict(tekst, GEEN, 0.0, "geen-default")
        top_slug, top_score = kand[0]
        return (Verdict(tekst, top_slug, top_score, "embedding")
                if top_score >= EMBED_DREMPEL else Verdict(tekst, GEEN, top_score, "geen-default"))

    def _vrijgeven_embedder(self) -> None:
        """Geef het GPU-geheugen van de embedder vrij (na de batch, voor de LLM-loop)."""
        self._embedder = None
        try:
            import gc

            import torch
            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass

    def classify(self, tekst: str) -> Verdict:
        return self.classify_many([tekst])[tekst]

    def classify_many(self, teksten: list[str], checkpoint_path=None) -> dict[str, Verdict]:
        uniek = list(dict.fromkeys(teksten))
        resultaat = {t: v for t, v in _laad_checkpoint(checkpoint_path).items() if t in uniek}
        todo = [t for t in uniek if t not in resultaat]
        if not todo:
            return {t: resultaat[t] for t in uniek}

        if not self.llm:
            kand = self._kandidaten_batch(todo)
            for t in todo:
                resultaat[t] = self._beslis_zonder_llm(t, kand.get(t))
            if checkpoint_path:
                _schrijf_checkpoint(checkpoint_path, resultaat)
            return {t: resultaat[t] for t in uniek}

        # LLM aan. Lexicon-treffers en hemato-vangnet eerst; de rest via de LLM.
        via_llm = []
        for t in todo:
            hint = mapping.map_text(t)
            if hint and not self.verifieer_lexicon:
                resultaat[t] = Verdict(t, hint, 1.0, "lexicon", lexicon=hint)
            elif mapping.forceer_geen(t):
                resultaat[t] = Verdict(t, GEEN, 1.0, "lexicon", lexicon="")
            else:
                via_llm.append(t)
        if checkpoint_path:
            _schrijf_checkpoint(checkpoint_path, resultaat)

        if via_llm:
            kand = self._kandidaten_batch(via_llm)
            if self._embedder:
                self._vrijgeven_embedder()  # GPU vrij voor de LLM-pass (sequentieel)
            for i, t in enumerate(via_llm, 1):
                resultaat[t] = self._beslis_llm(t, kand[t])
                if checkpoint_path and (i % CHECKPOINT_ELKE == 0 or i == len(via_llm)):
                    _schrijf_checkpoint(checkpoint_path, resultaat)
                if i % 50 == 0 or i == len(via_llm):
                    print(f"    LLM {i}/{len(via_llm)}", flush=True)
        return {t: resultaat[t] for t in uniek}
