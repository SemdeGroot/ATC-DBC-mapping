"""Audit the Kompas -> IKNL mapping over a broad set of oncology drugs.

Scrapes every drug in DRUGS, maps each indication entry, and reports which entries
stay unmatched so the keyword table in mapping.py can be closed gap by gap. Run
this, inspect the unmatched list, extend SYNONYMS/ABBREVIATIONS, repeat.
"""
from __future__ import annotations

from scripts.drugs import DRUGS
from scripts.iknl import fetch_taxonomy
from scripts.kompas import fetch_indications
from scripts.mapping import map_entry
from scripts.polite_http import FetchError, PoliteClient


def main() -> None:
    client = PoliteClient()
    taxonomy = fetch_taxonomy(client)
    print(f"IKNL tumorgroepen: {len(taxonomy)}\n")

    total = 0
    matched = 0
    unmatched_headings: dict[str, set[str]] = {}
    no_match_drugs: list[str] = []
    missing_pages: list[str] = []

    for drug in DRUGS:
        try:
            indications = fetch_indications(client, drug)
        except FetchError as exc:
            missing_pages.append(f"{drug}: {exc}")
            continue
        drug_matched = 0
        for entry in indications.entries:
            total += 1
            if map_entry(entry):
                matched += 1
                drug_matched += 1
            else:
                # Group misses by context: a context that never matches is the real
                # signal, treatment-line fragments under a matched context are noise.
                label = entry.context or entry.text
                unmatched_headings.setdefault(label, set()).add(drug)
        if indications.entries and drug_matched == 0:
            no_match_drugs.append(drug)

    print(f"Entries totaal:   {total}")
    print(f"Entries gematcht: {matched}")
    print(f"Entries niet-gematcht: {total - matched}\n")

    if missing_pages:
        print("== Pagina niet gevonden / fout ==")
        for line in missing_pages:
            print(f"  {line}")
        print()

    if no_match_drugs:
        print("== Middelen zonder enige match (controleer: niet-onco of gemist?) ==")
        for drug in no_match_drugs:
            print(f"  {drug}")
        print()

    print("== Niet-gematchte kopjes/items (kopje -> middelen) ==")
    for label in sorted(unmatched_headings):
        drugs = ", ".join(sorted(unmatched_headings[label]))
        print(f"  [{drugs}]\n    {label}")


if __name__ == "__main__":
    main()
