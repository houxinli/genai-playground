#!/usr/bin/env bash
set -euo pipefail

# 设置环境变量以显示下载进度
export HF_HUB_ENABLE_HF_TRANSFER=1
export HUGGINGFACE_HUB_VERBOSITY=debug
export HF_HUB_DISABLE_PROGRESS_BARS=0

CONDA_ENV=${CONDA_ENV:-llm}
export VLLM_WORKER_GPU_MEM_FRACTION=${VLLM_WORKER_GPU_MEM_FRACTION:-0.90}
export VLLM_ATTENTION_BACKEND=${VLLM_ATTENTION_BACKEND:-XFORMERS}
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=${VLLM_ALLOW_LONG_MAX_MODEL_LEN:-1}

# 设置 CUDA 环境变量
export LD_LIBRARY_PATH=~/.local/lib:$LD_LIBRARY_PATH
export LIBRARY_PATH=~/.local/lib:${LIBRARY_PATH:-}
export CUDA_HOME=/usr/local/cuda-12.4
export PATH=$CUDA_HOME/bin:$PATH

# 使用标准的 Qwen3-14B 模型
MODEL=${MODEL:-Qwen/Qwen3-32B}
PORT=${PORT:-8000}
TP_SIZE=${TP_SIZE:-4}

echo "[vLLM] Serving model: $MODEL on port $PORT"
echo "[vLLM] Using attention backend: $VLLM_ATTENTION_BACKEND"
echo "[vLLM] Max model length: ${MAX_LEN:-40960}"
echo "[vLLM] LD_LIBRARY_PATH: $LD_LIBRARY_PATH"

exec conda run -n "$CONDA_ENV" python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" \
  --port "$PORT" \
  --tensor-parallel-size "$TP_SIZE" \
  --max-model-len "${MAX_LEN:-40960}" \
  --dtype "${DTYPE:-auto}" \
  --gpu-memory-utilization "$VLLM_WORKER_GPU_MEM_FRACTION" \
  --use-tqdm-on-load


