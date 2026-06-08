# De LLM-classificatie op de Leiden HPC (ALICE) draaien

De zware stap (de LLM) draait los van de rest. Lokaal bouw je een kleine **worklist**,
op ALICE classificeer je die met een groter model (Qwen2.5-14B op 1x RTX 2080 Ti), en
lokaal bouw je daarna de Excel. ALICE heeft geen embeddings/Kompas/S3 nodig - alleen
`worklist.json` en Ollama.

```
lokaal:  export_worklist  ->  data/worklist.json
ALICE:   classify_worklist (14B)  ->  data/verdicts.json   (resumebaar)
lokaal:  main.py --reuse-verdicts  ->  output/dbc_drugs.xlsx
```

## 0. Lokaal: de worklist maken

```bash
./venv/bin/python -m scripts.export_worklist
# voor de 14B mag de LLM ook lexicon-treffers herzien:
# ./venv/bin/python -m scripts.export_worklist --verify-lexicon
```

## 1. Inloggen op ALICE

```bash
ssh <ulcn-gebruiker>@login1.alice.universiteitleiden.nl
```

Gebruik je eigen ULCN-account. (Buiten het universiteitsnetwerk: eerst de Leiden-VPN aan,
of via de jumphost zoals in de ALICE-documentatie.)

## 2. Code + worklist naar je persoonlijke ALICE-map

Zet het project in je **persoonlijke** projectmap op ALICE (niet in een gedeelde
cursusmap), bv. onder `/data1/<gebruiker>/` of je home. Vanaf je laptop:

```bash
DEST=<ulcn-gebruiker>@login1.alice.universiteitleiden.nl:/data1/<gebruiker>/ATC-IKNL
# code (zonder venv/data-bulk), en de worklist apart:
rsync -avz --exclude venv --exclude data/g-standaard --exclude data/kompas-cache \
      --exclude output --exclude .git ./ "$DEST/"
rsync -avz data/worklist.json "$DEST/data/"
```

`scripts/`, `main.py`, `hpc/` en `data/worklist.json` zijn genoeg; de G-standaard, de
Kompas-cache en de embeddings hoeven NIET mee.

## 3. Eenmalige setup op de login-node (heeft internet)

```bash
cd /data1/<gebruiker>/ATC-IKNL
bash hpc/setup_login.sh          # installeert Ollama user-local + pullt qwen2.5:14b-instruct
```

(De compute-nodes hebben vaak geen internet; daarom pullen we het model hier.)

## 4. De GPU-job submitten

```bash
sbatch hpc/classify.sh           # 1x 2080 Ti, max 8 uur, resumebaar
squeue --me                      # status
tail -f logs/<jobid>.out         # voortgang (LLM x/y)
```

Valt de job uit of loopt de walltime af, submit dan gewoon opnieuw: `verdicts.json` wordt
incrementeel weggeschreven, dus een herstart pakt alleen de resterende teksten op.

## 5. Resultaat terughalen en lokaal de Excel bouwen

```bash
# op je laptop:
rsync -avz <ulcn-gebruiker>@login1.alice.universiteitleiden.nl:/data1/<gebruiker>/ATC-IKNL/data/verdicts.json data/
./venv/bin/python main.py --reuse-verdicts
# voor de --verify-lexicon-variant: ./venv/bin/python main.py --reuse-verdicts --verify-lexicon
```

`output/dbc_drugs.xlsx` is dan klaar voor de apotheker.

## Aandachtspunten
- Past het model niet (`logs/ollama_*.log` toont CPU-fallback), kies dan een kleiner
  model: `MODEL=qwen2.5:7b-instruct sbatch hpc/classify.sh`.
- Quota: `/data1` heeft meer ruimte dan je home; zet het project en `ollama/models` daar.
- Node-excludes `node860,node857` staan al in de job (bekende kapotte CUDA-nodes).
