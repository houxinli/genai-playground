# Translation Task

当前翻译流水线分为 3 段：`下载 -> 翻译 -> 修复/清理`，支持 Pixiv 和 Fanbox 两条下载链路。

开始前建议先看：

- [`../../docs/PROJECT_STATUS.md`](../../docs/PROJECT_STATUS.md)：当前状态、组件健康度、开发计划
- [`../../docs/AGENT_CONTEXT.md`](../../docs/AGENT_CONTEXT.md)：稳定背景和常用约定
- [`../../docs/journal/README.md`](../../docs/journal/README.md)：历史决策和问题记录

这份 README 主要负责“怎么运行”，不是“当前优先级的真相源”。

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
├── scripts/repair_bilingual.py         # 增量修复双语文件
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

```bash
make translate-start-fg ARGS="tasks/translation/data/fanbox/momizi813/11386126.txt \
  --bilingual-simple --stream \
  --name-glossary-file tasks/translation/data/fanbox/name_maps/momizi813_rules.txt \
  --enable-name-glossary \
  --name-glossary-output-dir tasks/translation/logs/name_glossaries"
```

## 3. 修复与清理

### 增量修复（主入口，推荐）

```bash
conda run -n llm python tasks/translation/src/translate.py \
  tasks/translation/data/pixiv/50235390 \
  --repair-existing \
  --preset pixiv_gemma4_heretic_mlx_local \
  --stream
```

这会自动读取同级 `*_bilingual/`，输出到 `*_bilingual_fixed/`。

### 增量修复（高级覆盖参数）

```bash
conda run -n llm python tasks/translation/scripts/repair_bilingual.py \
  tasks/translation/data/pixiv/50235390 \
  --existing-bilingual-dir tasks/translation/data/pixiv/50235390_bilingual \
  --output-dir tasks/translation/data/pixiv/50235390_bilingual_fixed \
  --repair-existing --bilingual-simple --stream
```

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

## 常用查看命令

```bash
./scripts/monitor_translation.sh status
./scripts/monitor_translation.sh monitor
./scripts/monitor_translation.sh stats
```
