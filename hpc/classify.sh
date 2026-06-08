#!/bin/bash
# SLURM-job voor de Leiden HPC (ALICE): classificeer data/worklist.json met een
# Ollama-LLM op 1x RTX 2080 Ti (11 GB). Schrijft data/verdicts.json (resumebaar).
#
# Submitten vanuit de projectmap:   sbatch hpc/classify.sh
# Groter model overschrijven:        MODEL=qwen2.5:14b-instruct sbatch hpc/classify.sh
#SBATCH -J atc-dbc-llm
#SBATCH -p gpu-2080ti-11g
#SBATCH --gres=gpu:2080_ti:1
#SBATCH --cpus-per-task=6
#SBATCH --mem=24G
#SBATCH -t 08:00:00
#SBATCH --exclude=node860,node857
#SBATCH --output=logs/%j.out
set -euo pipefail

PROJ="${SLURM_SUBMIT_DIR:-$PWD}"
cd "$PROJ"
mkdir -p logs
MODEL="${MODEL:-qwen2.5:14b-instruct}"

echo "Node: $(hostname)"; nvidia-smi -L || true

# Ollama user-local: binary + modellen in de projectmap (geen sudo, geen home-quota).
export PATH="$PROJ/ollama/bin:$PATH"
export LD_LIBRARY_PATH="$PROJ/ollama/lib:${LD_LIBRARY_PATH:-}"
export OLLAMA_MODELS="$PROJ/ollama/models"
export OLLAMA_HOST="127.0.0.1:11434"
if ! command -v ollama >/dev/null 2>&1; then
    echo "FOUT: ollama niet gevonden. Draai eerst hpc/setup_login.sh op de login-node." >&2
    exit 1
fi

# Start de Ollama-server op de achtergrond en wacht tot hij reageert.
ollama serve > "logs/ollama_${SLURM_JOB_ID}.log" 2>&1 &
OLLAMA_PID=$!
trap 'kill $OLLAMA_PID 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do ollama list >/dev/null 2>&1 && break; sleep 2; done
ollama list | grep -q "${MODEL%%:*}" || ollama pull "$MODEL"   # pull als nog niet aanwezig

# Lichte venv: classify_worklist heeft alleen 'requests' nodig (geen torch).
module load Python/3.11.5-GCCcore-13.2.0 2>/dev/null || module load Miniconda3 2>/dev/null || true
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
python -m pip install -q --upgrade pip requests >/dev/null 2>&1 || true

echo "Classificeren met $MODEL ..."
python -m scripts.classify_worklist --model "$MODEL"
echo "Klaar. Haal data/verdicts.json terug met rsync en draai lokaal: python main.py --reuse-verdicts"
