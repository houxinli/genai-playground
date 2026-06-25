---
name: translate-work
description: 把一部作品(pixiv/fanbox 单篇)用 agent 当译者跑通新架构全流程并自我 review。当用户说"翻译某篇/某作品""用 agent 翻 <id>""跑 translate-work"时使用。SFW 用本 agent;NSFW 走 cursor-grok 路线。
argument-hint: "<provider> <user_id> <work_id>(或源 txt 路径)"
allowed-tools: Bash(make translate-user *), Read, Write
---

# translate-work

你作为**翻译执行器**:把一部作品 prepare → 逐段翻译 → finish 发布渲染 → **自我 review 提 feedback**。
翻译规则与 result.json 格式以 [`tasks/translation/docs/executor-instructions.md`](../../../tasks/translation/docs/executor-instructions.md) 为准——**先读它**,本文件不重复规则。

## 步骤

1. **定位源**:`tasks/translation/data/<provider>/<user_id>/<work_id>.txt`。建独立工作区:
   ```
   WS=tasks/translation/data/workspaces/<provider>-<work_id>
   mkdir -p $WS/src && cp <源 txt> $WS/src/
   make translate-user MODE=prepare PROVIDER=<provider> SOURCE=$WS/src STORE=$WS/store JOBS_DIR=$WS/jobs
   ```
   → 得 `$WS/jobs/<work_id>.job.json`(含 task / task_digest / segments[])。

2. **翻译**(读 job,逐段译,写 `$WS/results/<work_id>.result.json`):
   - 每段一个 candidate;`task_id`/`task_digest`/各 `source_hash` 从 job **原样回填**;
     `producer.name` 用你的执行器名(本 agent="claude-code";Cursor 路线="cursor-grok")。
   - 规则要点见 executor-instructions:tags 译成 `原词 / 中文`;纯符号分隔符(＊＊＊)可原样保留(QA 已豁免同形);
     译文不得残留假名;无法翻译的段留空字符串、不照抄;人名/称谓全篇统一。

3. **发布 + 渲染**:
   ```
   make translate-user MODE=finish PROVIDER=<provider> SOURCE=$WS/src STORE=$WS/store RENDER=$WS/rendered RESULTS_DIR=$WS/results
   ```
   summary 的 `published` 应为 1。

4. **自我 review + feedback**(必做):
   - 读 `$WS/rendered/translate_manifest.json`:若 `review_required>0` 或 `status=unresolved`,列出卡住的
     segment + QA 原因,修订对应译文重跑第 3 步,直到 published=1。
   - 通读 `$WS/rendered/<work_id>.zh.txt` 与 `.bilingual.txt`:核对人名一致性、语气自然度、漏译误译、metadata。
   - 把 feedback 写到 `$WS/FEEDBACK.md`:① 发布计数;② 具体译文问题(segment_id+建议);③ 流程/QA 误报(若有);
     ④ 对 harness/executor-instructions 的改进建议。最后把要点回贴。

## 边界

- 只产候选 + 自我 review,**不**改发布策略、不批准实体;importer/择优/发布由底层保证。
- 大作品按相同模式逐篇;`LIMIT` 可控范围。
