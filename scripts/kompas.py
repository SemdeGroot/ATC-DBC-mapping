"""Kompas-preparaatteksten uit de Remedice S3-mirror lezen en de Indicaties parsen.

De gescrapete preparaatteksten staan in de prod-bucket onder prefix `preparaat/`
(een markdown per geneesmiddel + een .metadata.json sidecar). `sync()` spiegelt ze
lokaal via de AWS-CLI; daarna parseren we per bestand de ATC-code (uit de subtitel)
en de `## Indicaties`-sectie.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

S3_BUCKET = "remedice-prod-scraped-content"
S3_PREFIX = "preparaat/"
AWS_PROFILE = "remedice-prod-bootstrap"
AWS_REGION = "eu-central-1"
CACHE_DIR = _ROOT / "data" / "kompas-cache" / "preparaat"

# ATC in de subtitelregel, bv. "*azitromycine (oculair) | ... | S01AA26*".
_ATC = re.compile(r"\b([A-Z]\d{2}[A-Z]{2}\d{2})\b")
# Markdown-link [tekst](url) -> tekst.
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


@dataclass
class Preparaat:
    slug: str          # bestandsnaam zonder extensie (S3-sleutel)
    titel: str
    atc: str | None
    indicaties: list[str]


def sync(profile: str = AWS_PROFILE) -> int:
    """Spiegel preparaat/*.md lokaal (zonder de .metadata.json sidecars).

    Retourneert het aantal lokale .md-bestanden na de sync.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "aws", "s3", "sync",
        f"s3://{S3_BUCKET}/{S3_PREFIX}", str(CACHE_DIR),
        "--profile", profile, "--region", AWS_REGION,
        "--exclude", "*", "--include", "*.md", "--exclude", "*.metadata.json",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"aws s3 sync faalde:\n{res.stderr.strip()}")
    return sum(1 for _ in CACHE_DIR.glob("*.md"))


def remote_count(profile: str = AWS_PROFILE) -> int:
    """Aantal .md-objecten in de bucket (voor de volledigheidscheck)."""
    cmd = [
        "aws", "s3", "ls", f"s3://{S3_BUCKET}/{S3_PREFIX}",
        "--recursive", "--profile", profile, "--region", AWS_REGION,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"aws s3 ls faalde:\n{res.stderr.strip()}")
    return sum(1 for ln in res.stdout.splitlines() if ln.endswith(".md"))


def _schoon(tekst: str) -> str:
    return _LINK.sub(r"\1", tekst).strip()


def parse(md: str, slug: str = "") -> Preparaat:
    """Parse een preparaattekst: titel, ATC en de Indicaties-bullets."""
    regels = md.splitlines()
    titel = ""
    atc = None
    for r in regels[:6]:
        if r.startswith("# ") and not titel:
            titel = r[2:].strip()
        if atc is None:
            m = _ATC.search(r)
            if m:
                atc = m.group(1)

    indicaties: list[str] = []
    in_sectie = False
    for r in regels:
        if r.startswith("## "):
            in_sectie = r[3:].strip().lower() == "indicaties"
            continue
        if not in_sectie:
            continue
        s = r.strip()
        if not s or s.lower().startswith("gerelateerde informatie"):
            continue
        if s.startswith("- "):
            item = _schoon(s[2:].rstrip(";.").strip())
            if item:
                indicaties.append(item)
    return Preparaat(slug=slug, titel=titel, atc=atc, indicaties=indicaties)


def in_scope(atc: str | None) -> bool:
    """Scope: oncologie (L), diabetes (A10) en obesitas (A08)."""
    return bool(atc) and (atc.startswith("L") or atc.startswith("A10") or atc.startswith("A08"))


def load_preparaten(alleen_scope: bool = True) -> list[Preparaat]:
    """Lees alle gecachete preparaatteksten in (optioneel gefilterd op scope)."""
    if not CACHE_DIR.is_dir():
        raise FileNotFoundError(f"{CACHE_DIR} ontbreekt; draai eerst kompas.sync()")
    uit = []
    for pad in sorted(CACHE_DIR.glob("*.md")):
        prep = parse(pad.read_text(encoding="utf-8"), slug=pad.stem)
        if not alleen_scope or in_scope(prep.atc):
            uit.append(prep)
    return uit
