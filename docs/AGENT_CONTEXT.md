# GenAI Playground — Agent 稳定背景

> 这份文档只保留"长半衰期"的环境、约定与排障经验。
>
> - 开发规范：见仓库根 [`../AGENTS.md`](../AGENTS.md)
> - 当前状态：见 [`PROJECT_STATUS.md`](PROJECT_STATUS.md)
> - 历史决策：见 [`journal/README.md`](journal/README.md)
> - 翻译执行手册：见 [`../tasks/translation/README.md`](../tasks/translation/README.md)

## 项目概览

仓库包含两个子项目：

1. **翻译流水线** (`tasks/translation/`) — 当前主战场。
   日语 → 中文，下载 → 翻译 → 修复/清理 → 打包。
   核心栈：vLLM / Apple MLX / OpenRouter，统一走 OpenAI 兼容接口。

2. **Sunday Movies** (`tasks/sunday-movies/`) — 维护模式。
   影院档期与多源评分（Fandango / 豆瓣 / IMDb）。

详细目录边界在 [`../AGENTS.md`](../AGENTS.md) §1。

## 运行环境

### Conda

```bash
conda activate llm
# 或
conda run -n llm <command>
```

环境定义：`environment-llm.yml`（Linux + CUDA）、`environment-llm-mac.yml`（Apple Silicon + MLX）。

### CUDA / vLLM（Linux 服务器）

```bash
# 解决 ld 找不到 libcuda 的链接错误
mkdir -p ~/.local/lib
ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so ~/.local/lib/libcuda.so

export LD_LIBRARY_PATH=~/.local/lib:$LD_LIBRARY_PATH
export LIBRARY_PATH=~/.local/lib:${LIBRARY_PATH:-}
export CUDA_HOME=/usr/local/cuda-12.4
export PATH=$CUDA_HOME/bin:$PATH

# HuggingFace 缓存
export HF_HOME=/path/to/your/hf_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
```

vLLM 关键环境变量：

```bash
export VLLM_ATTENTION_BACKEND=XFORMERS
export VLLM_WORKER_GPU_MEM_FRACTION=0.90
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export VLLM_LOGGING_LEVEL=INFO
```

服务默认值：端口 `8000`；模型 `Qwen/Qwen3-32B-AWQ`（最大长度 40960，TP=2）/ `Qwen/Qwen3-32B`（32768，TP=4）；显存利用率 90%。

### Apple Silicon / MLX

```bash
conda env update -n llm -f environment-llm-mac.yml
make mlx-start-bg
make mlx-status
make mlx-test
```

默认模型来自 `environment-llm-mac.yml`；切模型用 `MODEL=...` 显式传。

## 服务管理

```bash
make vllm-start          # 前台启动 AWQ
make vllm-start-32b      # 前台启动 32B
make vllm-start-bg       # tmux 后台启动 AWQ
make vllm-status         # 状态
make vllm-logs           # 日志（tail -f）
make vllm-stop           # 停止
```

`tmux attach -t vllm` 进后台 session。

权威健康检查：`python scripts/check_vllm.py`（比 `manage_vllm.sh status` 更可靠）。

## 常见排障

| 现象 | 应对 |
| --- | --- |
| `cannot find -lcuda` | 见上方"CUDA / vLLM"配置 |
| `manage_vllm.sh status` 状态误判 | 用 `python scripts/check_vllm.py` |
| `404 The model X does not exist` | 客户端模型名要与服务端一致；显式传 `--model` 或 `-m` |
| 译文里夹带原文或 `<think>` 内容 | 用主翻译入口，不要直调底层 client；输出仅留译文，原文进日志 |
| 32B CUDA OOM | 用 AWQ 量化版，或下调 `TP_SIZE` 与显存利用率 |
| tqdm 进度条不显示 | 前台 `make vllm-start` 或后台 `tmux attach` |
| 翻译卡 / 超时 | 检查 `tasks/translation/logs/latest_translation.log` 与 `translation_state.json` |

## 状态与日志位置

- 主翻译日志：`tasks/translation/logs/translation-<ts>.log`，软链 `latest_translation.log`
- 运行状态：`tasks/translation/logs/translation_state.json`（顶层 + 子目录都可能存在）
- QA 报告：默认 `tasks/translation/logs/qa_reports/`
- 人名预读：默认 `tasks/translation/logs/name_glossaries/`

## 给新 Agent 的建议

1. **不要先翻 journal 重建上下文**。按 [`../AGENTS.md`](../AGENTS.md) §11 的顺序读：开发规范 → PROJECT_STATUS → 翻译 README。
2. **优先用 Make / 管理脚本**，不要直接绕过去调底层 Python。
3. **CUDA / vLLM 环境变量是反复踩坑的来源**，复制本文件里的配置而不是自己拼。
4. **状态机是真相**：排查"为什么没跑/跑成什么样"先看 `translation_state.json`，不要靠 ls 输出目录猜。
5. **删代码时同步删 CLI flag、config 字段、文档段落** —— 这条在 [`../AGENTS.md`](../AGENTS.md) §8 有完整规则。

## "整理进展" 工作流

仓库里有 `.cursor/rules/organize-progress.mdc` 定义了"整理进展"指令的执行细则（git 状态分析、逐文件变更、日志写入、commit message 模板）。当用户说"整理进展"时按那份文档执行。

---

**最后更新**：2026-05-14
