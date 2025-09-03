## 项目日志（Journal）

> 用于记录按时间推进的进展、问题与结论，便于日后回溯与复用。

### 如何使用
- 每次推进时追加一条记录（日期 + 主题 + 结论/操作步骤/参考链接）。
- 重要资料（分析、参数、命令）保留专门文档，Journal 写“摘要 + 链接”。

---

## 合并自 HISTORY.md（完整记录）

# GenAI Playground - 项目历史记录

> 按时间顺序记录项目的学习过程、问题解决和成果总结

---

## 📅 2024-08-28 项目启动

### 🎯 项目目标
- 在 4× RTX 6000 服务器上系统体验 LLM 推理与微调
- 掌握核心工程栈（vLLM、HF 生态、LoRA/QLoRA、分布式/并行概念）
- 建立完整的本地机器翻译服务

### 🏗️ 初始规划
1. **vLLM 推理与服务** - 部署主流 7B 指令模型
2. **指令模型加载与推理** - transformers vs vLLM 对比
3. **QLoRA 微调最小闭环** - 小样本微调实验
4. **评估与部署** - OpenAI 兼容接口、并发、流式
5. **扩展功能** - VLM 与视觉生成/微调（可选）

### 📚 技术背景学习

#### vLLM 接口能力
- **OpenAI 兼容 API**: `/v1/chat/completions`，支持流式、并发、温度等参数
- **原生 Python**: `vllm.LLM` 类，直接加载模型进行推理
- **命令行**: `vllm.inference` 用于单次推理
- **批处理**: `vllm.batch` 用于批量推理

#### 为什么使用 OpenAI 兼容接口？
- 生态兼容：已有代码/工具无需修改
- 标准化：统一的参数格式和响应结构
- 部署便利：可直接替换 OpenAI 服务

#### 模型排行榜
- **Hugging Face Open LLM Leaderboard**: 开源模型性能对比
- **LMSYS Chatbot Arena**: 聊天机器人对战排名
- **当前最强 7B**: Qwen2.5-7B-Instruct、Llama-3.1-8B-Instruct

#### 硬件要求
- **推理 7B**: 单张 RTX 6000 即可（量化后）
- **训练 7B**: 
  - 全参数：8× A100 80GB+
  - LoRA/QLoRA：1-2张 RTX 6000
- **M1 Pro MacBook**: 可运行量化后的 7B（llama.cpp、MLX、ollama）

---

## 📅 2024-08-28 环境配置

### 🔧 初始环境状态
- **驱动/CUDA**: `NVIDIA-SMI 570.124.06`, CUDA runtime 12.8
- **GPU**: 4× RTX 6000 Ada, 49GB 显存
- **PyTorch**: 2.6.0+cu124 已安装

### 📋 环境配置步骤
1. 创建 `llm` conda 环境（Python 3.10）
2. 安装 PyTorch cu124、transformers/accelerate/datasets/peft/bitsandbytes
3. 安装 vLLM（与已装 PyTorch 匹配）

### 🎯 小测·第1组（vLLM 基础）
1. **问**: vLLM 相比 transformers.pipeline 推理的主要优势有哪些？适合哪些场景？
2. **问**: 在多 GPU 上，vLLM 的 `--tensor-parallel-size` 起什么作用？与显存/吞吐的关系？
3. **问**: KV Cache 是什么？为何能大幅提升长对话/长上下文推理吞吐？
4. **实操**: 启动 vLLM（7B 指令模型），用 `scripts/chat_vllm.py` 访问一次

> **作答区**（待完成）

---

## 📅 2024-09-01 问题解决与突破

### 🔧 问题1: CUDA 库链接问题
- **问题**: `cannot find -lcuda` 编译错误
- **解决**: 用户级符号链接 + 环境变量设置
- **经验**: 避免系统级修改，优先用户级解决方案

### 🔧 问题2: 服务管理优化
- **问题**: 需要前台运行 + 日志记录
- **解决**: 时间戳日志 + 管理脚本
- **经验**: 使用 `tee` 命令同时输出到控制台和文件

### 🔧 问题3: 文件结构整理
- **问题**: 文件位置混乱，路径错误
- **解决**: 按功能模块组织，统一路径规范
- **经验**: 始终在项目目录内创建文件

---

## 📅 2024-09-01 项目成果

### ✅ 成功部署的功能
1. **本地机器翻译服务**: 基于 vLLM + Qwen3-4B 的日语到中文翻译
2. **服务管理系统**: 完整的服务启动、停止、监控、日志管理
3. **问题解决记录**: 详细记录了所有遇到的问题和解决方案

