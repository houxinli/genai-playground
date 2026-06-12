# Translation Task

当前生产流水线分为 3 段：`下载 -> 翻译 -> 修复/清理`，支持 Pixiv 和 Fanbox 两条下载链路。
下一代 workspace/candidate/version/API+Agent 目标架构尚未切入生产，见
[`docs/system-design.md`](docs/system-design.md)。

开始前建议先看：

- [`../../docs/PROJECT_STATUS.md`](../../docs/PROJECT_STATUS.md)：当前状态、组件健康度、开发计划
- [`docs/system-design.md`](docs/system-design.md)：目标数据模型、API/Agent 双路线、多候选版本和迁移计划
- [`../../docs/AGENT_CONTEXT.md`](../../docs/AGENT_CONTEXT.md)：稳定背景和常用约定
- [`../../docs/journal/README.md`](../../docs/journal/README.md)：历史决策和问题记录

这份 README 只负责“当前怎么运行”，不是目标架构或当前优先级的真相源。

## 环境

建议先执行：

```bash
conda activate llm
```

补充：`tasks/translation/translate` 现在会优先尝试 `conda run -n llm`，未激活环境也能运行。

## 目录与入口

```
tasks/translation/
├── translate                      # 便捷入口（调用 src/translate.py）
├── src/translate.py               # 主翻译入口
├── src/scripts/batch_download_v1.py  # Pixiv 批量下载
├── src/scripts/file_manager.py        # 文件管理（rename/list/cleanup）
├── src/scripts/cleanup_bilingual.py   # 双语质量清理
├── scripts/fanbox_download.py         # Fanbox 终端下载
├── scripts/fanbox_browser_downloader.js # Fanbox 浏览器批量下载
├── scripts/fanbox_browser_snippet.js    # Fanbox 浏览器单篇下载
├── scripts/repair_bilingual.py         # 历史 repair 入口，优先用 src/translate.py
├── scripts/convert_bilingual_to_simplified.py # 双语译文繁转简
└── scripts/cleanup_bad_outputs.py      # 清理异常双语输出
```

## 1. 下载

### Pixiv（终端）

```bash
# 先准备 refresh token（一次性）
conda run -n llm python tasks/translation/src/scripts/pixiv_auth.py login

# 按作者批量下载
make pixiv-download USER_ID=50235390 ARGS="--limit 0 --offset 0 --rate-limit 1 --retries 5"
```

数据默认写入：`tasks/translation/data/pixiv/<USER_ID>/`

### Fanbox（浏览器，推荐）

你已经提到自己是“Chrome 右键/脚本”方式，这条就是对应入口：

1. 打开已登录 Fanbox 页面
2. F12 -> Console（或 Chrome Snippets 右键 Run）
3. 粘贴并执行 `tasks/translation/scripts/fanbox_browser_downloader.js`
4. 执行：

```javascript
await fanboxSelectDownloadDirectory()
await downloadFanboxPosts({ creatorId: "momizi813" })
```

单篇下载用 `fanbox_browser_snippet.js`：

```javascript
await downloadCurrentFanboxPost()
```

### Fanbox（终端备选）

```bash
make fanbox-download CREATOR_ID=momizi813 ARGS="--max-posts 20"
```

## 2. 翻译

### 启动本地 vLLM

```bash
make vllm-start-bg MODEL=Qwen/Qwen3-32B-AWQ
make vllm-status
make vllm-logs
```

### Apple Silicon：启动本地 MLX（默认 Gemma 4 Heretic）

```bash
conda env update -n llm -f environment-llm-mac.yml
make mlx-start-bg
make mlx-status
make mlx-test
```

如果需要临时切换模型，再显式传 `MODEL=...`。

### 批量翻译（推荐）

```bash
# 前台
make translate-batch INPUT_DIR=tasks/translation/data/pixiv/50235390

# 后台
make translate-batch-bg INPUT_DIR=tasks/translation/data/pixiv/50235390
make translate-status
make translate-attach
make translate-logs-follow
```

默认使用 `bilingual-simple` 流程，输出到同级 `*_bilingual/` 目录。

### 单文件/自定义参数

```bash
make translate-start-fg ARGS="tasks/translation/data/pixiv/50235390/25341719.txt --bilingual-simple --stream"
```

说明：默认 provider 是 `openrouter`。如需切本地 vLLM，请显式传 `--llm-provider vllm --llm-base-url http://localhost:8000/v1`。

在 Apple Silicon + MLX 场景下，可直接复用同一套 OpenAI 兼容接口：

```bash
make translate-start-fg ARGS="tasks/translation/data/pixiv/50235390/12430834.txt --preset pixiv_gemma4_heretic_mlx_local --stream"
```

