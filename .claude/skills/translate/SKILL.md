---
name: translate
description: 用统一 TSV harness 把 pixiv/fanbox 作品日→中翻译并发布渲染。支持断点续跑、整作者、Cursor/Grok/Claude/Codex/OpenRouter 任一执行器。
argument-hint: "<provider> <creator_id> [work_id] [executor=cursor-grok|claude-code|codex]"
---

# translate

你是日→中翻译执行器。用户一句话即可触发,例如:

- `用 translate 翻译 pixiv 104039620 的 28349232,执行器 cursor-grok。`
- `用 translate 继续 pixiv 104039620 的 28349232。`

**不依赖聊天历史**:先从 workspace 文件恢复状态;有未完成的就续,没有才新建。**全程自主连续执行,步骤之间不要问"是否继续"**;只有源无法解析、或结构命令反复失败才停下报告。

翻译规则以 [`tasks/translation/docs/executor-instructions.md`](../../tasks/translation/docs/executor-instructions.md) 为准——先读它,本文件不重复。

## 单一中间产物:扁平 TSV

你**只写 TSV,不手写 `result.json`**——result 由 harness 从 `job.json + zh.tsv` 机械组装(回填 segment_id/source_hash/task_digest)。

```text
job.json → results/<source_id>.zh.tsv → (harness 组装) result.json → 发布 → 渲染 → verify
```

TSV 每行:`<0 基段序号><TAB><中文译文>`。译文可空(表示无法翻译,但该行必须在)。不要 Markdown 包裹、不要解释、不要多列。

## 流程

工作区 `WS=tasks/translation/data/workspaces/<provider>-<work_id>`。

1. **prepare**(导出 bundle;源在 `data/<provider>/<creator>/<work_id>.txt`):
   ```
   mkdir -p $WS/src && cp <源 txt> $WS/src/
   make translate-user MODE=prepare PROVIDER=<p> SOURCE=$WS/src STORE=$WS/store JOBS_DIR=$WS/jobs
   ```
2. **翻译**:读 `$WS/jobs/<work_id>.job.json` 的 `segments[]`,逐段译,写/追加 `$WS/results/<work_id>.zh.tsv`。
   - tags 段译成 `原词 / 中文`,保留 `[]` 和逗号;译文不得残留假名;人名/术语遵 `job.context_pack`。
3. **发布渲染**(finish 自动从 tsv 用原始 job 组装、发布、渲染、合并整本):
   ```
   make translate-user MODE=finish PROVIDER=<p> SOURCE=$WS/src STORE=$WS/store JOBS_DIR=$WS/jobs RENDER=$WS/rendered RESULTS_DIR=$WS/results PRODUCER=<执行器名>
   ```
4. **verify**(独立核对,**回贴真实 JSON**;不准凭记忆声称完成):
   ```
   make translate-user MODE=verify PROVIDER=<p> SOURCE=$WS/src STORE=$WS/store RENDER=$WS/rendered RESULTS_DIR=$WS/results
   ```
5. **FEEDBACK**:写 `$WS/FEEDBACK.md`——verify JSON、`review_required` 段及译文问题、改进建议;回贴要点。

整作者:把该 creator 的所有 `<work_id>.txt` 都放进 `$WS/src`,prepare/finish 会逐篇处理并合并整本。

## 断点续跑

tsv 不全时 finish 会报缺段。续法:对照 `job.segments` 数量找出 tsv 里缺的段序号,**补译那些行追加到同一个 `<work_id>.zh.tsv`**,再重跑 finish。tsv 已有的行不重译。(无 run_id / 分片目录——就一个扁平 tsv。)

## 边界

- **结构错误必须修**:缺段、重复/越界段序号、stale job/source。
- **质量问题不阻断发布**:假名残留 / same_as_source / 拒绝模板等单候选会**照常发布**并计入 `review_required`,事后改对应 tsv 行重跑 finish 即可——不要因此重译整篇。
- 完全无译文(空候选)的段仍会阻断建版。
- **内容策略(如 NSFW 由哪个执行器承担)以 [`AGENTS.md`](../../AGENTS.md) 与各执行器自身适配为准**,本 skill 不内联——按你所在执行器的约定执行。
