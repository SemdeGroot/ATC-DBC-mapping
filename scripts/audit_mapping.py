"""Diagnose voor het lexicon (laag 1): welke indicatieteksten matcht het nog niet?

Toont per bron (add-on / kompas) hoeveel distinctieve teksten het lexicon dekt en
welke het laat lopen. Niet-gematchte teksten zijn het signaal voor een ontbrekend
keyword (of horen terecht bij 'geen'). Draaien:

    ./venv/bin/python -m scripts.audit_mapping [--bron add-on|kompas|beide] [--toon N]
"""
from __future__ import annotations

import argparse
import collections

from scripts import drugs, mapping


def _teksten_per_bron(universe) -> dict[str, list[str]]:
    addon, kompas_teksten = {}, {}
    for g in universe.values():
        for ind in g.addon:
            addon[ind["inid"]] = ind["inkort"]
        for b in g.kompas_indicaties:
            kompas_teksten[b.lower()] = b
    return {"add-on": list(addon.values()), "kompas": list(kompas_teksten.values())}


def audit(bron: str = "beide", toon: int = 40) -> None:
    universe = drugs.build_universe()
    per_bron = _teksten_per_bron(universe)
    bronnen = ["add-on", "kompas"] if bron == "beide" else [bron]

    for b in bronnen:
        teksten = per_bron[b]
        hits = collections.Counter()
        defer = []
        for t in teksten:
            slug = mapping.map_text(t)
            (hits.update([slug]) if slug else defer.append(t))
        tot = len(teksten) or 1
        print(f"\n=== {b}: {len(teksten)} distinct | lexicon {len(teksten)-len(defer)} "
              f"({100*(len(teksten)-len(defer))//tot}%) | defer {len(defer)} ===")
        for slug, c in hits.most_common():
            print(f"   {slug:22} {c}")
        print(f"-- niet gematcht (eerste {toon}, mogelijk lexicon-gat of terecht 'geen') --")
        for t in defer[:toon]:
            print("   |", t)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bron", choices=["add-on", "kompas", "beide"], default="beide")
    ap.add_argument("--toon", type=int, default=40)
    args = ap.parse_args()
    audit(args.bron, args.toon)
