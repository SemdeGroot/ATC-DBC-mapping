# ATC-IKNL

Koppelt indicaties uit het Farmacotherapeutisch Kompas aan de algemene
tumorgroep-indeling van de IKNL (Nederlandse Kankerregistratie).


## Installeren

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Draaien

```bash
./venv/bin/python main.py
```

Dit scrapet (beleefd, met cache) de IKNL-tumorgroepen en de geneesmiddelen uit
`drugs.py`, bepaalt per middel de set IKNL-tumorgroepen, en schrijft een rij per
(middel, tumorgroep) naar `output/drug_tumorgroep.csv`.

Pagina's worden lokaal gecachet in `cache/`; een tweede run doet geen
netwerkverkeer. Verwijder `cache/` om opnieuw op te halen.

## Mapping controleren / verfijnen

```bash
./venv/bin/python audit_mapping.py
```

Toont per middel de niet-gematchte kopjes/items. Een kopje dat nooit matcht is het
signaal voor een ontbrekend keyword; behandellijn-fragmenten en niet-oncologische
indicaties (MS, RA, Crohn) horen ongekoppeld te blijven.

## Aanpassen

* Geneesmiddelen: pas `DRUGS` in `drugs.py` aan (wordt later de Excel-input).
* Mapping verfijnen: pas `SYNONYMS` / `ABBREVIATIONS` in `mapping.py` aan.
