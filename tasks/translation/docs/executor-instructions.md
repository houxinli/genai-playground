# 翻译执行器指令（agent 中立）

> 本文件是**所有翻译执行器的单一真相源**：Claude Code、Cursor+Grok、Codex 等编码 agent 都按这一份
> 执行,各自的 skill/rule 只是指向本文件的薄壳,不重复翻译规则。

## 角色

你是一个**日→中翻译执行器**。给定一个 job bundle,你逐段翻译,产出一份 `result.json`,然后把它导回
candidate 库。你不做选择、不改发布版本——只产出候选译文。

## 输入:job bundle

由 `make translate-bundle` 或 `make export-job` 生成,结构:

```json
{
  "task": { "task_id": "...", "task_digest": "...", "segment_ids": [...],
            "source_hashes": { "<segment_id>": "<hash>" }, ... },
  "task_digest": "...",
  "segments": [ { "segment_id": "...", "kind": "body|metadata.*", "source_text": "<日文>" }, ... ]
}
```

## 翻译规则（复用现有流水线约定）

- **逐段对照、禁止省略**:`segments` 里每一个 segment 都必须有对应译文,不合并、不拆分、不调序、不跳过。
- **引号样式**:沿用原文的方引号「」『』,不要改成中文引号。
- **标点**:中文用恰当的中文标点;不要因为原文没有句号就省略。
- **拟声词/感叹词**:重复时控制在 5 次以内。
- **专名/人名一致**:同一专名全文译法一致(如有 glossary 以其为准)。
- **metadata.* segment**(title/caption/excerpt/series.title/tags):只译内容值。tags 译成 `原词 / 中文`
  并保留 `[]` 与逗号。
- **只输出译文**:不要加解释、注释、Markdown 包裹或额外空行。
- **假名残留**:译文不得残留日文假名(被翻成语气词/拟声词或删去);单独的 っ、ん 等同理。
- **不要把原文当译文**:逐段确认是中文译文,不是照抄日文(否则会被 QA 判 `same_as_source`)。

## 输出:result.json

对 bundle 的每个 segment 产一个 candidate,写成 `result.json`(符合 `schemas/result.schema.json`):

```json
{
  "schema_version": 1,
  "task_id": "<bundle.task.task_id>",
  "task_digest": "<bundle.task_digest 原样回填>",
  "producer": { "type": "harness", "name": "<claude-code|cursor-grok|codex>", "model": "<模型名或 null>" },
  "candidates": [
    { "result_candidate_key": "option-a",
      "segment_id": "<segment_id>",
      "source_hash": "<bundle.task.source_hashes[segment_id] 原样回填>",
      "text": "<你的中文译文>" }
  ],
  "findings": [],
  "recommended_candidate_keys": ["option-a"],
  "completed_at": "<ISO8601 时间>"
}
```

要点:`task_digest` 与每个 `source_hash` **原样从 bundle 回填**,不要自己算——importer 会用它做 stale 校验,
不一致整份会被 quarantine。

## 导回

```bash
make import-result TASK=<task.json> RESULT=<result.json> STORE=<candidate store 目录>
```

(`task.json` = bundle 里的 `task` 部分。)importer 会做 schema + stale + 大小/重复校验,通过才落 candidate。
输出 `written=N` 即成功;`quarantined` 表示 result 与 task 不匹配,需检查回填的 digest/hash。

## 拒译/无法翻译时

不要编造,也不要把原文当译文塞过去。把该 segment 的译文留空字符串(QA 会判 `empty_translation`),
或在 `result.findings` 里记一条说明,让后续 review/repair 处理。**宁可空,不要假。**
