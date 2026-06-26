# 翻译执行器指令（agent 中立）

> 本文件是**所有翻译执行器的单一真相源**：Claude Code、Cursor+Grok、Codex 等编码 agent 都按这一份
> 执行,各自的 skill/rule 只是指向本文件的薄壳,不重复翻译规则。

## 角色

你是一个**日→中翻译执行器**。给定一个 job bundle,你逐段翻译,优先产出 `<source_id>.zh.tsv`
(`段号<TAB>译文`)。`result.json` 是规范业务工件,但应由 harness 从 job + TSV 机械组装,不要由
Agent/API/人工执行器手写身份字段。你不做选择、不改发布版本——只产出候选译文输入。

## 输入:job bundle

由 `make translate-bundle` 或 `make export-job` 生成(两者都需传 `STORE=`):生成 bundle 的**同时**把源
DocumentRevision 幂等写入该 store。这是 `import-result` 闭环的前置——import 端的 integrity gate 要求同文档
revision shard 已存在,否则整份 quarantine。对全新文档也因此一步到位,无需单独入库步骤。bundle 结构:

```json
{
  "task": { "task_id": "...", "task_digest": "...", "segment_ids": [...],
            "source_hashes": { "<segment_id>": "<hash>" }, ... },
  "task_digest": "...",
  "segments": [ { "segment_id": "...", "kind": "body|metadata.*", "source_text": "<日文>" }, ... ],
  "context_pack": { "terminology": [...], "entities": [...], "neighbors": { "<segment_id>": {"prev": "...", "next": "..."} } }
}
```

## Context Pack(硬约束 + 上下文)

`bundle.context_pack` 是本 job 自包含的上下文,**翻译时必须读取并遵守**(可能为空):

- **`entities`**:作用域人名/专名约束,形如 `{source, target, aliases?, forbidden?, scope?}`。
  - `target` 是该名的**中文标准译名**——出现该名(及 `aliases`)时**一律**译成 `target`,全文一致。
  - `forbidden` 是**禁止使用的坏译**,绝不可出现。
- **`terminology`**:术语约束 `{source, target, note?}`,同名术语统一译为 `target`。
- **`neighbors`**:每个 body segment 的前/后一条**源句**,仅供你理解上下文(代词指代、语气衔接);**不要翻译或输出 neighbors 本身**。

`entities`/`terminology` 的优先级高于你的自由判断;与下面通用规则冲突时以 context_pack 为准。

## 翻译规则（复用现有流水线约定）

- **逐段对照、禁止省略**:`segments` 里每一个 segment 都必须有对应译文,不合并、不拆分、不调序、不跳过。
- **引号样式**:沿用原文的方引号「」『』,不要改成中文引号。
- **标点**:中文用恰当的中文标点;不要因为原文没有句号就省略。
- **拟声词/感叹词**:重复时控制在 5 次以内。
- **专名/人名一致**:同一专名全文译法一致;**以 `bundle.context_pack.entities`/`terminology` 为准**(target=标准译名,绝不用 forbidden 坏译)。
- **metadata.* segment**(title/caption/excerpt/series.title/tags):只译内容值。tags 译成 `原词 / 中文`
  并保留 `[]` 与逗号。
- **只输出译文**:不要加解释、注释、Markdown 包裹或额外空行。
- **假名残留**:译文不得残留日文假名(被翻成语气词/拟声词或删去);单独的 っ、ん 等同理。
- **不要把原文当译文**:逐段确认是中文译文,不是照抄日文(否则会被 QA 判 `same_as_source`)。

## 输出:zh.tsv(执行器唯一手写产物)

对 bundle 的每个 segment 产一行：

```text
0<TAB>第一段中文译文
1<TAB>第二段中文译文
2<TAB>
```

要点：

- 段号是 `bundle.segments` 的 0-based index。
- 译文按 TAB 后原样保留；无法翻译时 TAB 后留空。
- full run 必须覆盖全部 segment index；patch run 只覆盖 patch scope,发布前由 harness 叠加到 base 译文。
- 不要抄 `segment_id` / `source_hash` / `task_digest`；这些由 harness 从 job 回填。

## 派生:result.json

Harness 用 `tasks/translation/src/core/result_assemble.py` / `make translate-assemble` 把 TSV 组装成
`result.json`(符合 `schemas/result.schema.json`):

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

要点:`task_digest` 与每个 `source_hash` **由 harness 原样从 bundle 回填**——importer 会用它做 stale 校验,
不一致整份会被 quarantine。执行器不要自己算、不要手写。

## 导回

```bash
make import-result TASK=<task.json> RESULT=<result.json> STORE=<candidate store 目录>
```

(`task.json` = bundle 里的 `task` 部分。)importer 会做 schema + stale + 大小/重复校验,通过才落 candidate。
输出 `written=N` 即成功;`quarantined` 表示 result 与 task 不匹配,需检查回填的 digest/hash。

## 拒译/无法翻译时

不要编造,也不要把原文当译文塞过去。把该 segment 在 TSV 中写成 `段号<TAB>` 空译文
(QA 会判 `empty_translation`),让后续 review/repair 处理。**宁可空,不要假。**
