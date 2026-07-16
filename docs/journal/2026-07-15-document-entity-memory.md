# 2026-07-15 篇内首次译名记忆

## 动机

翻译完成后再让 LLM 通读源/译文抽实体会多一次调用，且只能事后修正；未入实体库的新名字在同一篇的顺序批次中仍可能漂移。目标收缩为容易被低成本模型遵守的篇内一致性：跨篇可以不同，本文第一次实际译法一经采用便锁定。

## 决策

- 不做全文预读，也不做翻译后的第二次 LLM 收割。
- Context Pack 已批准实体优先；否则本文首次观察的 `source -> target` 胜出。
- 后续观察若不同，只纠正当前批译文；variant 不进入下一批上下文。
- API 使用临时 `T/E` 行协议在同一次调用里返回译文和本段实际名字。
- Agent 译文仍只写 `zh.tsv`，篇内锁定表使用可选两列 `names.tsv`，每篇独立。
- 首次译名复用 Result info finding 留证，发布后只进入 entity-review candidate；未经审核不跨篇生效。

## 验证

- reducer 覆盖 first-wins、Context Pack 优先、冲突只改当前段和幻觉观察过滤。
- OpenRouter mock 覆盖下一调用只收到 canonical target。
- Agent finish 覆盖 `names.tsv` 自动组装、源译证据校验、approved target 兜底且不重复送审。
