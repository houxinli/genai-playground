#!/usr/bin/env bash
set -euo pipefail

CONDA_ENV=${CONDA_ENV:-llm}
MODEL=${MODEL:-deadbydawn101/gemma-4-E2B-Heretic-Uncensored-mlx-4bit}
PORT=${PORT:-8080}
HOST=${HOST:-127.0.0.1}
HF_HOME=${HF_HOME:-$HOME/.cache/huggingface}
export HF_HOME
export HF_HUB_ENABLE_HF_TRANSFER=${HF_HUB_ENABLE_HF_TRANSFER:-0}
export PYTHONUNBUFFERED=1

mkdir -p "$HF_HOME"

echo "[MLX] Serving model: $MODEL"
echo "[MLX] Host: $HOST"
echo "[MLX] Port: $PORT"
echo "[MLX] HF_HOME: $HF_HOME"

exec conda run -n "$CONDA_ENV" python -m mlx_lm server \
  --model "$MODEL" \
  --host "$HOST" \
  --port "$PORT"
