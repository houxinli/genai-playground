---
name: extract-names
description: 用 agent(Cursor+Grok 等)从一部作品抽取人名,产 {原文,读音,中文译名},导入实体库经 review。当用户要"抽人名/建姓名库/提取角色名/给某篇/某作者建译名表"时使用。
argument-hint: "[revision JSON 路径,或 document_id]"
allowed-tools: Bash(make extract-job *), Bash(make import-extraction *), Read, Write
---

# extract-names

你作为**人名抽取器**:读作品文本 → 列出所有出场人名 → 导入实体库(经 review 闸门)。
抽取是**不可信候选生产者**,准度由 review 兜——宁可多捞,坏的人审时剔除。

## 步骤

1. **导出待抽取文本**:`make extract-job REVISION=<rev.json> OUT=job.json`
   (job 含 document_id + 待扫描段 segments[{segment_id,kind,source_text}])。
2. **读 job,逐部作品通读后抽人名**,写 `result.json`:
   ```json
   {"document_id": "<原样回带 job 里的 document_id>", "proposals": [
     {"mention": "原文写法", "readings": ["假名读音"], "suggested_target": "建议中文译名",
      "confidence": 0.0-1.0, "segment_id": "该名首次出现段的 id(从 job.segments 取)"}
   ]}
   ```
   - 同一人物多种写法各列一条,但 `suggested_target` 保持一致。
   - **不要**把拟声词/普通名词/称谓本身当人名。给不准译名时 `suggested_target` 留空(留给 review 补)。
3. **导回**:`make import-extraction REVISION=<rev.json> RESULT=result.json ENTITY_STORE=<库> QUEUE=<队列>`
   - 看到 `{"proposals": N, "reviews": M}` 即成功。
   - 命中既有实体 → 链接;有译名的新名 → 建 `candidate` 实体(读音一并入库,供读音匹配);无译名 → 入 review 待补。

## 边界

- 作用域(provider/creator)由 `document_id` 自动推得,无需手填。
- 本 skill 只产候选 + 入 review,**不**直接批准/锁定实体(由 `entity-review approve` 人工决定)。
- 与启发式抽取(`make extract-entities`)互补:启发式离线兜底,本 skill 召回更高且能给译名/读音。
