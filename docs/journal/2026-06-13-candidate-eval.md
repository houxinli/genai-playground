# 2026-06-13 candidate QA 评估(P1.3)

## 背景

compare/select 需要给每个 candidate 打分(issue #48)。复用 qa_gate 的确定性硬规则,
对单个 candidate 产出绑定的 Evaluation。

## 改动

- `candidate_eval.py`:`evaluate_candidate(candidate, source_text)` → schema 合法 Evaluation
  (verdict pass/fail + findings),findings code 与 qa_gate 对齐(empty_translation /
  failure_marker / refusal_marker / same_as_source / kana_residue);evaluation_id 确定性派生。
  `error_count(evaluation)` 作为 compare/select 的打分输入。
- 6 测试(好/坏候选、各 finding、确定性)。

## 验证

pytest 全量 184 绿(基线 178→184)。

## 下一步

#50 compare/select + DocumentVersion + 从版本渲染:用 error_count 在 legacy 与新候选间择优,
组装版本并渲染改进的 bilingual——momizi813 demo 的最后一块机制。
