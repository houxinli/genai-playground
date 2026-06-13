#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""candidate QA 评估:对单个 Candidate 跑确定性硬规则,产出绑定的 Evaluation。

复用 qa_gate 的逐行规则(空译文/失败标记/拒绝模板/与原文相同/假名残留),作为 compare/select
的打分基础。规则确定性 → 同一 candidate+同一 evaluator 版本得到稳定 Evaluation。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from .artifact_schemas import canonical_dumps, validate_artifact
    from .qa_gate import FAILURE_MARKERS, REFUSAL_MARKERS, _contains_kana
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.artifact_schemas import canonical_dumps, validate_artifact
    from core.qa_gate import FAILURE_MARKERS, REFUSAL_MARKERS, _contains_kana

EVALUATOR_NAME = "deterministic-qa"
EVALUATOR_VERSION = "candidate-qa-v1"
_FALLBACK_CREATED_AT = "1970-01-01T00:00:00Z"


def _findings(source_text: str, text: str) -> List[Dict[str, Any]]:
    """与 qa_gate 对齐的硬规则 findings(均为 error 级)。"""
    findings: List[Dict[str, Any]] = []
    stripped = text.strip()
    if not stripped:
        findings.append({"code": "empty_translation", "severity": "error", "message": "译文为空"})
        return findings  # 空译文无需再查其它
    for marker in FAILURE_MARKERS:
        if marker in text:
            findings.append({"code": "failure_marker", "severity": "error",
                             "message": f"译文含失败标记: {marker}", "evidence": marker})
    for marker in REFUSAL_MARKERS:
        if marker in text:
            findings.append({"code": "refusal_marker", "severity": "error",
                             "message": f"译文含拒绝模板: {marker}", "evidence": marker})
    if stripped == source_text.strip():
        findings.append({"code": "same_as_source", "severity": "error", "message": "译文与原文完全相同"})
    if _contains_kana(text):
        findings.append({"code": "kana_residue", "severity": "error", "message": "译文残留假名"})
    return findings


def evaluate_candidate(
    candidate: Dict[str, Any], source_text: str, created_at: str = _FALLBACK_CREATED_AT
) -> Dict[str, Any]:
    """对一个 Candidate 跑硬规则,返回 schema 合法的 Evaluation(verdict + findings)。"""
    findings = _findings(source_text, candidate["text"])
    verdict = "fail" if any(f["severity"] == "error" for f in findings) else "pass"
    evaluation_id = "eval_" + hashlib.sha256(
        canonical_dumps({
            "candidate_id": candidate["candidate_id"],
            "evaluator": EVALUATOR_VERSION,
            "findings": findings,
        }).encode("utf-8")
    ).hexdigest()[:16]
    evaluation = {
        "schema_version": 1,
        "evaluation_id": evaluation_id,
        "candidate_id": candidate["candidate_id"],
        "evaluator": {"type": "rule", "name": EVALUATOR_NAME, "version": EVALUATOR_VERSION},
        "verdict": verdict,
        "findings": findings,
        "scores": {},
        "created_at": created_at,
    }
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
