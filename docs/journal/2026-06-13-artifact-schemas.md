# 2026-06-13 业务工件 JSON Schema 落地(P0.3)

## 背景

新架构第一块基石(issue #35):七类业务工件的 schema 在 system-design §5/§6/§9
定稿(含 #21 修订的 candidate 幂等键),但仅存在于文档,无机器可校验的真相源。

## 改动

- `tasks/translation/schemas/`:document-revision / candidate(v2) / evaluation /
  document-version / annotation / task / result 七个自包含 Draft 2020-12 schema,
  身份字段(document/revision/segment/candidate id)带格式约束。
- `src/core/artifact_schemas.py`:schema 加载与校验、canonical digest、
  §5.4 stale-result 防护(`check_result_against_task`)、§9.2 candidate 幂等键派生
  (`candidate_id_for`)、单文件 CLI 校验入口。
- 15 个测试:七类 valid fixture、schema_version/必填/多余字段/身份格式拒绝、
  round-trip digest 稳定、stale-result 三种失配、幂等键已知向量与跨执行独立。

## 决策

- schema 自包含(不跨文件 $ref),与 agent/schemas 同策略,规避 resolver 复杂度。
- candidate 幂等键字段必填但可空(human/legacy 候选),由 producer.type 区分。
- 后续 P0.4 fixture、P0.5 adapter、P0.6 importer 直接消费本模块。

## 验证

pytest 全量 130 绿(基线 115→130);CLI 对 task fixture 校验通过。
