"""Scrape the IKNL kankersoorten taxonomy: the official Dutch tumor-group list.

The /kankersoorten overview links to one page per tumorgroep at
/kankersoorten/<slug>. Those 27 groups are the "general indication" level we map
Kompas indications onto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from scripts.polite_http import PoliteClient

KANKERSOORTEN_URL = "https://iknl.nl/kankersoorten"


@dataclass(frozen=True)
class Tumorgroep:
    name: str
    slug: str
    url: str


def parse_taxonomy(html: str) -> list[Tumorgroep]:
    soup = BeautifulSoup(html, "lxml")
    groups: dict[str, Tumorgroep] = {}
    for anchor in soup.find_all("a", href=re.compile(r"^/kankersoorten/[^/]+$")):
        slug = anchor["href"].rsplit("/", 1)[-1]
        name = anchor.get_text(" ", strip=True)
        if not name:
            continue
        groups.setdefault(slug, Tumorgroep(name=name, slug=slug, url=f"https://iknl.nl{anchor['href']}"))
    return sorted(groups.values(), key=lambda group: group.name.lower())


def fetch_taxonomy(client: PoliteClient) -> list[Tumorgroep]:
    return parse_taxonomy(client.get(KANKERSOORTEN_URL))
