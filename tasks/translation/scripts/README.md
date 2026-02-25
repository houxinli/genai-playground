# Translation Scripts Guide

本目录存放翻译流水线的辅助脚本。按场景分为 3 类：下载、修复、清理。

## 1) Fanbox 下载（浏览器版，推荐）

### `fanbox_browser_downloader.js`（批量下载）
- 场景：整站批量拉取某个创作者全部文章。
- 方式：在已登录 Fanbox 的 Chrome/Edge 页面打开 DevTools Console，粘贴脚本后运行。
- 最小命令：
  ```javascript
  await downloadFanboxPosts({ creatorId: "momizi813" })
  ```
- 首次需选择目录：
  ```javascript
  await fanboxSelectDownloadDirectory()
  ```
- 支持断点续传（目录内 `.fanbox_state.json`）。

### `fanbox_browser_snippet.js`（单篇下载）
- 场景：当前文章页单篇导出。
- 页面示例：`https://<creator>.fanbox.cc/posts/<post_id>`
- 最小命令：
  ```javascript
  await downloadCurrentFanboxPost()
  ```
- 常用：
  ```javascript
  await downloadCurrentFanboxPost({ forcePickDirectory: true })
  ```

提示：你如果已经把脚本保存到 Chrome Snippets，可以直接右键 `Run`，不必每次粘贴。

## 2) Fanbox 下载（终端版）

### `fanbox_download.py`
- 场景：不走浏览器，直接通过 `FANBOXSESSID` 拉取。
- 依赖：`FANBOXSESSID`（CLI 参数/环境变量/cookie 文件）。
- 示例：
  ```bash
  conda run -n llm python tasks/translation/scripts/fanbox_download.py \
    --creator-id momizi813 \
    --max-posts 20
  ```

## 3) 修复与清理

### `repair_bilingual.py`
- 作用：对已有双语文件做增量修复，只重译缺失/异常行。
- 示例（目录批量）：
  ```bash
  conda run -n llm python tasks/translation/scripts/repair_bilingual.py \
    tasks/translation/data/pixiv/50235390 \
    --existing-bilingual-dir tasks/translation/data/pixiv/50235390_bilingual \
    --output-dir tasks/translation/data/pixiv/50235390_bilingual_fixed \
    --repair-existing --bilingual-simple --stream
  ```

### `cleanup_bad_outputs.py`
- 作用：删除 few-shot 泄漏或大段复制原文的双语文件。
- 示例：
  ```bash
  conda run -n llm python tasks/translation/scripts/cleanup_bad_outputs.py \
    --bilingual-dir tasks/translation/data/pixiv/50235390_bilingual \
    --original-dir tasks/translation/data/pixiv/50235390 \
    --dry-run
  ```

## 4) 其他相关脚本位置

- Pixiv 批量下载：`tasks/translation/src/scripts/batch_download_v1.py`
- 文件管理（rename/list/cleanup）：`tasks/translation/src/scripts/file_manager.py`
- 双语质量清理：`tasks/translation/src/scripts/cleanup_bilingual.py`
