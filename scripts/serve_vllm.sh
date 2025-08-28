#!/usr/bin/env bash
set -euo pipefail

CONDA_ENV=${CONDA_ENV:-llm}
export VLLM_WORKER_GPU_MEM_FRACTION=${VLLM_WORKER_GPU_MEM_FRACTION:-0.90}
export VLLM_ATTENTION_BACKEND=${VLLM_ATTENTION_BACKEND:-FLASHINFER}

MODEL=${MODEL:-Qwen/Qwen2.5-7B-Instruct}
PORT=${PORT:-8000}

echo "[vLLM] Serving model: $MODEL on port $PORT"
exec conda run -n "$CONDA_ENV" python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" \
  --port "$PORT" \
  --tensor-parallel-size "${TP_SIZE:-1}" \
  --max-model-len "${MAX_LEN:-32768}" \
  --dtype "${DTYPE:-bfloat16}" \
  --gpu-memory-utilization "$VLLM_WORKER_GPU_MEM_FRACTION"


