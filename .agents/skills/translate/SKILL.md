---
name: translate
description: 用统一 TSV harness 翻译 pixiv/fanbox 单篇或整作者作品。支持断点续跑、完整 run、少量片段 patch run、Cursor/Grok/Claude/Codex/OpenRouter 交叉验证。
argument-hint: "<provider> <creator_id> [work_id|all] [executor=cursor-grok|claude-code|codex|openrouter]"
---

# translate

你是日->中翻译执行器。用户可以只说一句话，例如：

- `用 translate skill 翻译 pixiv 用户 104039620 的 28349232 文章，执行器 cursor-grok。`
- `用 translate skill 翻译 pixiv 用户 104039620 的所有文章，执行器 cursor-grok。`
- `用 translate skill 继续 pixiv 用户 104039620 的 28349232 文章。`

不要依赖聊天历史。先从 workspace 里的文件恢复状态；已有未完成 run 就继续，没有才新建。

## 单一中间产物

所有执行器统一走：

```text
job.json -> zh.tsv -> result.json -> import -> version -> publish -> render -> verify/review
```

- 你只写 TSV，不手写 `result.json`。
- `result.json` 由 harness 从 `job.json + zh.tsv` 机械组装，回填 `segment_id` / `source_hash` / `task_digest`。
- OpenRouter、Cursor/Grok、Claude Code、Codex、人工翻译都应产同形 TSV，便于 diff、交叉验证和择优。

TSV 每行格式：

```text
<0-based segment index><TAB><中文译文>
```

译文可以为空字符串表示无法翻译，但行必须存在。不要输出 Markdown 包裹、解释或额外列。

## Run 类型

同一 source 可以有多个 run。不要把 patch run 当 full run 检查。

| 类型 | 用途 | 完整性规则 |
| --- | --- | --- |
| `full` | 首次整篇翻译或重新全量翻译 | 必须覆盖 job 的所有 segment index |
| `patch` | 少量片段重译/修复 | 只要求覆盖 patch scope 指定的 index |
| `review` | 只产诊断/feedback | 不产发布译文 |

`patch` 发布时不是拿 partial TSV 直接 assemble；必须先解析当前已发布 version 或最近可用 full run，形成 base translations，再把 patch TSV 覆盖到对应 index，最后组装一份完整 `result.json`。如果没有 base，patch run 不能发布，必须先做 full run。

分片 TSV 只是 write-ahead 中间文件：

```text
results/<source_id>/<run_id>/parts/000000-000024.zh.tsv
results/<source_id>/<run_id>/parts/000025-000049.zh.tsv
```

分片只按它声明/计划的范围检查完整性。合并后的 run TSV 再按 run 类型检查：`full` 查全段，`patch` 查 patch scope。

## 恢复规则

进入任务后先定位 workspace：

```text
tasks/translation/data/workspaces/<provider>-<creator_id>/
tasks/translation/data/workspaces/<provider>-<source_id>/
```

按下面顺序恢复，不要猜：

1. 读 `jobs/prepare_manifest.json` 和对应 `<source_id>.job.json`，确认 segment 总数。
2. 扫 `results/` 下已有 `.zh.tsv`、`parts/*.zh.tsv`、`result.json`。
3. 读 `rendered/translate_manifest.json` 和 `FEEDBACK.md`，判断是否已 publish/render。
4. 若存在未完成 run，继续该 run 的 missing scope；否则按用户目标新建 run。

Full run 的 next action 是最小缺失 index range。Patch run 的 next action 只来自用户标记的问题片段、review report 或 FEEDBACK 里的具体 segment，不要因为 patch TSV 不全而重译整篇。

## 翻译规则

翻译规则以 `tasks/translation/docs/executor-instructions.md` 为准。关键约束：

- 逐段对应，不合并、不拆分、不调序。
- 人名/术语遵守 `job.context_pack.entities` 和 `terminology`。
- `metadata.tags` 译成 `原词 / 中文` 并保留 `[]` 与逗号。
- 译文不得残留日文假名；确实无法翻译时留空，不要照抄原文。

## 执行边界

- 结构错误必须修：缺段、重复 index 冲突、越界 index、stale job/source hash。
- 质量问题不应阻断 render/publish：假名残留、拒绝模板、same_as_source、术语不稳等进入 review/FEEDBACK，后续用 patch run 修。
- 结束回复必须包含真实 verify JSON 或 manifest summary、产物路径、未解决问题数量和下一步 patch scope。
- 中途不要问是否继续。只有源无法解析、结构命令连续失败、或没有 base 却被要求 patch publish 时才停下报告。
