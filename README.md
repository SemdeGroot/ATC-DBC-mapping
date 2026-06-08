# ATC-IKNL: geneesmiddelen koppelen aan DBC-diagnosecodes

> **Onderzoekscontext.** Dit is een eenmalige, niet-commerciele data-analyse, uitgevoerd
> tijdens mijn Farmacie-coschap in het ziekenhuis, ten behoeve van het IKNL (Integraal
> Kankercentrum Nederland). Doel: in kaart brengen welke geneesmiddelen bij welke
> DBC-diagnosecodes uit de DICA/DMA-inclusiecriteria horen. De gebruikte bronnen zijn de
> G-standaard (Z-Index), een lokaal gecachete kopie van Farmacotherapeutisch-Kompas-teksten
> en - voor de zware modelstap - de Leiden HPC (ALICE). Alle verwerking is lokaal/offline;
> er worden geen patientgegevens gebruikt. Vragen of zorgen over het gebruik van een bron of
> systeem? Neem gerust contact op - dit is legitiem onderzoekswerk en ik pas het graag aan.

## Wat doet dit

Voor elke werkzame stof (ATC-code) binnen scope (oncologie **L**, diabetes **A10**,
obesitas **A08**) bepalen we de bijbehorende **DBC-diagnosecodes**. Er bestaat geen directe
ATC->DBC-tabel, dus de koppeling loopt via de indicatie:

```
geneesmiddel (ATC7) -> indicatie -> DBC-ziektebeeld -> DBC-codes
```

- **Diabetes/obesitas** zijn triviaal: de ATC-groep is de diagnose (A10 = diabetes, A08 = obesitas).
- **Oncologie (L)** is het lastige geval: de ATC-groep zegt niets over de tumor, dus we lezen
  de indicatietekst en classificeren die naar 1 van de 14 DBC-ziektebeelden of "geen".

Twee bronnen per stof: de officiele **add-on-indicatie** uit de G-standaard (autoritair) en
de **Kompas**-indicatiesectie (aanvullend). De matching is een hybride: een hoge-precisie
**lexicon** (trefwoorden/afkortingen) doet de duidelijke gevallen, een **embedding**-model
(BGE-M3) levert kandidaten, en een lokale **LLM** (Ollama/Qwen) beslist de rest, met een
expliciete "geen"-optie. Een mens controleert alleen de gemarkeerde gevallen.

## Eenmalige voorbereiding

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python -m scripts.build_gstandaard_db     # data/gstandaard.sqlite (uit data/g-standaard/extracted)
./venv/bin/python -c "from scripts import kompas; print(kompas.sync())"   # Kompas-cache uit S3 (prod-profiel)
```

Lokaal draait de LLM via [Ollama](https://ollama.com); `ollama pull qwen2.5:3b-instruct`.

## Draaien

```bash
./venv/bin/python main.py --model qwen2.5:3b-instruct
```

Output in `output/`:
- `dbc_drugs.xlsx` - **de deliverable** (15 tabbladen): tab "Medicatie" met geel-gemarkeerde
  te-controleren koppelingen + een tab per DBC-ziektebeeld met de medicatielijst (incl.
  Add-on/EVS en off-label-vlag). Middelen zonder ziektebeeld staan onderaan als "geen".
- `drug_dbc.csv` - dezelfde data plat (databron, per DBC-code).

Opties: `--no-llm` (alleen lexicon+embeddings), `--reuse-verdicts` (alleen output herbouwen
uit `data/verdicts.json`), `--verify-lexicon` (LLM herziet ook lexicon-treffers; alleen met
een sterk model), `--limit N` (subset, voor tests).

## Controle door de apotheker (HITL)

In `dbc_drugs.xlsx`, tab "Medicatie", staan de **gele** rijen die controle nodig hebben.
Corrigeer waar nodig in de kolom `correctie` (dropdown met de 14 ziektebeelden + "geen"),
en draai daarna de macro `macro/HergroepeerZiektebeelden.bas` (Alt+F11 -> importeren ->
uitvoeren). De ziektebeeld-tabbladen worden dan op basis van je correcties bijgewerkt.

## Grote modelrun op de HPC

Voor een nauwkeuriger run met een groter model (Qwen2.5-14B) op de Leiden HPC: zie
[`hpc/README.md`](hpc/README.md). Kort: lokaal `export_worklist`, op ALICE
`classify_worklist` (resumebaar), daarna lokaal `main.py --reuse-verdicts`.

## Structuur

Analysemodules in `scripts/`, orkestrator `main.py` in de root. Het uitgewerkte plan en de
verantwoording staan in `prompts/atc-dbc-mapping.md`; codeconventies in `CLAUDE.md`.
