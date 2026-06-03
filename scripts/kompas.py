"""Scrape Farmacotherapeutisch Kompas preparaatteksten for the Indicaties section.

A preparaattekst exposes the indications block as an element whose id ends in
"-indicaties" (the contra-indications block ends in "-contra-indicaties" and is
skipped). Inside, each tumor type is introduced by a sub-heading (h3-h6) or an intro
paragraph, and the bullets below it are treatment-line variations that often omit
the tumor name. Each bullet is paired with that preceding context so the tumor
name is not lost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from scripts.polite_http import FetchError, PoliteClient

BASE_URL = "https://www.farmacotherapeutischkompas.nl/bladeren/preparaatteksten"


@dataclass
class IndicationEntry:
    context: str
    text: str


@dataclass
class KompasIndications:
    name: str
    slug: str
    url: str
    entries: list[IndicationEntry] = field(default_factory=list)


def to_slug(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[\s/]+", "_", slug)
    return re.sub(r"[^a-z0-9_]", "", slug)


def build_url(name: str) -> str:
    slug = to_slug(name)
    return f"{BASE_URL}/{slug[0]}/{slug}"


def _split_items(text: str) -> list[str]:
    parts = re.split(r"[;\n]", text)
    return [item for item in (p.strip().strip(".").strip() for p in parts) if item]


def _direct_text(element) -> str:
    # Text of this list item only, excluding any nested ul/ol so a parent bullet
    # does not absorb its children's text.
    parts = []
    for child in element.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.name in ("ul", "ol"):
            continue
        else:
            parts.append(child.get_text(" ", strip=True))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def parse_indications(html: str, name: str, url: str) -> KompasIndications:
    soup = BeautifulSoup(html, "lxml")

    section = None
    for element in soup.find_all(id=re.compile(r"indicaties$")):
        if element.get("id", "").endswith("contra-indicaties"):
            continue
        section = element
        break
    if section is None:
        raise FetchError(f"no indicaties section found for {name}")

    entries: list[IndicationEntry] = []
    current_context = ""
    for element in section.descendants:
        tag = getattr(element, "name", None)
        if tag in ("h3", "h4", "h5", "h6"):
            heading = element.get_text(" ", strip=True)
            if heading and heading.lower() != "indicaties":
                current_context = heading
        elif tag == "p":
            intro = element.get_text(" ", strip=True)
            if intro:
                current_context = intro
        elif tag == "li":
            for piece in _split_items(_direct_text(element)):
                entries.append(IndicationEntry(context=current_context, text=piece))

    if not entries:
        # Some preparaatteksten phrase the indications as paragraphs, not a list.
        for paragraph in section.find_all("p"):
            for piece in _split_items(paragraph.get_text(" ", strip=True)):
                entries.append(IndicationEntry(context="", text=piece))

    seen: set[tuple[str, str]] = set()
    unique: list[IndicationEntry] = []
    for entry in entries:
        key = (entry.context.lower(), entry.text.lower())
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    return KompasIndications(name=name, slug=to_slug(name), url=url, entries=unique)


def fetch_indications(client: PoliteClient, name: str) -> KompasIndications:
    url = build_url(name)
    html = client.get(url)
    return parse_indications(html, name, url)
