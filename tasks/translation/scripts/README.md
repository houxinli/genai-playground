# Translation Scripts Guide

本目录存放翻译流水线的辅助脚本。按场景分为 3 类：下载、修复、清理。

进入脚本细节前建议先看：

- [`../../../docs/PROJECT_STATUS.md`](../../../docs/PROJECT_STATUS.md)：当前状态、组件健康度、开发计划
- [`../docs/system-design.md`](../docs/system-design.md)：目标系统设计与脚本迁移方向
- [`../README.md`](../README.md)：翻译任务主操作手册
- [`../../../docs/journal/README.md`](../../../docs/journal/README.md)：历史决策和排障记录

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
- 状态：历史兼容入口；新调用优先走 `src/translate.py --repair-existing`。
- 作用：对已有双语文件做增量修复，只重译缺失/异常行。
- 示例（目录批量）：
  ```bash
  conda run -n llm python tasks/translation/scripts/repair_bilingual.py \
    tasks/translation/data/pixiv/50235390 \
    --existing-bilingual-dir tasks/translation/data/pixiv/50235390_bilingual \
    --output-dir tasks/translation/data/pixiv/50235390_bilingual_fixed \
    --repair-existing --bilingual-simple --stream
  ```

目标架构中 repair 将创建新 candidate，不再直接以多个输出目录表达版本。该脚本在 candidate/version
主路径落地后应薄化为兼容导入层或删除。

### `cleanup_bad_outputs.py`
- 作用：删除 few-shot 泄漏或大段复制原文的双语文件。
- 示例：
  ```bash
  conda run -n llm python tasks/translation/scripts/cleanup_bad_outputs.py \
    --bilingual-dir tasks/translation/data/pixiv/50235390_bilingual \
    --original-dir tasks/translation/data/pixiv/50235390 \
    --dry-run
  ```

### `apply_translation_replacements.py`
- 作用：对双语文件“译文行”批量做确定性替换（常用于统一人名/称谓译法），不改原文行。
- 默认输出：`<原目录>_replaced/同名文件.txt`。
- 先 dry-run 观察命中数量：
  ```bash
  conda run -n llm python tasks/translation/scripts/apply_translation_replacements.py \
    tasks/translation/data/fanbox/momizi813_bilingual_v2/11386126.txt \
    --replace 高雄=高尾 \
    --replace 高男=高尾 \
    --replace 高冈=高尾 \
    --dry-run
  ```
- 批量目录输出到新目录：
  ```bash
  conda run -n llm python tasks/translation/scripts/apply_translation_replacements.py \
    tasks/translation/data/fanbox/momizi813_bilingual_v2 \
    --rules-file tasks/translation/data/fanbox/name_rules.txt \
    --output-dir tasks/translation/data/fanbox/momizi813_bilingual_v3
  ```

### `normalize_bilingual_names.py`
- 作用：按“日文名 -> 中文标准名”统一双语正文中的人名；支持显式别名，适合长期复用到同作者新文。
- 默认输出：`<原目录>_namefix/同名文件.txt`。
- 推荐把“标准名 + 别名”合并成一个规则文件（`--rules-file`）：
  - `日文=中文标准名`
  - `日文=中文标准名|错译1,错译2`
  - 建议“每个日文名一行”
- 推荐工作流：
  1. 先 `--dry-run --report-file` 看候选统计。
  2. 把稳定的人名和错译都写进 `--rules-file`。
  3. `--auto-canonical` 默认关闭；只有做候选发现时才临时开 `first` 或 `most`。
  4. 已经维护好别名字典后，建议加 `--no-auto-alias`，避免自动推断带来的误替换。
- 示例（单文件）：
  ```bash
  conda run -n llm python tasks/translation/scripts/normalize_bilingual_names.py \
    tasks/translation/data/fanbox/momizi813_bilingual/11386126.txt \
    --rules-file tasks/translation/data/fanbox/name_maps/momizi813_rules.txt \
    --global-alias \
    --no-auto-alias \
    --dry-run \
    --report-file /tmp/namefix_report.json
  ```
- 示例（目录批量）：
  ```bash
  conda run -n llm python tasks/translation/scripts/normalize_bilingual_names.py \
    tasks/translation/data/fanbox/momizi813_bilingual \
    --rules-file tasks/translation/data/fanbox/name_maps/momizi813_rules.txt \
    --output-dir tasks/translation/data/fanbox/momizi813_bilingual_namefix
  ```

