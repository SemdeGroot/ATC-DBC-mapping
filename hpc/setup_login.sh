#!/bin/bash
# Eenmalige setup op de ALICE LOGIN-node (die internet heeft): installeer Ollama
# user-local in de projectmap en pull het model. Daarna draait de GPU-job offline.
#
# Draaien vanuit de projectmap op de login-node:   bash hpc/setup_login.sh
set -euo pipefail

PROJ="$PWD"
MODEL="${MODEL:-qwen2.5:14b-instruct}"
mkdir -p "$PROJ/ollama/bin" "$PROJ/ollama/models"
export PATH="$PROJ/ollama/bin:$PATH"
export LD_LIBRARY_PATH="$PROJ/ollama/lib:${LD_LIBRARY_PATH:-}"
export OLLAMA_MODELS="$PROJ/ollama/models"
export OLLAMA_HOST="127.0.0.1:11434"

if [ ! -x "$PROJ/ollama/bin/ollama" ]; then
    echo "Ollama downloaden (user-local, geen sudo)..."
    curl -fSL https://ollama.com/download/ollama-linux-amd64.tgz -o /tmp/ollama.tgz
    tar -xzf /tmp/ollama.tgz -C "$PROJ/ollama"
    rm -f /tmp/ollama.tgz
fi

ollama serve > /tmp/ollama_setup.log 2>&1 &
OLLAMA_PID=$!
trap 'kill $OLLAMA_PID 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do ollama list >/dev/null 2>&1 && break; sleep 2; done

echo "Model pullen: $MODEL (~9 GB) ..."
ollama pull "$MODEL"
echo "Setup klaar. Model staat in $OLLAMA_MODELS. Submit nu de job: sbatch hpc/classify.sh"
