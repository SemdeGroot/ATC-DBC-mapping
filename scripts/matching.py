"""Hybride matching: indicatietekst -> DBC-ziektebeeld of 'geen'.

Drie lagen, in volgorde van precisie:
1. lexicon (scripts.mapping) - hoge precisie, eerst;
2. embeddings (BGE-M3, cosine) - top-k kandidaat-ziektebeelden + score;
3. lokale LLM (Ollama, Qwen2.5-7B) - eindoordeel met expliciete 'geen'-optie + rationale.

De embedding- en LLM-laag laden lui (sentence-transformers resp. Ollama); ontbreken ze,
dan degradeert de matcher netjes (lexicon + cosine-drempel, of alleen lexicon).
Op 6 GB VRAM draaien de passes sequentieel: eerst embeddings, daarna de LLM.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from scripts import mapping

GEEN = "geen"
EMBED_MODEL = "BAAI/bge-m3"
# 7B is nauwkeuriger maar past krap in 6 GB VRAM. Past het niet (controleer met
# `ollama ps`: hoog CPU% = traag), gebruik dan "qwen2.5:3b-instruct" - die draait
# volledig op de GPU en is fors sneller, met voor deze afgebakende taak nauwelijks
# kwaliteitsverlies.
OLLAMA_MODEL = "qwen2.5:7b-instruct"
OLLAMA_URL = "http://localhost:11434/api/generate"
NUM_CTX = 2048   # korte prompts; kleine KV-cache zodat het model in 6 GB VRAM past
TOP_K = 4
EMBED_DREMPEL = 0.55  # fallback-drempel als de LLM niet beschikbaar is


@dataclass
class Verdict:
    tekst: str
    ziektebeeld: str           # slug of 'geen'
    score: float               # cosine (embedding) of LLM-confidence
    methode: str               # lexicon | embedding | llm | geen-default
    rationale: str = ""


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


def _vraag_llm(tekst: str, kandidaten: list[tuple[str, str]], model: str) -> dict:
    """Laat de LLM kiezen uit de kandidaat-ziektebeelden of 'geen'. Retour: dict-JSON."""
    opties = "\n".join(f"- {slug}: {profiel}" for slug, profiel in kandidaten)
    prompt = (
        "Je classificeert een Nederlandse geneesmiddel-indicatie naar precies een "
        "DBC-ziektebeeld, of naar 'geen' als de indicatie niet bij een van de opties hoort "
        "(bv. hematologische kanker, auto-immuunziekte, of een tumor die niet in de lijst staat).\n\n"
        f"Indicatie: \"{tekst}\"\n\n"
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


class Matcher:
    def __init__(self, ziektebeelden: dict, gebruik_embeddings: bool = True,
                 gebruik_llm: bool = True, ollama_model: str = OLLAMA_MODEL):
        self.slugs = list(ziektebeelden)
        # Volledig profiel (incl. ICD) voor de embeddings; kort profiel (naam + DBC-
        # omschrijvingen) voor de LLM-prompt, zodat die compact blijft en in NUM_CTX past.
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

        embs = np.asarray(self._embedder.encode(teksten))
        scores = embs @ np.asarray(self._profiel_emb).T  # (n_teksten, n_slugs)
        out: dict[str, list[tuple[str, float]]] = {}
        for i, t in enumerate(teksten):
            idx = scores[i].argsort()[::-1][:TOP_K]
            out[t] = [(self.slugs[j], float(scores[i][j])) for j in idx]
        return out

    def _beslis(self, tekst: str, kand: list[tuple[str, float]]) -> Verdict:
        """LLM-oordeel als beschikbaar, anders cosine-drempel."""
        if self.llm:
            try:
                antwoord = _vraag_llm(tekst, [(s, self.kort[s]) for s, _ in kand], self.ollama_model)
                zb = antwoord.get("ziektebeeld", GEEN)
                zb = zb if zb in self.slugs else GEEN
                return Verdict(tekst, zb, float(antwoord.get("confidence", 0.0)), "llm",
                               str(antwoord.get("rationale", "")))
            except Exception:
                pass  # een kapotte/trage LLM-respons mag de run niet stoppen: val terug
        top_slug, top_score = kand[0]
        return (Verdict(tekst, top_slug, top_score, "embedding")
                if top_score >= EMBED_DREMPEL else Verdict(tekst, GEEN, top_score, "geen-default"))

    def classify(self, tekst: str) -> Verdict:
        return self.classify_many([tekst])[tekst]

    def classify_many(self, teksten: list[str]) -> dict[str, Verdict]:
        resultaat: dict[str, Verdict] = {}
        deferred: list[str] = []
        for t in dict.fromkeys(teksten):
            slug = mapping.map_text(t)
            if slug:
                resultaat[t] = Verdict(t, slug, 1.0, "lexicon")
            elif self._embedder:
                deferred.append(t)
            else:
                resultaat[t] = Verdict(t, GEEN, 0.0, "geen-default")
        if deferred:
            kand = self._kandidaten_batch(deferred)
            for i, t in enumerate(deferred, 1):
                resultaat[t] = self._beslis(t, kand[t])
                if self.llm and (i % 50 == 0 or i == len(deferred)):
                    print(f"    LLM {i}/{len(deferred)}", flush=True)
        return resultaat
