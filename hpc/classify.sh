#!/bin/bash
# SLURM-job voor de Leiden HPC (ALICE): classificeer data/worklist.json met vLLM + een
# HuggingFace-model (standaard Qwen2.5-14B-Instruct-AWQ, ~9 GB, past op 1x RTX 2080 Ti
# 11 GB). Schrijft data/verdicts.json (incrementeel, resumebaar). Alles in de job;
# HuggingFace is bereikbaar vanaf de compute-node.
#
# Submitten vanuit de projectmap:   sbatch hpc/classify.sh
# Ander model (bv. kleiner):         MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ sbatch hpc/classify.sh
#SBATCH -J atc-dbc-llm
#SBATCH -p gpu-2080ti-11g
#SBATCH --gres=gpu:2080_ti:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH -t 08:00:00
#SBATCH --exclude=node860,node857
#SBATCH --output=logs/%j.out
set -euo pipefail

PROJ="${SLURM_SUBMIT_DIR:-$PWD}"
cd "$PROJ"
mkdir -p logs
MODEL="${MODEL:-Qwen/Qwen2.5-14B-Instruct-AWQ}"

echo "Node: $(hostname)"; nvidia-smi -L || true

# HuggingFace-cache in de projectmap (op /zfsstore of /data1), niet je home-quota.
export HF_HOME="$PROJ/.hf_cache"
mkdir -p "$HF_HOME"

# Aparte venv met vLLM (brengt zijn eigen torch mee; los van de embeddings-venv).
module load Python/3.11.5-GCCcore-13.2.0 2>/dev/null || module load Miniconda3 2>/dev/null || true
[ -d venv-vllm ] || python3 -m venv venv-vllm
source venv-vllm/bin/activate
python -c "import vllm" 2>/dev/null || pip install -q --upgrade pip vllm requests

echo "Classificeren met vLLM ($MODEL) ..."
python -m scripts.classify_worklist --backend vllm --model "$MODEL"
echo "Klaar. Haal data/verdicts.json terug met rsync en draai lokaal: python main.py --reuse-verdicts"
