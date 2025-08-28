#!/usr/bin/env bash
set -euo pipefail

CONDA_ENV=${CONDA_ENV:-llm}
export VLLM_WORKER_GPU_MEM_FRACTION=${VLLM_WORKER_GPU_MEM_FRACTION:-0.90}
export VLLM_ATTENTION_BACKEND=${VLLM_ATTENTION_BACKEND:-XFORMERS}
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=${VLLM_ALLOW_LONG_MAX_MODEL_LEN:-1}

# 使用标准的 Qwen3-4B 模型
MODEL=${MODEL:-Qwen/Qwen3-4B}
PORT=${PORT:-8000}

echo "[vLLM] Serving model: $MODEL on port $PORT"
echo "[vLLM] Using attention backend: $VLLM_ATTENTION_BACKEND"
echo "[vLLM] Max model length: ${MAX_LEN:-40960}"

exec conda run -n "$CONDA_ENV" python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" \
  --port "$PORT" \vllo
  --tensor-parallel-size "${TP_SIZE:-1}" \
  --max-model-len "${MAX_LEN:-40960}" \
  --dtype "${DTYPE:-auto}" \
  --gpu-memory-utilization "$VLLM_WORKER_GPU_MEM_FRACTION"


