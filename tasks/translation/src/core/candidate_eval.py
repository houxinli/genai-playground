#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""candidate QA 评估:对单个 Candidate 跑确定性硬规则,产出绑定的 Evaluation。

复用 qa_gate 的逐行规则(空译文/失败标记/拒绝模板/与原文相同/假名残留),作为 compare/select
的打分基础。规则确定性 → 同一 candidate+同一 evaluator 版本得到稳定 Evaluation。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from .artifact_schemas import evaluation_id_for, validate_artifact, validate_candidate_identity
    from .qa_gate import hard_rule_hits
    from .source_identity import _source_hash
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.artifact_schemas import evaluation_id_for, validate_artifact, validate_candidate_identity
    from core.qa_gate import hard_rule_hits
    from core.source_identity import _source_hash

EVALUATOR_NAME = "deterministic-qa"
# v2:same_as_source 仅对可翻译源触发(分隔符豁免)。规则集变了 → 升版,旧 fail 工件不与新 pass 同版可比(Codex #125)。
EVALUATOR_VERSION = "candidate-qa-v2"
_FALLBACK_CREATED_AT = "1970-01-01T00:00:00Z"


_FINDING_MESSAGES = {
    "empty_translation": "译文为空",
    "failure_marker": "译文含失败标记",
    "refusal_marker": "译文含拒绝模板",
    "same_as_source": "译文与原文完全相同",
    "kana_residue": "译文残留假名",
}


def _findings(source_text: str, text: str) -> List[Dict[str, Any]]:
    """硬规则 findings(均为 error 级)。规则判定走 qa_gate.hard_rule_hits(与离线 gate 同一份真相源),
    此处只把命中 code 包装成 Evaluation finding。"""
    findings: List[Dict[str, Any]] = []
    for hit in hard_rule_hits(source_text, text):
        code = hit["code"]
        evidence = hit.get("evidence")
        finding = {"code": code, "severity": "error",
                   "message": _FINDING_MESSAGES[code] + (f": {evidence}" if evidence else "")}
        if evidence:
            finding["evidence"] = evidence
        findings.append(finding)
    return findings


def evaluate_candidate(
    candidate: Dict[str, Any], source_text: str, created_at: str = _FALLBACK_CREATED_AT
) -> Dict[str, Any]:
    """对一个 Candidate 跑硬规则,返回 schema 合法的 Evaluation(verdict + findings)。

    评估前校验 candidate schema 与 source_text 哈希:错配/旧 revision 的源文本会让评估绑错,
    必须拒绝(防错误 pass 进入 compare/select)。
    """
    schema_errors = validate_artifact("candidate", candidate)
    if schema_errors:
        raise ValueError(f"candidate schema invalid: {schema_errors}")
    identity_errors = validate_candidate_identity(candidate)
    if identity_errors:
        raise ValueError(f"candidate identity invalid: {identity_errors}")
    if _source_hash(source_text) != candidate["source_hash"]:
        raise ValueError(
            f"source_text hash mismatch for candidate {candidate['candidate_id']}: "
            "评估的源文本与 candidate.source_hash 不一致"
        )

    findings = _findings(source_text, candidate["text"])
    verdict = "fail" if any(f["severity"] == "error" for f in findings) else "pass"
    # 同 id 必同内容(immutable 不变量);id 由除 evaluation_id 外全部字段派生,与 verify 共用 evaluation_id_for。
    core = {
        "schema_version": 1,
        "candidate_id": candidate["candidate_id"],
        "evaluator": {"type": "rule", "name": EVALUATOR_NAME, "version": EVALUATOR_VERSION},
        "verdict": verdict,
        "findings": findings,
        "scores": {},
        "created_at": created_at,
    }
    evaluation = {"evaluation_id": evaluation_id_for(core), **core}
    errors = validate_artifact("evaluation", evaluation)
    if errors:
        raise ValueError(f"built evaluation invalid: {errors}")
    return evaluation


def error_count(evaluation: Dict[str, Any]) -> int:
    """该 evaluation 的 error 级 finding 数(compare/select 的打分输入)。"""
    return sum(1 for f in evaluation["findings"] if f["severity"] == "error")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--source-text", required=True, help="该 candidate 对应 segment 的源文本")
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    evaluation = evaluate_candidate(candidate, args.source_text)
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    return 0 if evaluation["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
