# De LLM-classificatie op de Leiden HPC (ALICE) draaien

De zware stap (de LLM) draait los van de rest. Lokaal bouw je een kleine **worklist**,
op ALICE classificeer je die met **vLLM + een HuggingFace-model** (Qwen2.5-14B-Instruct-AWQ
op 1x RTX 2080 Ti), en lokaal bouw je daarna de Excel. ALICE heeft geen embeddings/Kompas/S3
nodig - alleen `worklist.json`, vLLM en het HF-model (HuggingFace is bereikbaar op ALICE).

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

## 3. De GPU-job submitten

De job draait alles op de compute-node (heeft internet): hij maakt een venv met vLLM
(`venv-vllm/`), downloadt het HF-model naar `.hf_cache/` (op /zfsstore of /data1) en
classificeert. Niets op de login-node.

```bash
cd /data1/<gebruiker>/ATC-IKNL
sbatch hpc/classify.sh           # 1x 2080 Ti, max 8 uur, resumebaar
squeue --me                      # status
tail -f logs/<jobid>.out         # voortgang (vLLM x/y) + "Device: cuda"
```

Valt de job uit of loopt de walltime af, submit dan gewoon opnieuw: zowel het model
(`.hf_cache/`) als `verdicts.json` worden gecachet, dus een herstart pakt alleen de
resterende teksten op.

## 4. Resultaat terughalen en lokaal de Excel bouwen

```bash
# op je laptop:
rsync -avz <ulcn-gebruiker>@login1.alice.universiteitleiden.nl:/data1/<gebruiker>/ATC-IKNL/data/verdicts.json data/
./venv/bin/python main.py --reuse-verdicts
# voor de --verify-lexicon-variant: ./venv/bin/python main.py --reuse-verdicts --verify-lexicon
```

`output/dbc_drugs.xlsx` is dan klaar voor de apotheker.

## Aandachtspunten
- Past de 14B niet in 11 GB of werkt de AWQ-kernel niet op de 2080 Ti, kies een kleiner
  of ander gequantiseerd model: `MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ sbatch hpc/classify.sh`
  (of een GPTQ-variant). De prompts zijn kort, dus `max_model_len=2048` volstaat.
- Quota: zet het project en `.hf_cache/` + `venv-vllm/` op `/data1` of `/zfsstore`, niet je home.
- Node-excludes `node860,node857` staan al in de job (bekende kapotte CUDA-nodes).
- **Getest:** de classificatielogica (export -> classify -> verdicts -> Excel) is lokaal
  end-to-end gevalideerd; de vLLM-op-ALICE-stap (module-namen, vLLM-install, AWQ op de
  2080 Ti) is gebaseerd op de ALICE-docs en kan een kleine aanpassing nodig hebben.
