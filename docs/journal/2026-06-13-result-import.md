# 2026-06-13 result 导入(import-result,task/result 协议落地端)

## 背景

API/Agent 执行器产出的 Result 需要可靠地落成 Candidate(issue #44):这是"用新 harness
(本地 agent/Grok 4)提升翻译"目标的 keystone——外部执行结果由此进入 candidate 模型。
gh-35 已备好 candidate_id_for 与 check_result_against_task。

## 改动

- `result_import.py`:
  - `build_candidates_from_result`:校验 task/result schema → §5.4 stale 校验
    (task_id/task_digest/schema/segment/source_hash)→ 任一不符抛 QuarantineError(整份不导入)。
  - 通过后按 candidate_id_for(task_digest, result_digest, key, segment_id) 派生 id,
    producer 取自 result(harness 名回填 producer.harness),provenance 带幂等三字段。
  - `import_result`:写入复用 legacy_import 的幂等 + 冲突检测 + 原子写;返回报告或 quarantine。
- 6 测试:happy path、幂等、stale source_hash 隔离不写、task_digest 失配隔离、
  跨执行独立 candidate、同 result 同 id。

## 验证

pytest 全量 168 绿(基线 162→168)。

## 意义

至此 task/result 协议的**导入端**完成;下一步 #46 export-job 补**生成端**,
之后即可接本地 agent / Grok 4 的薄适配(P2.2)对 momizi813 跑通。
