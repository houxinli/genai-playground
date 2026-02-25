# GenAI Playground

本仓库包含多个任务子项目。当前最常用的是 `tasks/translation`（Pixiv/Fanbox 下载 + 日中翻译 + 修复清理）。

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
│   ├── AGENT_CONTEXT.md
│   └── journal/
└── tasks/
    └── translation/
        ├── README.md
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
conda run -n llm python tasks/translation/scripts/repair_bilingual.py --help
conda run -n llm python tasks/translation/src/scripts/cleanup_bilingual.py --help
```

## 文档

- 总览：[`docs/README.md`](docs/README.md)
- 翻译任务：[`tasks/translation/README.md`](tasks/translation/README.md)
- Journal 索引：[`docs/journal/README.md`](docs/journal/README.md)
