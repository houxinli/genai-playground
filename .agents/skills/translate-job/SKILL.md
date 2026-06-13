---
name: translate-job
description: 日→中翻译执行器。读 job bundle、逐段翻译、写 result.json、import 落 candidate。用于对一篇作品/一个 job 产出译文候选。
---

# translate-job 执行器(Codex)

你作为**翻译执行器**。翻译规则与 `result.json` 格式以单一真相源
[`tasks/translation/docs/executor-instructions.md`](../../../tasks/translation/docs/executor-instructions.md)
为准——先读它,本文件不重复规则。

## 步骤

1. 拿到 job bundle(已有路径直接用;只给作品则
   `make translate-bundle SOURCE=<源目录> PROVIDER=<pixiv|fanbox> DOCUMENT=<document_id> OUT=<job.json>`)。
2. 按 executor-instructions.md 逐段翻译 `segments[]`。
3. 写 `result.json`:每段一个 candidate,`task_digest` 与各 `source_hash` 从 bundle **原样回填**,
   `producer.name="codex"`。
4. `make import-result TASK=<task.json> RESULT=<result.json> STORE=<store 目录>`;`written=N` 即成功。

## 边界

- 内容上无法翻译的段,留空字符串、不照抄原文(executor-instructions.md「拒译」一节)。
- 只产候选,不做 selection、不改发布版本。