需要固定系列人名时，先维护一份规则文件，再启用全文预读。存在人工规则时，流水线会优先注入人工规则；自动预读结果会写入 `--name-glossary-output-dir`，用于后续补充规则。
正文翻译可以继续使用 OpenRouter，同时让人名预读单独走本地 OpenAI 兼容服务，避免本地模型参与正文翻译质量链路。

```bash
make translate-start-fg ARGS="tasks/translation/data/fanbox/momizi813/11386126.txt \
  --preset fanbox_openrouter_local_names \
  --name-glossary-file tasks/translation/data/fanbox/name_maps/momizi813_rules.txt \
  --stream"
```

`fanbox_openrouter_local_names` 默认使用 OpenRouter 做正文翻译、本地 vLLM/MLX 做人名预读，并在完成后写入硬规则 QA 报告。Pixiv 可使用 `pixiv_openrouter_local_names`。

已有输出也可以单独跑 QA：

```bash
conda run -n llm python tasks/translation/src/translate.py \
  tasks/translation/data/fanbox/momizi813_bilingual_fixed/11386126.txt \
  --qa-only \
  --name-glossary-file tasks/translation/data/fanbox/name_maps/momizi813_rules.txt
```

如果先对旧双语目录跑了 QA，可在修复时把 QA 报告目录喂回 repair，让拒绝模板、人名坏别名等 QA 标记的问题行也进入重译：

```bash
conda run -n llm python tasks/translation/src/translate.py \
  tasks/translation/data/fanbox/momizi813 \
  --repair-existing \
  --preset fanbox_openrouter_local_names \
  --repair-from-qa-report-dir tasks/translation/logs/qa_reports \
  --qa-fail-on-error
```

## 3. 修复与清理

### 增量修复（主入口，推荐）

```bash
conda run -n llm python tasks/translation/src/translate.py \
  tasks/translation/data/pixiv/50235390 \
  --repair-existing \
  --preset pixiv_openrouter_local_names \
  --stream
```

修复人名敏感的译文时，同样传入 `--name-glossary-file`，修复 prompt 会注入相同的人名硬约束。

这会自动读取同级 `*_bilingual/`，输出到 `*_bilingual_fixed/`。

### 增量修复（历史兼容入口）

```bash
conda run -n llm python tasks/translation/scripts/repair_bilingual.py \
  tasks/translation/data/pixiv/50235390 \
  --existing-bilingual-dir tasks/translation/data/pixiv/50235390_bilingual \
  --output-dir tasks/translation/data/pixiv/50235390_bilingual_fixed \
  --repair-existing --bilingual-simple --stream
```

该脚本只用于兼容旧操作或诊断。新调用统一走主入口 `src/translate.py --repair-existing`。

### 清理低质量 bilingual

```bash
conda run -n llm python tasks/translation/src/scripts/cleanup_bilingual.py \
  tasks/translation/data/pixiv/50235390
```

### 清理 few-shot 泄漏/复制原文

```bash
conda run -n llm python tasks/translation/scripts/cleanup_bad_outputs.py \
  --bilingual-dir tasks/translation/data/pixiv/50235390_bilingual \
  --original-dir tasks/translation/data/pixiv/50235390 \
  --dry-run
```

### 批量繁转简（仅译文行）
默认输出到 `<原目录>_simp/同名文件`（不覆盖原文件）。

先安装本地 opencc（任选其一）：

```bash
brew install opencc
# 或 conda 环境安装 Python 版
conda run -n llm pip install opencc-python-reimplemented
```

```bash
conda run -n llm python tasks/translation/scripts/convert_bilingual_to_simplified.py \
  tasks/translation/data/fanbox/momizi813_bilingual \
  --output-dir tasks/translation/data/fanbox/momizi813_bilingual_simp \
  --backend opencc
```

## 4. 目标工作流（尚未实现）

目标系统会在保持当前 Make 入口兼容的前提下，逐步增加：

- segment 级多个 candidate 和不可变 document version
- OpenRouter/vLLM/MLX 批量 API 与 Codex/Claude Code/Cursor job bundle 双路线
- 单篇与跨文本 entity/terminology 一致性
- 用户标记某句话有问题并触发定向 review/repair
- QA 后只接受明确改善的 repair candidate
- 从确定版本渲染 bilingual/zh/package

实现阶段、JSON/SQLite 边界和兼容策略见 [`docs/system-design.md`](docs/system-design.md)。

## 常用查看命令

```bash
./scripts/monitor_translation.sh status
./scripts/monitor_translation.sh monitor
./scripts/monitor_translation.sh stats
```
