---
name: translate-job
description: 把日→中翻译 job bundle 翻成 candidate 并导回库。当用户要"翻译这篇/这个 job"、用新 harness 翻译、执行 translate-job、或对一篇作品产出译文候选时使用。
argument-hint: "[job bundle 路径,或源目录+document_id]"
allowed-tools: Bash(make translate-bundle *), Bash(make import-result *), Bash(make export-job *), Read
---

# translate-job

你作为**翻译执行器**:读 job bundle → 逐段翻译 → 写 result.json → import 落 candidate。

**翻译规则与 result.json 格式以 [`tasks/translation/docs/executor-instructions.md`](../../../tasks/translation/docs/executor-instructions.md) 为准**——先读它,本文件不重复规则。

## 步骤

1. **拿到 job bundle**。已有 bundle 路径就用;只给了源目录/作品就先生成:
   `make translate-bundle SOURCE=<源目录> PROVIDER=<pixiv|fanbox> DOCUMENT=<document_id> OUT=<job.json>`
2. **读 bundle**,按 executor-instructions.md 逐段翻译 `segments[]`(SFW 内容自己翻;若属 NSFW,应由 Cursor+Grok 路线处理,不在本 skill)。
3. **写 result.json**:每段一个 candidate,`task_digest` 与各 `source_hash` 从 bundle 原样回填,`producer.name="claude-code"`。
4. **导回**:把 bundle 的 `task` 部分存成 task.json,然后
   `make import-result TASK=<task.json> RESULT=<result.json> STORE=<store 目录>`。
   看到 `written=N` 即成功;`quarantined` 说明回填的 digest/hash 不对。

## 边界

- 内容策略上无法翻译的段,**留空字符串、不要照抄原文**(executor-instructions.md「拒译」一节)。
- 本 skill 只产候选,不做 selection、不改发布版本。
