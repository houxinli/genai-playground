# 环境配置说明

## 系统要求

- **操作系统**: Ubuntu 22.04.4 LTS
- **GPU**: 4x RTX 6000 Ada Generation
- **CUDA**: 12.8 (driver), 12.4 (PyTorch)
- **Python**: 3.10.18 / 3.11.7
- **Conda**: 24.1.2

## 环境变量说明

### CUDA 相关
```bash
# 解决 libcuda.so 链接问题
export LD_LIBRARY_PATH=~/.local/lib:$LD_LIBRARY_PATH
export LIBRARY_PATH=~/.local/lib:$LIBRARY_PATH
```

### vLLM 配置
```bash
# 注意力后端：使用 XFORMERS 避免编译问题
export VLLM_ATTENTION_BACKEND=XFORMERS

# 允许长序列：覆盖模型默认最大长度
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1

# GPU 显存使用率：90%，为系统预留 10%
export VLLM_WORKER_GPU_MEM_FRACTION=0.90
```

## 快速设置

### 1. 激活环境
```bash
conda activate llm
```

### 2. 设置环境变量
```bash
source scripts/env_setup.sh
```

### 3. 启动服务
```bash
./scripts/serve_vllm.sh
```

## 环境文件

- `environment-llm.yml`: Conda 环境导出文件
- `requirements-llm.txt`: Pip 依赖列表
- `scripts/env_setup.sh`: 环境设置脚本

## 常见问题

### CUDA 链接错误
```bash
/usr/bin/ld: cannot find -lcuda: No such file or directory
```
**解决方案**: 运行 `source scripts/env_setup.sh`

### 注意力后端错误
```bash
VLLM_ATTENTION_BACKEND=FLASHINFER is not supported
```
**解决方案**: 使用 `XFORMERS` 后端

### 模型长度错误
```bash
max_model_len is greater than the derived max_model_len
```
**解决方案**: 设置 `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1`

## 性能调优

### GPU 显存使用率
- **0.90 (推荐)**: 平衡性能和稳定性
- **0.95**: 更高性能，但可能不稳定
- **0.80**: 更稳定，但性能略低

### 注意力后端选择
- **XFORMERS**: 兼容性好，性能稳定
- **FLASH_ATTN**: 性能更好，但需要特殊编译
- **TORCH_SDPA**: 原生 PyTorch，兼容性最好
