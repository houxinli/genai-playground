#!/usr/bin/env bash
# 环境设置脚本 - 设置 vLLM 运行所需的所有环境变量

set -euo pipefail

echo "🚀 设置 vLLM 运行环境..."

# 1. CUDA 库路径设置
export LD_LIBRARY_PATH=~/.local/lib:$LD_LIBRARY_PATH
export LIBRARY_PATH=~/.local/lib:$LIBRARY_PATH

# 2. vLLM 配置
export VLLM_ATTENTION_BACKEND=XFORMERS
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export VLLM_WORKER_GPU_MEM_FRACTION=0.90

# 3. 显示当前设置
echo "✅ 环境变量设置完成："
echo "   LD_LIBRARY_PATH: $LD_LIBRARY_PATH"
echo "   LIBRARY_PATH: $LIBRARY_PATH"
echo "   VLLM_ATTENTION_BACKEND: $VLLM_ATTENTION_BACKEND"
echo "   VLLM_ALLOW_LONG_MAX_MODEL_LEN: $VLLM_ALLOW_LONG_MAX_MODEL_LEN"
echo "   VLLM_WORKER_GPU_MEM_FRACTION: $VLLM_WORKER_GPU_MEM_FRACTION"

# 4. 验证 CUDA 库
if [ -L ~/.local/lib/libcuda.so ]; then
    echo "✅ CUDA 库链接正常: ~/.local/lib/libcuda.so"
else
    echo "❌ CUDA 库链接缺失，正在创建..."
    mkdir -p ~/.local/lib
    ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 ~/.local/lib/libcuda.so
    echo "✅ CUDA 库链接已创建"
fi

echo "🎯 环境设置完成！现在可以运行 vLLM 服务了。"
