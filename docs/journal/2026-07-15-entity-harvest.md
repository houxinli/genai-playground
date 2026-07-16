# 2026-07-15 OpenRouter 翻译后实体收割

## 动机

实体库与 review 闸门已经存在，但 OpenRouter 自动翻译完成后不会主动沉淀本篇出现的人名与专名。
执行器可能在同一篇里产生多个译名，后续篇章也无法复用已确认译名；直接把模型建议写入 Context Pack
又会绕过人工审核并污染知识库。

## 改动

- `entity_harvest.py` 从本篇源文/译文对照中解析结构化实体建议，拒绝冲突 target 与源文不存在的提案。
- 明确 variants 只归一本篇 Result；归一后的文本仍走 Candidate、QA、selection 与 DocumentVersion。
- 已有 approved/locked Context Pack target 优先于模型建议。
- 跨篇实体复用既有 `entity_review`：自动提案先落 `candidate + pending review`，人工批准后才进入 Context Pack。
- `translate-user` 的 OpenRouter auto 路线默认接入实体 review queue，可通过空 `ENTITY_REVIEW_QUEUE` 关闭额外调用。
- resolver 排除未审核 candidate，防止待审提案提前约束后续翻译。

## 验证

- 实体收割、实体库、review 与 translate-user 定向测试通过。
- 全量 `pytest tasks/translation/src -q`：439 项通过。
- `make docs-drift`、`make agent-validate` 通过。

## 后续

- 人工审核现有 creator-scope 提案并播种已确认译名。
- 后续把 agent prepare/finish 路线的抽取产物也统一接入同一 review 队列，不自动二次调用远程模型。