### `build_name_alias_draft.py`
- 作用：从 `normalize_bilingual_names.py --dry-run --report-file` 的报告中，聚合“全库候选人名”和 alias 草案。
- 输出：
  - `--output-alias-file`：已有标准名的 alias 草案（可直接作为 `--alias-file`）。
  - `--output-candidate-file`：新人名候选（含待确认项）。
- 推荐流程：
  1. 先跑全库 dry-run 报告：
  ```bash
  conda run -n llm python tasks/translation/scripts/normalize_bilingual_names.py \
    tasks/translation/data/fanbox/momizi813_bilingual \
    --auto-canonical off \
    --no-auto-alias \
    --dry-run \
    --report-file tasks/translation/logs/name_scan_momizi813_full.json
  ```
  2. 基于报告产出草案：
  ```bash
  conda run -n llm python tasks/translation/scripts/build_name_alias_draft.py \
    tasks/translation/logs/name_scan_momizi813_full.json \
    --rules-file tasks/translation/data/fanbox/name_maps/momizi813_rules.txt \
    --source-dir tasks/translation/data/fanbox/momizi813 \
    --candidate-min-total 4 \
    --candidate-min-top 2 \
    --output-alias-file tasks/translation/data/fanbox/name_maps/momizi813_aliases_draft.txt \
    --output-candidate-file tasks/translation/data/fanbox/name_maps/momizi813_names_candidates.txt
  ```

### `audit_name_consistency.py`
- 作用：在已做过 namefix 的目录上审计“规则未覆盖的人名变体候选”，用于迭代补充 `rules`。
- 输入：双语目录 + `--rules-file`
- 输出：
  - `--report-json`：机器可读明细
  - `--draft-file`：人工复核草案
- 示例：
  ```bash
  conda run -n llm python tasks/translation/scripts/audit_name_consistency.py \
    tasks/translation/data/fanbox/momizi813_bilingual_v2_namefix \
    --rules-file tasks/translation/data/fanbox/name_maps/momizi813_rules.txt \
    --min-count 2 \
    --report-json tasks/translation/logs/name_consistency_audit_momizi813_v2_namefix.json \
    --draft-file tasks/translation/data/fanbox/name_maps/momizi813_rules_candidates_v2_namefix.txt
  ```

### `discover_untracked_names.py`
- 作用：发现 `rules` 尚未覆盖的“新角色候选”（基于原文敬称），并给出译文侧中文候选分布。
- 适用场景：你已经有一版 `rules`，但怀疑还有很多角色没纳入。
- 输出：
  - `--report-json`：完整统计（含文件命中）
  - `--draft-file`：待人工确认的规则草案
- 示例：
  ```bash
  conda run -n llm python tasks/translation/scripts/discover_untracked_names.py \
    tasks/translation/data/fanbox/momizi813 \
    tasks/translation/data/fanbox/momizi813_bilingual_v2 \
    --rules-file tasks/translation/data/fanbox/name_maps/momizi813_rules.txt \
    --min-mentions 2 \
    --min-mentions-hiragana 5 \
    --report-json tasks/translation/logs/discover_untracked_names_momizi813_v2.json \
    --draft-file tasks/translation/data/fanbox/name_maps/momizi813_untracked_names_candidates.txt
  ```

### `convert_bilingual_to_simplified.py`
- 作用：批量将双语文件中的“译文行”统一为简体中文（不改原文行）。
- 默认输出：`<原目录>_simp/同名文件.txt`（例如 `momizi813_bilingual_simp/9807258.txt`）。
- 推荐（deterministic）：`opencc` backend
  先准备本地 opencc（任选其一）：
  ```bash
  brew install opencc
  # 或
  conda run -n llm pip install opencc-python-reimplemented
  ```
  ```bash
  conda run -n llm python tasks/translation/scripts/convert_bilingual_to_simplified.py \
    tasks/translation/data/fanbox/momizi813_bilingual \
    --output-dir tasks/translation/data/fanbox/momizi813_bilingual_simp \
    --backend opencc
  ```
- 无 opencc 时可用 `llm` backend（OpenRouter）：
  ```bash
  conda run -n llm python tasks/translation/scripts/convert_bilingual_to_simplified.py \
    tasks/translation/data/fanbox/momizi813_bilingual \
    --output-dir tasks/translation/data/fanbox/momizi813_bilingual_simp \
    --backend llm \
    --model <available-model-slug>
  ```

## 4) 其他相关脚本位置

- Pixiv 批量下载：`tasks/translation/src/scripts/batch_download_v1.py`
- 文件管理（rename/list/cleanup）：`tasks/translation/src/scripts/file_manager.py`
- 双语质量清理：`tasks/translation/src/scripts/cleanup_bilingual.py`
