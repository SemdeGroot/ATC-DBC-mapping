"""Map a list of drugs to their general IKNL tumorgroepen.

For each drug the Kompas indications are scraped and every indication entry is
mapped to an IKNL tumorgroep. The result per drug is the set of tumorgroepen it is
indicated for (the general indication level). Output is one CSV row per
(drug, tumorgroep).

Later the drug list comes from an Excel input and the output becomes Excel; for now
the list lives in drugs.py and the result is a CSV.
"""
from __future__ import annotations

import csv
from pathlib import Path

from scripts.drugs import DRUGS
from scripts.iknl import fetch_taxonomy
from scripts.kompas import fetch_indications
from scripts.mapping import couple
from scripts.polite_http import FetchError, PoliteClient

OUTPUT_PATH = Path(__file__).parent / "output" / "drug_tumorgroep.csv"


def main() -> None:
    client = PoliteClient()
    taxonomy = fetch_taxonomy(client)
    print(f"IKNL tumorgroepen: {len(taxonomy)}\n")

    rows = []
    empty = []
    missing = []
    for drug in DRUGS:
        try:
            indications = fetch_indications(client, drug)
        except FetchError as exc:
            missing.append(f"{drug}: {exc}")
            continue

        tumorgroepen = sorted({name for c in couple(indications, taxonomy) for name in c.tumorgroepen})
        if tumorgroepen:
            print(f"{drug}: {', '.join(tumorgroepen)}")
            for tumorgroep in tumorgroepen:
                rows.append({"geneesmiddel": drug, "iknl_tumorgroep": tumorgroep})
        else:
            empty.append(drug)
            print(f"{drug}: (geen tumorgroep)")

    if missing:
        print("\nPagina niet gevonden:")
        for line in missing:
            print(f"  {line}")
    if empty:
        print("\nGeen tumorgroep (controleer of dit een niet-oncologisch middel is):")
        for drug in empty:
            print(f"  {drug}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["geneesmiddel", "iknl_tumorgroep"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nResultaat opgeslagen: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