### 📊 技术指标
- **模型**: Qwen/Qwen3-4B-Thinking-2507-FP8
- **硬件**: 4× RTX 6000 Ada (24GB VRAM)
- **性能**: 单卡运行，显存利用率 90%
- **响应时间**: API 响应正常，翻译质量良好

### 🏗️ 最终项目结构
```

#### check_vllm.py 用法与返回示例
```bash
# 运行
python scripts/check_vllm.py

# 典型输出（成功）
✅ vLLM 服务正在运行
📊 端口: 8000
📦 可用模型:
  - Qwen/Qwen3-32B-AWQ
    最大长度: 40960
    创建时间: <timestamp>

# 典型输出（失败）
❌ 无法连接到 vLLM 服务（请检查服务是否启动、端口是否正确）
```

#### .gitignore 清单（约定）
- 忽略生成/敏感内容：
  - `tasks/translation/data/input/*`
  - `tasks/translation/data/output/*`
  - `tasks/translation/logs/*`
  - 本地缓存/模型大文件应不入库（统一 HF_HOME 指向缓存目录）

#### vLLM 前台/后台运行建议
- 前台：首次加载新模型、观察下载/加载进度、调试参数。
- 后台：模型已缓存/稳定运行；用 `scripts/check_vllm.py` 做健康检查；日志写入 `logs/vllm-*.log`。

#### few-shot 与 token 控制小结
- 样例尽量风格一致、适度偏长但避免超上下文；必要时只选关键 few-shot。
- 成人内容翻译：优先 32B-AWQ；`max_tokens` 放宽（如 16000）；尽量减少额外解释性话语。

#### 译文质量常见问题与处置
- 语序异常：尝试更强模型或在 prompt 中强调语序；参考 samples 风格。
- 截断/合规：遇到内容政策导致截断时，换 32B-AWQ；或减少上下文/提高 `max_tokens`。
- 术语统一：在 prompt/术语表中明确术语对照（如 パイズリ→乳交）。

#### 日常检查清单
- GPU：`nvidia-smi`、`gpustat`（显存是否释放、是否 OOM）。
- 磁盘：`df -h`、`du -sh $HF_HOME`（空间是否足够、下载是否增长）。
- 服务：`python scripts/check_vllm.py`（模型名与上下文长度是否符合预期）。
- 日志：`logs/vllm-*.log`（是否有 OOM/404/连接错误）。
genai-playground/
├── Makefile                    # 主要构建文件
├── README.md                   # 项目说明
├── scripts/                    # 通用脚本目录
│   ├── manage_vllm.sh         # vLLM 服务管理脚本
│   ├── serve_vllm.sh          # vLLM 服务启动脚本
│   ├── test_gpu.py            # GPU 测试脚本
│   └── ...                    # 其他通用脚本
├── tasks/translation/          # 翻译任务目录
│   └── scripts/               # 翻译相关脚本
│       ├── test_translation.py # 翻译测试脚本
│       ├── serve_qwen3.sh     # Qwen3 服务启动脚本
│       └── translate_qwen3.py # Qwen3 翻译脚本
├── docs/                       # 项目文档目录
│   ├── HISTORY.md             # 项目历史记录（本文件）
│   ├── RUNBOOK.md             # 操作手册
│   └── SETUP_GUIDE.md         # 配置指南
└── logs/                       # 日志目录（自动创建）
```

### 🚀 使用指南
```bash
# 启动翻译服务
make vllm-start

# 查看服务状态
make vllm-status

# 测试翻译功能
make vllm-test

# 查看实时日志
make vllm-logs

# 停止服务
make vllm-stop
```

### 📝 翻译测试结果
- ✅ `こんにちは、世界。` → `你好，世界。`
- ✅ `今日は良い天気ですね。` → `今天天气真好。`
- ✅ `私は日本語を勉強しています。` → `我正在学习日语。`

### 📚 关键技术栈
- **vLLM**: 高性能 LLM 推理框架
- **Qwen3-4B**: 阿里云通义千问模型
- **CUDA 12.4**: NVIDIA GPU 计算平台
- **Python 3.10**: 编程语言环境

### ⚙️ 核心配置
```bash
# 服务配置
MODEL=Qwen/Qwen3-4B
TP_SIZE=1
MAX_LEN=40960
DTYPE=auto
GPU_MEMORY_UTILIZATION=0.90
ATTENTION_BACKEND=XFORMERS

# 环境变量
LD_LIBRARY_PATH=~/.local/lib:/usr/local/cuda-12.4/lib64
LIBRARY_PATH=~/.local/lib
CUDA_HOME=/usr/local/cuda-12.4
```

---

## 📅 2024-09-01 项目价值总结

### 🎯 技术价值
1. **完整的部署流程**: 从环境配置到服务运行的完整记录
2. **问题解决能力**: 详细的问题分析和解决方案
3. **可复现性**: 标准化的配置和脚本，便于复现

### 📚 学习价值
1. **CUDA 环境配置**: 深入理解 CUDA 库链接机制
2. **vLLM 使用**: 掌握高性能 LLM 推理框架
3. **服务管理**: 学习生产级服务部署和管理

### 🛠️ 实用价值
1. **本地翻译服务**: 避免在线服务的限制和隐私问题
2. **可扩展架构**: 便于添加其他模型和功能
3. **文档完善**: 详细的使用说明和问题解决记录

---

## 🔮 未来规划

### 🎯 可能的改进方向
1. **多模型支持**: 添加更多语言模型和翻译方向
2. **批量处理**: 支持文件批量翻译
3. **Web 界面**: 添加简单的 Web 界面
4. **性能优化**: 多卡并行，提高处理速度

### 🚀 技术升级
1. **模型升级**: 尝试更大的模型（如 Qwen3-14B）
2. **框架升级**: 跟进 vLLM 最新版本
3. **硬件优化**: 充分利用 4 卡并行能力

### 📋 学习计划
1. **vLLM 推理与服务** - 完成基础部署
2. **指令模型加载与推理** - transformers vs vLLM 对比
3. **QLoRA 微调最小闭环** - 小样本微调实验
4. **评估与部署** - OpenAI 兼容接口、并发、流式
5. **扩展功能** - VLM 与视觉生成/微调（可选）

---

**项目状态**: ✅ 基础功能完成  
**最后更新**: 2024-09-01  
**维护者**: lujiang
### 2025-09-02 学习与决策摘要

#### Qwen3-32B 模型分析（摘要）
- 结论：完整版 32B 推理显存需求超出 4×49GB，在线服务采用 `Qwen/Qwen3-32B-AWQ`。
- AWQ 量化在我们硬件上平衡质量与显存占用，默认使用 4 卡并行（TP=4）。
- 详细分析见：`docs/QWEN3_32B_ANALYSIS.md`。

#### vLLM 配置与下载可观测（摘要）
- 模型加载进度：`--use-tqdm-on-load`；下载进度由 HF Hub 控制，可通过 `HF_HUB_ENABLE_HF_TRANSFER=1`、`HUGGINGFACE_HUB_VERBOSITY=debug` 等环境变量增强日志。
- 统一缓存：`HF_HOME=/mnt/shengdata1/lujiang/hf_cache`。
- 详细说明见：`docs/VLLM_CONFIG.md`。

#### 故障记录：libcuda.so 链接问题
- 现象：启动/运行阶段出现 `libcuda.so` 相关链接错误或找不到库。
- 影响：vLLM/torch 相关组件无法正常加载，导致服务启动失败。
- 解决：
  - 使用用户级路径与环境变量修正库查找（如 `LD_LIBRARY_PATH`、`LIBRARY_PATH`、`CUDA_HOME`）。
  - 优先在用户空间放置符号链接，避免系统级更改。
  - 记录在服务启动脚本中以便复现（参考 `scripts/serve_vllm.sh`）。

---

### 2025-09-02 全日回顾（卡点与决策）

#### 主要目标
- 用 vLLM 提供本地翻译服务；将 `tasks/translation/data/japanese/input_1.txt` 翻译为中文；质量以 samples 为参考，保留“直白露骨”的风格。

#### 关键卡点与解决
- 服务状态误判：`manage_vllm.sh status` 因 PID 判断 Bug 误报，修正变量名后仍不稳 → 增加基于 `/v1/models` 的检查脚本 `scripts/check_vllm.py`，成为权威状态来源。
- 模型 404：脚本请求 `Qwen/Qwen3-14B`，但服务实际加载 `Qwen/Qwen3-4B` → 统一到服务默认 14B/32B（后续为 32B-AWQ），并在调用端显式传 `-m`。
- 输出不合规：输出文件夹（应为 `tasks/translation/data/output`）与输出内容（夹带原文与思考 `<think>`）不符合约定 → 通用脚本确保输出仅译文，完整 Prompt/Response 写入 `tasks/translation/logs/`。
- 下载/加载进度：vLLM 仅显示“加载”进度；下载由 HF Hub 负责 → 设置 `HF_HUB_ENABLE_HF_TRANSFER=1`、`HUGGINGFACE_HUB_VERBOSITY=debug`、`HF_HUB_DISABLE_PROGRESS_BARS=0`，必要时推荐先用 `huggingface-cli download` 预下并复用缓存。
- 32B 显存：完整版 32B 需要约 ≥256GB（估），4×49GB 不足；32B-AWQ 约 19GB 权重、总显存约 4×43~46GB 可跑 → 服务默认 32B-AWQ，完整 32B 仅离线评估。
- `count_tokens.py`：原版写死路径 → 改为 CLI：传入“文件或目录”，默认 `Qwen/Qwen3-32B` tokenizer，可 `-m` 覆盖。
- 脚本收敛：删除零散测试脚本，保留通用 `tasks/translation/scripts/test_translation.py`（带日志、参数可配）。
- 文档与结构：清理 docs，设定 Journal 为时间线；将长期参考文档指到 Journal；`AGENT_CONTEXT.md` 用作新会话 Prompt，不承载历史。

#### vLLM 配置要点（内联收录）
- 启动核心参数：`--tensor-parallel-size ${TP_SIZE}`（本机常用 4）、`--use-tqdm-on-load`、`--download-dir`（建议与 `HF_HOME` 指向同盘）。
- 环境变量建议：
  - `HF_HOME=/mnt/shengdata1/lujiang/hf_cache`
  - `HF_HUB_ENABLE_HF_TRANSFER=1`
  - `HUGGINGFACE_HUB_VERBOSITY=debug`
  - `HF_HUB_DISABLE_PROGRESS_BARS=0`
- 可靠健康检查：`GET http://localhost:8000/v1/models`，解析已加载模型名与上下文长度。

#### Qwen3-32B 分析（内联收录）
- Context window：40960 tokens（与是否 AWQ 无关）。
- 显存与取舍：
  - 完整 32B：在本机 4×49GB 条件下易 OOM（日志已证实）。
  - 32B-AWQ：权重约 19GB，服务端总显存约 170~190GB（含 KV/激活/碎片），稳定运行。
- 质量与行为：32B 基座在成人内容上可能触发截断/合规策略，32B-AWQ 实测更稳定输出完整译文。

#### 今日决定
- 服务默认模型：`Qwen/Qwen3-32B-AWQ` + `TP_SIZE=4`。
- 输出与日志：输出文件仅译文；日志统一到 `tasks/translation/logs/`，含完整 Prompt/Response 与元信息。
- 文档体例：以 `docs/JOURNAL.md` 为“技术博客式”时间线，详档按需保留独立文件或直接内联至 Journal。

#### 待办
- 提供完整 32B 的 `huggingface-cli` 下载命令（放 Journal“下载策略”条目）。
- 评估 Sakura-13B-Galgame 模型（下载→服务→对比）。
- example_1 使用 32B-AWQ 跑通并落盘（完整日志）。

---

### 并入：vLLM 服务配置说明（原 docs/VLLM_CONFIG.md 全文）

# vLLM 服务配置说明

## 模型加载进度显示

vLLM 提供了 `--use-tqdm-on-load` 参数来显示模型加载进度。当启动新模型或首次下载模型时，会在日志中显示进度条。

### 当前配置

在 `scripts/serve_vllm.sh` 中已启用：
```bash
--use-tqdm-on-load
```

### 相关参数

- `--use-tqdm-on-load`: 启用加载进度条显示（默认：True）
- `--download-dir`: 指定模型下载目录
- `--load-format`: 指定模型加载格式

### 日志查看

启动服务后，可以通过以下方式查看加载进度：

```bash
# 实时查看日志
./scripts/manage_vllm.sh logs

# 查看最新日志
tail -f logs/latest.log
```

### 注意事项

1. 如果模型已经缓存，不会显示下载进度
2. 首次启动大模型时，会显示详细的加载进度
3. 进度信息会记录在日志文件中
4. 建议在启动大模型时使用前台模式，以便观察进度

### 示例日志输出

```
[vLLM] Loading model weights...
100%|██████████| 100/100 [00:30<00:00,  3.33it/s]
[vLLM] Model loaded successfully
[vLLM] Serving model: Qwen/Qwen3-14B on port 8000
```

---

### 并入：Qwen3-32B 模型分析（原 docs/QWEN3_32B_ANALYSIS.md 全文）

# Qwen3-32B 模型分析报告

## 1. 模型下载进度查看

### 实时查看下载进度
```bash
# 查看vLLM启动日志（包含下载进度）
./scripts/manage_vllm.sh logs

# 实时查看日志
tail -f logs/vllm-*.log

# 查看HuggingFace缓存下载进度
ls -la /mnt/shengdata1/lujiang/hf_cache/hub/models--Qwen--Qwen3-32B/
```

### 当前配置
- 已启用 `--use-tqdm-on-load` 参数
- 下载进度会显示在vLLM启动日志中

## 2. 模型存储位置和空间占用

### 存储位置
- **HuggingFace缓存**: `/mnt/shengdata1/lujiang/hf_cache/hub/models--Qwen--Qwen3-32B/`
- **环境变量**: `HF_HOME=/mnt/shengdata1/lujiang/hf_cache`

### 空间占用对比
| 模型 | 大小 | 状态 |
|------|------|------|
| Qwen3-4B | 7.6G | 已下载 |
| Qwen3-14B | 28G | 已下载 |
| Qwen3-32B | 16M | 仅元数据，未下载完整模型 |

### 32B模型预估空间
- **原始模型**: ~60-70GB
- **量化版本**: ~15-20GB (AWQ/GGUF)

## 3. GPU显存分析

### 当前GPU配置
- **GPU数量**: 4张 RTX 6000 Ada Generation
- **单卡显存**: 49GB
- **总显存**: 196GB

### 32B模型显存需求
- **原始32B模型**: ~64GB (需要2-3张卡)
- **量化32B模型**: ~16-20GB (单卡可运行)

### 显存清理
```bash
# 清理vLLM进程
pkill -f vllm

# 查看显存使用
gpustat
```

## 4. Qwen3-32B 分支分析

### 可用分支
| 分支 | 用途 | 大小 | 适用场景 |
|------|------|------|----------|
| `Qwen/Qwen3-32B` | 原始模型 | ~60-70GB | 最高质量，需要大量显存 |
| `Qwen/Qwen3-32B-AWQ` | AWQ量化 | ~15-20GB | 平衡质量和效率 |
| `Qwen/Qwen3-32B-FP8` | FP8量化 | ~30-35GB | 高质量量化 |
| `Qwen/Qwen3-32B-GGUF` | GGUF量化 | ~15-20GB | 通用量化格式 |

### 推荐选择
**建议使用 `Qwen/Qwen3-32B-AWQ`**：
- 显存需求适中 (~20GB)
- 质量损失最小
- vLLM原生支持

## 5. Context长度分析

### 模型配置
- **最大序列长度**: 40,960 tokens
- **词汇表大小**: 151,936
- **层数**: 64
- **隐藏维度**: 5,120
- **注意力头数**: 64

### 当前任务分析
- **输入文件**: ~9,000字符 ≈ 3,000 tokens
- **示例文本**: ~1,000字符 ≈ 300 tokens
- **总需求**: ~4,000 tokens
- **剩余空间**: 36,000 tokens (充足)

## 6. Few-shot策略优化

### 当前1-shot策略
```python
# 当前使用example_2_2作为示例
example_input = "明日、このOカップのブラジャーで包まれた胸でパイズリしてあげる"
example_output = "明天我会用这O罩杯的胸罩包裹着的胸来给你做乳交"
```

### 优化建议

#### 1. 增加更多示例
```python
examples = [
    ("明日、このOカップのブラジャーで包まれた胸でパイズリしてあげる", 
     "明天我会用这O罩杯的胸罩包裹着的胸来给你做乳交"),
    ("彼女の大きな胸で僕を包み込んでくれた", 
     "她用她的大胸把我包裹起来"),
    # 添加更多语序相关的示例
]
```

#### 2. 明确语序指导
```python
prompt_template = """
翻译要求：
1. 保持自然的语序，不要生硬翻译
2. 日语"で"表示工具/手段时，翻译为"用...来..."
3. 保持原文的逻辑顺序
4. 参考示例的翻译风格
"""
```

#### 3. 使用更长的上下文
- 32B模型context更长，可以使用更多示例
- 建议使用3-5个高质量示例
- 包含不同语序模式的示例

## 7. 实施建议

### 立即行动
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

### 长期优化
1. **收集更多示例**：从samples中提取更多语序正确的示例
2. **A/B测试**：对比不同示例组合的效果
3. **质量评估**：建立自动化的质量评估机制

### 2025-09-02 下载策略（命令级）

#### 统一缓存与网络加速
- 建议持久缓存目录：`HF_HOME=/mnt/shengdata1/lujiang/hf_cache`
- 建议环境：
```bash
export HF_HOME=/mnt/shengdata1/lujiang/hf_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
export HUGGINGFACE_HUB_VERBOSITY=debug
export HF_HUB_DISABLE_PROGRESS_BARS=0
```

#### 预下载完整 32B（基座）
```bash
huggingface-cli download Qwen/Qwen3-32B \
  --local-dir /mnt/shengdata1/lujiang/hf_cache/models--Qwen--Qwen3-32B \
  --local-dir-use-symlinks False \
  --resume-download
```

#### 预下载 32B-AWQ（服务默认）
```bash
huggingface-cli download Qwen/Qwen3-32B-AWQ \
  --local-dir /mnt/shengdata1/lujiang/hf_cache/models--Qwen--Qwen3-32B-AWQ \
  --local-dir-use-symlinks False \
  --resume-download
```

说明：
- 也可改用 `vllm serve <repo-or-local-path> --download-dir /mnt/shengdata1/lujiang/hf_cache`，两者共用缓存。
- 进度条与吞吐日志依赖 `hf_transfer` 与 `HUGGINGFACE_HUB_VERBOSITY=debug`。

---

### 2025-09-02 故障复现：libcuda.so 链接

现象：
- 报错 `cannot find -lcuda` 或运行时报找不到 `libcuda.so` / `libcuda.so.*`。

定位步骤：
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

结论与建议：
- 优先使用“用户级”路径与环境变量修复，避免系统级改动；将关键变量写入启动脚本（如 `scripts/serve_vllm.sh`）。
- 如使用 conda 环境，确保在同一 shell 中 `conda activate llm` 后再启动服务与验证。

---

### 2025-09-02 其他问题回顾

- `manage_vllm.sh status` 误报：PID 判断变量名错误导致，总是显示未运行；已修复，并以 `/v1/models` 为最终权威来源（`scripts/check_vllm.py`）。
- 模型名不一致：服务与客户端请求不一致导致 `404 The model ... does not exist`；统一通过 `-m` 显式传模型，并确认服务日志中的加载模型名。
- 输出内容不合规：译文输出夹带原文与 `<think>` 思考；改为输出仅保留译文，完整 Prompt/Response 写入日志（`tasks/translation/logs/`）。
- 32B OOM：尝试加载完整 32B 时报 CUDA OOM；确认 32B-AWQ 方案可稳定运行（TP=4），服务默认切换为 AWQ。
- Makefile 目标过期：仍指向已删除的 `translate_stable.py`/`translate_exp.py`；已改为通用 `test_translation.py`。
- 文档误删与恢复：清理 docs 时误删；现采用“Journal 加详档”的博客式结构并恢复关键文档。
- `count_tokens.py`：改为 CLI 传参，支持文件或目录统计，默认 Qwen3 tokenizer，可通过 `-m` 指定。
- 默认日志文件：通用翻译脚本默认自动生成时间戳日志路径（无需手动指定）。

#### Makefile 记录（当前 translate 目标）
```make
translate:
	@echo "📝 执行翻译任务..."
	$(PY) tasks/translation/scripts/test_translation.py --input tasks/translation/data/input/input_1.txt --output tasks/translation/data/output/translated.txt --model Qwen/Qwen3-32B-AWQ
```

#### serve_vllm.sh 记录（关键参数）
```bash
export HF_HUB_ENABLE_HF_TRANSFER=1
export HUGGINGFACE_HUB_VERBOSITY=debug
export HF_HUB_DISABLE_PROGRESS_BARS=0

export VLLM_WORKER_GPU_MEM_FRACTION=0.90
export VLLM_ATTENTION_BACKEND=XFORMERS
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1

export LD_LIBRARY_PATH=~/.local/lib:$LD_LIBRARY_PATH
export LIBRARY_PATH=~/.local/lib:${LIBRARY_PATH:-}
export CUDA_HOME=/usr/local/cuda-12.4
export PATH=$CUDA_HOME/bin:$PATH

MODEL=${MODEL:-Qwen/Qwen3-32B}
PORT=${PORT:-8000}
TP_SIZE=${TP_SIZE:-4}

python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" \
  --port "$PORT" \
  --tensor-parallel-size "$TP_SIZE" \
  --max-model-len "${MAX_LEN:-40960}" \
  --dtype "${DTYPE:-auto}" \
  --gpu-memory-utilization "$VLLM_WORKER_GPU_MEM_FRACTION" \
  --use-tqdm-on-load
```

### 维护约定
- Journal 是唯一权威的时间线；其他分析文档/配置文档作为“可链接参考”。
- 每当出现：
  1) 新的工程决策（换模型/参数/结构）；
  2) 新的故障及定位过程；
  3) 新的最佳实践或脚本；
  应在此追加条目并附上参考链接。

---

### 2025-09-02 翻译流水线优化与测试

#### 翻译脚本重构与优化
- **代码模块化**：将 `translate_pixiv_v1.py` 中的工具函数提取到 `tasks/translation/scripts/utils/` 模块，提高代码可维护性
- **文件管理优化**：删除冗余的 `.meta.json` 文件（69个），减少总文件数；重命名系列文章文件为 `{series_id}_{novel_id}.txt` 格式（32个文件）
- **日志系统改进**：在命令行输出中显示对应的日志文件路径，便于调试和监控

#### 翻译质量测试
- **测试文章**：使用系列文章 `1256365_12430834.txt` 和独立文章 `12670318.txt` 进行翻译质量验证
- **参数优化**：发现 `temperature=0.0` 和 `frequency-penalty=0.0` 的组合能提供最稳定的翻译输出
- **质量检查**：`looks_bad_output` 函数成功检测到异常输出模式，确保翻译质量

#### 关键技术改进
- **动态token计算**：根据输入长度动态计算 `max_tokens`，避免超出模型上下文限制
- **输出清理**：自动移除模型思考部分（`<think>...</think>`），保持输出纯净
- **错误处理**：增强重试机制和错误检测，提高翻译成功率

#### vLLM 配置优化
- **AWQ 模型 TP 配置**：发现 AWQ 模型需要 TP 能整除某个数，将默认 TP_SIZE 从 3 改为 2
- **完整 32B 模型配置**：支持 TP=4、kv-cache-dtype=fp8、trust-remote-code 等关键参数
- **自动配置切换**：根据模型名自动选择最优配置（32B vs AWQ）

#### 文件结构优化
```
tasks/translation/data/pixiv/50235390/
├── index.json                    # 文章索引和元数据
├── 1256365_12430834.txt          # 系列文章（重命名后）
├── 1256365_12430834_zh.txt       # 翻译输出
├── 12670318.txt                  # 独立文章
├── 12670318_zh.txt               # 翻译输出
└── ...                           # 其他文章
```

#### 翻译性能指标
- **处理速度**：单篇文章翻译时间约30-180秒（取决于文章长度）
- **输出质量**：完整保留原文结构和语义，专业术语翻译准确
- **稳定性**：通过质量检查的文章翻译成功率100%

#### 下一步计划
- 批量翻译剩余文章（约67篇）
- 考虑添加双语对照输出格式
- 优化长文章的翻译策略（分块+重叠）

---

**项目状态**: ✅ 翻译流水线稳定运行  
**最后更新**: 2025-09-02  
**维护者**: lujiang

---

### 2025-09-02 vLLM 启动与日志可观测性改进（tmux/script + 前台模式）

- 背景：后台运行时没有 TTY，tqdm 自动关闭，日志中无进度条；需要在“可观测性”和“可后台运行”之间取得平衡。
- 解决方案：
  - 前台模式：`manage_vllm.sh start` 使用 `script -q -f -c` 分配伪 TTY（tqdm 认为有终端），同时落盘日志；Make 目标：`vllm-start`、`vllm-start-32b`。
  - 后台模式：`manage_vllm.sh start-bg` 使用 `tmux + script` 运行，记录会话名到 `logs/vllm.pid`，可 `tmux attach -t vllm` 实时查看；Make 目标：`vllm-start-bg`、`vllm-start-32b-bg`。
  - 统一将 stderr 合流到日志；`serve_vllm.sh` 采用 `python -u` 或 `PYTHONUNBUFFERED=1` 以避免缓冲吞掉刷新。
- 其他改动：
  - `serve_vllm.sh` 增加 DEBUG 开关：`DEBUG=1` 时提升 vLLM/HF 的日志等级（`VLLM_LOGGING_LEVEL=DEBUG`, `HF_HUB_VERBOSITY=debug`）。
  - 32B 默认 `max-num-seqs=1` 保守并发，提高稳定性；32B `max-model-len=32K`，AWQ `max-model-len=40K`。
  - 加入 `--uvicorn-log-level`、`--enable-log-requests`、`--enable-log-outputs`、`--max-log-len`，便于请求级日志排查。
- Makefile：
  - 前台：`vllm-start`（AWQ）、`vllm-start-32b`（32B）。
  - 后台：`vllm-start-bg`、`vllm-start-32b-bg`。
  - Debug 便捷目标：`vllm-start-debug`、`vllm-start-bg-debug`（设置 `DEBUG=1`）。

### 2025-09-02 翻译脚本增强（Pixiv 批量）

- `translate_pixiv_v1.py`：
  - 新增 `--preface-file`，把翻译指令模板移出代码，便于敏感内容管理；
  - 新增 `--max-context-length`，未指定时基于模型名自动推断（32B=32768；AWQ=40960）；
  - 动态计算 `max_tokens`，避免超过上下文；
  - 日志去重：固定前缀（preface/few-shot）只保留一次，分块逐条记录“原文+翻译”；日志名包含输入文件名，便于检索。


---

## 📋 TODO List 整理

### ✅ 已完成的任务

#### 基础架构
- ✅ ~~vLLM 服务部署与配置~~
- ✅ ~~CUDA 环境配置与问题解决~~
- ✅ ~~服务管理脚本（启动、停止、状态检查）~~
- ✅ ~~OpenAI 兼容 API 接口~~
- ✅ ~~Qwen3-32B-AWQ 模型加载与测试~~

#### 翻译流水线
- ✅ ~~Pixiv 小说批量下载脚本~~
- ✅ ~~批量翻译脚本（支持全文和分块模式）~~
- ✅ ~~文件重命名脚本（系列文章）~~
- ✅ ~~工具函数模块化~~
- ✅ ~~术语对照表注入~~
- ✅ ~~质量检查机制（looks_bad_output）~~
- ✅ ~~日志系统完善~~
- ✅ ~~动态token计算~~
- ✅ ~~输出清理（移除思考部分）~~

#### 文件管理
- ✅ ~~删除冗余 .meta.json 文件~~
- ✅ ~~.gitignore 配置（忽略敏感数据）~~
- ✅ ~~代码提交与版本管理~~

#### 文档
- ✅ ~~Journal.md 更新~~
- ✅ ~~技术文档整理~~
- ✅ ~~问题解决记录~~

### 🔄 进行中的任务

#### 翻译质量优化
- 🔄 批量翻译剩余文章（约67篇）
- 🔄 长文章翻译策略优化（分块+重叠）

### 📝 待办任务

#### 短期任务（1-2周）
- [ ] **日志系统改进**：修改日志系统，每篇文章只生成一篇日志，而不是每次请求生成一篇
- [ ] **批量翻译**：完成剩余67篇文章的翻译
- [ ] **翻译质量评估**：建立自动化的翻译质量评估机制
- [ ] **错误处理增强**：改进重试机制，处理更多异常情况

#### 中期任务（1个月）
- [ ] **双语对照输出**：添加 `bilingual.md` 双语对齐导出功能
- [ ] **EPUB 生成**：实现 EPUB 格式输出
- [ ] **跨块一致性**：对分块译文做跨块一致性润色（术语/人名/称谓统一）
- [ ] **并发优化**：将分块请求改为并发队列（控制 QPS），提升吞吐

#### 长期任务（2-3个月）
- [ ] **模型评估**：评估 Sakura-13B-Galgame 模型（下载→服务→对比）
- [ ] **完整32B模型**：提供完整 32B 的 `huggingface-cli` 下载命令
- [ ] **多模型支持**：添加更多语言模型和翻译方向
- [ ] **Web 界面**：添加简单的 Web 界面
- [ ] **性能优化**：多卡并行，提高处理速度

#### 技术改进
- [ ] **QLoRA 微调**：小样本微调实验
- [ ] **VLM 支持**：视觉生成/微调功能
- [ ] **分布式训练**：掌握分布式/并行概念
- [ ] **模型升级**：尝试更大的模型（如 Qwen3-14B）

#### 文档完善
- [ ] **API 文档**：完善翻译 API 文档
- [ ] **部署指南**：编写完整的部署指南
- [ ] **故障排除**：整理常见问题和解决方案
- [ ] **性能基准**：建立性能基准测试

### 🎯 优先级排序

#### 高优先级（立即执行）
1. 批量翻译剩余文章
2. 日志系统改进（每篇文章一篇日志）
3. 翻译质量评估机制

#### 中优先级（近期执行）
1. 双语对照输出
2. EPUB 生成
3. 并发优化

#### 低优先级（长期规划）
1. Web 界面开发
2. 多模型支持
3. QLoRA 微调实验

---

**最后更新**: 2025-09-02  
**维护者**: lujiang


