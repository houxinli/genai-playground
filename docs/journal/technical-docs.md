# 技术文档补充

> 这些内容来自大 journal，包含详细的技术配置和分析

## vLLM 服务配置说明

### 模型加载进度显示

vLLM 提供了 `--use-tqdm-on-load` 参数来显示模型加载进度。当启动新模型或首次下载模型时，会在日志中显示进度条。

#### 当前配置

在 `scripts/serve_vllm.sh` 中已启用：
```bash
--use-tqdm-on-load
```

#### 相关参数

- `--use-tqdm-on-load`: 启用加载进度条显示（默认：True）
- `--download-dir`: 指定模型下载目录
- `--load-format`: 指定模型加载格式

#### 日志查看

启动服务后，可以通过以下方式查看加载进度：

```bash
# 实时查看日志
./scripts/manage_vllm.sh logs

# 查看最新日志
tail -f logs/latest.log
```

#### 注意事项

1. 如果模型已经缓存，不会显示下载进度
2. 首次启动大模型时，会显示详细的加载进度
3. 进度信息会记录在日志文件中
4. 建议在启动大模型时使用前台模式，以便观察进度

#### 示例日志输出

```
[vLLM] Loading model weights...
100%|██████████| 100/100 [00:30<00:00,  3.33it/s]
[vLLM] Model loaded successfully
[vLLM] Serving model: Qwen/Qwen3-14B on port 8000
```

## Qwen3-32B 模型分析报告

### 1. 模型下载进度查看

#### 实时查看下载进度
```bash
# 查看vLLM启动日志（包含下载进度）
./scripts/manage_vllm.sh logs

# 实时查看日志
tail -f logs/vllm-*.log

# 查看HuggingFace缓存下载进度
ls -la $HF_HOME/hub/models--Qwen--Qwen3-32B/
```

#### 当前配置
- 已启用 `--use-tqdm-on-load` 参数
- 下载进度会显示在vLLM启动日志中

### 2. 模型存储位置和空间占用

#### 存储位置
- **HuggingFace缓存**: `$HF_HOME/hub/models--Qwen--Qwen3-32B/`
- **环境变量**: `HF_HOME=/path/to/your/hf_cache`

#### 空间占用对比
| 模型 | 大小 | 状态 |
|------|------|------|
| Qwen3-4B | 7.6G | 已下载 |
| Qwen3-14B | 28G | 已下载 |
| Qwen3-32B | 16M | 仅元数据，未下载完整模型 |

#### 32B模型预估空间
- **原始模型**: ~60-70GB
- **量化版本**: ~15-20GB (AWQ/GGUF)

### 3. GPU显存分析

#### 当前GPU配置
- **GPU数量**: 4张 RTX 6000 Ada Generation
- **单卡显存**: 49GB
- **总显存**: 196GB

#### 32B模型显存需求
- **原始32B模型**: ~64GB (需要2-3张卡)
- **量化32B模型**: ~16-20GB (单卡可运行)

#### 显存清理
```bash
# 清理vLLM进程
pkill -f vllm

# 查看显存使用
gpustat
```

### 4. Qwen3-32B 分支分析

#### 可用分支
| 分支 | 用途 | 大小 | 适用场景 |
|------|------|------|----------|
| `Qwen/Qwen3-32B` | 原始模型 | ~60-70GB | 最高质量，需要大量显存 |
| `Qwen/Qwen3-32B-AWQ` | AWQ量化 | ~15-20GB | 平衡质量和效率 |
| `Qwen/Qwen3-32B-FP8` | FP8量化 | ~30-35GB | 高质量量化 |
| `Qwen/Qwen3-32B-GGUF` | GGUF量化 | ~15-20GB | 通用量化格式 |

#### 推荐选择
**建议使用 `Qwen/Qwen3-32B-AWQ`**：
- 显存需求适中 (~20GB)
- 质量损失最小
- vLLM原生支持

### 5. Context长度分析

#### 模型配置
- **最大序列长度**: 40,960 tokens
- **词汇表大小**: 151,936
- **层数**: 64
- **隐藏维度**: 5,120
- **注意力头数**: 64

