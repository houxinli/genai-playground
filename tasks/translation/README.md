# Translation Task

当前翻译流水线分为 3 段：`下载 -> 翻译 -> 修复/清理`，支持 Pixiv 和 Fanbox 两条下载链路。

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

## 3. 修复与清理

### 增量修复（只补坏行/缺失行）

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

## 常用查看命令

```bash
./scripts/monitor_translation.sh status
./scripts/monitor_translation.sh monitor
./scripts/monitor_translation.sh stats
```
