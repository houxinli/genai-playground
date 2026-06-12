# GenAI Playground

本仓库包含多个任务子项目。当前最常用的是 `tasks/translation`（Pixiv/Fanbox 下载 + 日中翻译 + 修复清理）。其他子项目：`tasks/ytmusic`、`tasks/sunday-movies`、`tasks/fitness`（自由文本健身日志解析 + 力量进展曲线，见 [`tasks/fitness/README.md`](tasks/fitness/README.md)）。

新 agent / 新对话建议先读：

- [`AGENTS.md`](AGENTS.md)：开发规范的真相源（编码、目录、配置分层、测试、commit/PR）
- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)：当前重点、组件状态、开发计划
- [`docs/AGENT_WORKFLOW.md`](docs/AGENT_WORKFLOW.md)：Codex/Claude Code/Cursor 共用的继续、交接与 context management
- [`tasks/translation/docs/system-design.md`](tasks/translation/docs/system-design.md)：翻译目标架构、Agent 协议、版本模型与迁移路线
- [`tasks/translation/README.md`](tasks/translation/README.md)：翻译子系统执行手册
- [`docs/AGENT_CONTEXT.md`](docs/AGENT_CONTEXT.md)：稳定环境/排障背景，按需翻

## 关键目录

```
genai-playground/
├── Makefile
├── scripts/
│   ├── manage_vllm.sh
│   ├── manage_translation.sh
│   └── monitor_translation.sh
├── docs/
│   ├── README.md
│   ├── PROJECT_STATUS.md
│   ├── AGENT_WORKFLOW.md
│   ├── AGENT_CONTEXT.md
│   └── journal/
├── agent/
│   ├── schemas/
│   ├── templates/
│   └── tasks/
└── tasks/
    └── translation/
        ├── README.md
        ├── docs/system-design.md
        ├── translate
        ├── src/
        └── scripts/
```

## 快速开始（翻译管线）

先准备环境：

```bash
conda activate llm
```

### 1) 启动 vLLM

```bash
make vllm-start-bg MODEL=Qwen/Qwen3-32B-AWQ
make vllm-status
```

### 2) 下载数据

```bash
# Pixiv
make pixiv-download USER_ID=50235390 ARGS="--limit 0 --offset 0 --rate-limit 1 --retries 5"

# Fanbox（终端版）
make fanbox-download CREATOR_ID=momizi813 ARGS="--max-posts 20"
```

Fanbox 浏览器下载（Chrome/Edge Console）请看：
[`tasks/translation/scripts/README.md`](tasks/translation/scripts/README.md)

### 3) 批量翻译

```bash
make translate-batch INPUT_DIR=tasks/translation/data/pixiv/50235390
# 或后台
make translate-batch-bg INPUT_DIR=tasks/translation/data/pixiv/50235390
```

### 4) 修复/清理

```bash
conda run -n llm python tasks/translation/src/translate.py \
  tasks/translation/data/pixiv/50235390 \
  --repair-existing \
  --preset pixiv_openrouter_local_names
conda run -n llm python tasks/translation/src/scripts/cleanup_bilingual.py --help
```

## 文档

- 当前状态与计划：[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)
- 跨 Agent 开发：[`docs/AGENT_WORKFLOW.md`](docs/AGENT_WORKFLOW.md)
- 翻译系统设计：[`tasks/translation/docs/system-design.md`](tasks/translation/docs/system-design.md)
- 总览：[`docs/README.md`](docs/README.md)
- Agent 上下文：[`docs/AGENT_CONTEXT.md`](docs/AGENT_CONTEXT.md)
- 翻译任务：[`tasks/translation/README.md`](tasks/translation/README.md)
- Journal 索引：[`docs/journal/README.md`](docs/journal/README.md)
