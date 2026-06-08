"""Tests voor de matcher-bedrading (lexiconlaag, offline; geen modeldownload)."""
import pytest

from scripts.dbc import load_ziektebeelden
from scripts.matching import GEEN, Matcher


@pytest.fixture(scope="module")
def matcher():
    # Zonder embeddings/LLM: alleen de lexiconlaag + nette degradatie.
    return Matcher(load_ziektebeelden(), gebruik_embeddings=False, gebruik_llm=False)


def test_lexicon_treffer(matcher):
    v = matcher.classify("gemetastaseerd mammacarcinoom")
    assert v.ziektebeeld == "borstkanker"
    assert v.methode == "lexicon"
    assert v.score == 1.0


def test_defert_zonder_engine_naar_geen(matcher):
    v = matcher.classify("Multiple sclerose")  # geen lexicon-treffer, geen hemato-term
    assert v.ziektebeeld == GEEN
    assert v.methode == "geen-default"


def test_hemato_vangnet_naar_geen(matcher):
    # hematologische termen -> hoge-precisie 'geen', niet aan een solide tumor
    for tekst in ("Chronische lymfatische leukemie", "non-Hodgkinlymfoom", "multipel myeloom"):
        assert matcher.classify(tekst).ziektebeeld == GEEN


def test_classify_many_dedupliceert(matcher):
    res = matcher.classify_many(["obesitas bij volwassenen", "obesitas bij volwassenen"])
    assert len(res) == 1
    assert res["obesitas bij volwassenen"].ziektebeeld == "obesitas"