#### 当前任务分析
- **输入文件**: ~9,000字符 ≈ 3,000 tokens
- **示例文本**: ~1,000字符 ≈ 300 tokens
- **总需求**: ~4,000 tokens
- **剩余空间**: 36,000 tokens (充足)

### 6. Few-shot策略优化

#### 优化建议

##### 1. 增加更多示例
- 使用多个高质量的翻译示例
- 包含不同语序模式的示例
- 确保示例风格一致

##### 2. 明确语序指导
- 保持自然的语序，不要生硬翻译
- 日语"で"表示工具/手段时，翻译为"用...来..."
- 保持原文的逻辑顺序
- 参考示例的翻译风格

##### 3. 使用更长的上下文
- 32B模型context更长，可以使用更多示例
- 建议使用3-5个高质量示例
- 包含不同语序模式的示例

### 7. 实施建议

#### 立即行动
1. **下载AWQ量化版本**：
   ```bash
   MODEL=Qwen/Qwen3-32B-AWQ make vllm-start
   ```

2. **优化prompt**：
   - 增加语序相关的示例
   - 明确语序指导规则
   - 使用更多高质量示例

3. **测试翻译质量**：
   ```bash
   python tasks/translation/scripts/test_quality_comparison.py
   ```

#### 长期优化
1. **收集更多示例**：从samples中提取更多语序正确的示例
2. **A/B测试**：对比不同示例组合的效果
3. **质量评估**：建立自动化的质量评估机制

## 下载策略（命令级）

### 统一缓存与网络加速
- 建议持久缓存目录：`HF_HOME=/path/to/your/hf_cache`
- 建议环境：
```bash
export HF_HOME=/path/to/your/hf_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
export HUGGINGFACE_HUB_VERBOSITY=debug
export HF_HUB_DISABLE_PROGRESS_BARS=0
```

### 预下载完整 32B（基座）
```bash
huggingface-cli download Qwen/Qwen3-32B \
  --local-dir $HF_HOME/models--Qwen--Qwen3-32B \
  --local-dir-use-symlinks False \
  --resume-download
```

### 预下载 32B-AWQ（服务默认）
```bash
huggingface-cli download Qwen/Qwen3-32B-AWQ \
  --local-dir $HF_HOME/models--Qwen--Qwen3-32B-AWQ \
  --local-dir-use-symlinks False \
  --resume-download
```

### 说明
- 也可改用 `vllm serve <repo-or-local-path> --download-dir $HF_HOME`，两者共用缓存
- 进度条与吞吐日志依赖 `hf_transfer` 与 `HUGGINGFACE_HUB_VERBOSITY=debug`

## 故障复现：libcuda.so 链接

### 现象
- 报错 `cannot find -lcuda` 或运行时报找不到 `libcuda.so` / `libcuda.so.*`

### 定位步骤
```bash
# 1) 确认 nvidia-smi 可用
nvidia-smi

# 2) 查询系统 CUDA 路径（如 /usr/local/cuda-*）
ls -l /usr/local | grep cuda || true

# 3) 查询 libcuda.so 所在（通常在 /usr/lib/x86_64-linux-gnu/ 或 驱动路径）
ldconfig -p | grep libcuda || true

# 4) 临时修复（当前会话）
export CUDA_HOME=/usr/local/cuda-12.4
export LD_LIBRARY_PATH=$CUDA_HOME/lib64:${LD_LIBRARY_PATH}
export LIBRARY_PATH=$CUDA_HOME/lib64:${LIBRARY_PATH}

# 5) 若仍缺失，创建用户级符号链接到驱动提供的 libcuda.so
mkdir -p ~/.local/lib
ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so ~/.local/lib/libcuda.so || true
export LD_LIBRARY_PATH=~/.local/lib:${LD_LIBRARY_PATH}

# 6) 验证 Python 能加载 CUDA
python - <<'PY'
import torch
print('torch.cuda.is_available =', torch.cuda.is_available())
print('torch.version.cuda =', getattr(torch.version, 'cuda', None))
PY
```

### 结论与建议
- 优先使用"用户级"路径与环境变量修复，避免系统级改动
- 将关键变量写入启动脚本（如 `scripts/serve_vllm.sh`）
- 如使用 conda 环境，确保在同一 shell 中 `conda activate llm` 后再启动服务与验证
