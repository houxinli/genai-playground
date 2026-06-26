# .agents/skills/translate

## 作用

统一日译中执行 skill。它定义本地 Agent 如何读取 workspace、产出 `<source_id>.zh.tsv`、恢复断点并交给 harness finish/publish。

## 直接子项

- `SKILL.md`：skill 真相源，包含恢复规则、TSV 格式、full/patch run 语义和结束汇报要求。

## 维护规则

- 翻译业务规则优先引用 `tasks/translation/docs/executor-instructions.md`。
- 本目录只保留执行器工作流，不手写 `result.json` 规则实现。
