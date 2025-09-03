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

# 模型配置
MODEL=${MODEL:-Qwen/Qwen3-32B}
PORT=${PORT:-8000}

# 根据模型自动调整配置
if [[ "$MODEL" == *"32B"* && "$MODEL" != *"AWQ"* ]]; then
    # 完整 32B 模型配置
    TP_SIZE=${TP_SIZE:-4}
    MAX_LEN=${MAX_LEN:-16384}
    MAX_NUM_SEQS=${MAX_NUM_SEQS:-8}
    KV_CACHE_DTYPE=${KV_CACHE_DTYPE:-fp8}
    DTYPE=${DTYPE:-bfloat16}
    TRUST_REMOTE_CODE=${TRUST_REMOTE_CODE:-1}
    echo "[vLLM] 使用完整 32B 模型配置：TP=4, max-len=16K, max-seqs=8, kv-cache=fp8"
else
    # AWQ 或其他模型配置
    TP_SIZE=${TP_SIZE:-3}
    MAX_LEN=${MAX_LEN:-40960}
    MAX_NUM_SEQS=${MAX_NUM_SEQS:-16}
    KV_CACHE_DTYPE=${KV_CACHE_DTYPE:-auto}
    DTYPE=${DTYPE:-auto}
    TRUST_REMOTE_CODE=${TRUST_REMOTE_CODE:-0}
    echo "[vLLM] 使用 AWQ/其他模型配置：TP=3, max-len=40K, max-seqs=16"
fi

echo "[vLLM] Serving model: $MODEL on port $PORT"
echo "[vLLM] Tensor parallel size: $TP_SIZE"
echo "[vLLM] Max model length: $MAX_LEN"
echo "[vLLM] Max sequences: $MAX_NUM_SEQS"
echo "[vLLM] KV cache dtype: $KV_CACHE_DTYPE"
echo "[vLLM] Using attention backend: $VLLM_ATTENTION_BACKEND"
echo "[vLLM] LD_LIBRARY_PATH: $LD_LIBRARY_PATH"

# 构建 vLLM 命令
VLLM_CMD="conda run -n $CONDA_ENV python -m vllm.entrypoints.openai.api_server \
  --model $MODEL \
  --port $PORT \
  --tensor-parallel-size $TP_SIZE \
  --max-model-len $MAX_LEN \
  --max-num-seqs $MAX_NUM_SEQS \
  --dtype $DTYPE \
  --gpu-memory-utilization $VLLM_WORKER_GPU_MEM_FRACTION \
  --use-tqdm-on-load"

# 添加可选参数
if [[ "$KV_CACHE_DTYPE" != "auto" ]]; then
    VLLM_CMD="$VLLM_CMD --kv-cache-dtype $KV_CACHE_DTYPE"
fi

if [[ "$TRUST_REMOTE_CODE" == "1" ]]; then
    VLLM_CMD="$VLLM_CMD --trust-remote-code"
fi

echo "[vLLM] 执行命令: $VLLM_CMD"
exec $VLLM_CMD


