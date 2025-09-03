#!/usr/bin/env bash
set -euo pipefail

# DEBUG 开关（0/1）
DEBUG=${DEBUG:-0}

# 设置环境变量以显示下载进度
export HF_HUB_ENABLE_HF_TRANSFER=1
export HF_HUB_VERBOSITY=${HF_HUB_VERBOSITY:-info}
export HF_HUB_DISABLE_PROGRESS_BARS=${HF_HUB_DISABLE_PROGRESS_BARS:-0}
export PYTHONUNBUFFERED=1

# 设置 vLLM 日志环境变量
export VLLM_LOGGING_LEVEL=${VLLM_LOGGING_LEVEL:-INFO}
export VLLM_LOGGING_FORMAT="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
export VLLM_LOGGING_DATE_FORMAT="%Y-%m-%d %H:%M:%S"

# 根据 DEBUG 动态提高日志级别
if [ "$DEBUG" = "1" ]; then
    export VLLM_LOGGING_LEVEL=DEBUG
    export HF_HUB_VERBOSITY=debug
    UVICORN_LEVEL=debug
else
    UVICORN_LEVEL=${UVICORN_LEVEL:-info}
fi

CONDA_ENV=${CONDA_ENV:-llm}
export VLLM_WORKER_GPU_MEM_FRACTION=${VLLM_WORKER_GPU_MEM_FRACTION:-0.90}
export VLLM_ATTENTION_BACKEND=${VLLM_ATTENTION_BACKEND:-XFORMERS}
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=${VLLM_ALLOW_LONG_MAX_MODEL_LEN:-1}

# 设置 CUDA 环境变量
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-~/.local/lib}
export LIBRARY_PATH=${LIBRARY_PATH:-~/.local/lib}
export CUDA_HOME=/usr/local/cuda-12.4
export PATH=$CUDA_HOME/bin:$PATH

# 模型配置
MODEL=${MODEL:-Qwen/Qwen3-32B-AWQ}
PORT=${PORT:-8000}

# 根据模型自动调整配置
if [[ "$MODEL" == *"32B"* && "$MODEL" != *"AWQ"* ]]; then
    # 完整 32B 模型配置
    TP_SIZE=${TP_SIZE:-4}
    MAX_LEN=${MAX_LEN:-32768}
    MAX_NUM_SEQS=${MAX_NUM_SEQS:-1}
    KV_CACHE_DTYPE=${KV_CACHE_DTYPE:-fp8}
    DTYPE=${DTYPE:-bfloat16}
    TRUST_REMOTE_CODE=${TRUST_REMOTE_CODE:-1}
    echo "[vLLM] 使用完整 32B 模型配置：TP=4, max-len=32K, max-seqs=1, kv-cache=fp8"
else
    # AWQ 或其他模型配置
    TP_SIZE=${TP_SIZE:-2}
    MAX_LEN=${MAX_LEN:-40960}
    MAX_NUM_SEQS=${MAX_NUM_SEQS:-1}
    KV_CACHE_DTYPE=${KV_CACHE_DTYPE:-auto}
    DTYPE=${DTYPE:-auto}
    TRUST_REMOTE_CODE=${TRUST_REMOTE_CODE:-0}
    echo "[vLLM] 使用 AWQ/其他模型配置：TP=2, max-len=40K, max-seqs=1"
fi

echo "[vLLM] Serving model: $MODEL on port $PORT"
echo "[vLLM] Tensor parallel size: $TP_SIZE"
echo "[vLLM] Max model length: $MAX_LEN"
echo "[vLLM] Max sequences: $MAX_NUM_SEQS"
echo "[vLLM] KV cache dtype: $KV_CACHE_DTYPE"
echo "[vLLM] Using attention backend: $VLLM_ATTENTION_BACKEND"
echo "[vLLM] Logging level: $VLLM_LOGGING_LEVEL"
echo "[vLLM] LD_LIBRARY_PATH: $LD_LIBRARY_PATH"

# 构建 vLLM 命令
VLLM_CMD="conda run -n $CONDA_ENV python -u -m vllm.entrypoints.openai.api_server \
  --model $MODEL \
  --port $PORT \
  --tensor-parallel-size $TP_SIZE \
  --max-model-len $MAX_LEN \
  --max-num-seqs $MAX_NUM_SEQS \
  --dtype $DTYPE \
  --gpu-memory-utilization $VLLM_WORKER_GPU_MEM_FRACTION \
  --use-tqdm-on-load \
  --uvicorn-log-level $UVICORN_LEVEL \
  --enable-log-requests \
  --enable-log-outputs \
  --max-log-len 1000"

# 添加可选参数
if [[ "$KV_CACHE_DTYPE" != "auto" ]]; then
    VLLM_CMD="$VLLM_CMD --kv-cache-dtype $KV_CACHE_DTYPE"
fi

if [[ "$TRUST_REMOTE_CODE" == "1" ]]; then
    VLLM_CMD="$VLLM_CMD --trust-remote-code"
fi

if [ "$DEBUG" = "1" ]; then
    echo "[vLLM] DEBUG 模式开启"
fi

echo "[vLLM] 执行命令: $VLLM_CMD"
# 在伪TTY环境下直接执行，进度条会被外层脚本的日志捕获
exec bash -lc "$VLLM_CMD"


