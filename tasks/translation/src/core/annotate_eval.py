#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注解候选的硬规则评估(#174 陪读)。

注解 candidate 的 text = 「注解后的源文行」——源文行插入若干 `(…)` 注解段而成。
核心不变量:**把注解行中的括号段剥掉后必须逐字等于源文**(注解只能插括号,不得增删改原文字符)。
这是确定性机械检查,与翻译的 candidate_eval(假名残留/拒绝模板)按 task_type 分开。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .artifact_schemas import evaluation_id_for, validate_artifact, validate_candidate_identity
    from .source_identity import _source_hash  # 与翻译评估同一哈希口径
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.artifact_schemas import evaluation_id_for, validate_artifact, validate_candidate_identity
    from core.source_identity import _source_hash

EVALUATOR_NAME = "annotate-rule-eval"
EVALUATOR_VERSION = "1"

# 注解括号:全角/半角圆括号都接受(执行器可能混用)。
_PAIRS = {"(": ")", "（": "）"}
_OPEN = set(_PAIRS)
_CLOSE = set(_PAIRS.values())

_FINDING_MESSAGES = {
    "skeleton_mismatch": "剥掉注解括号后与源文不一致(注解只能插入括号,不得增删改原文)",
    "unbalanced_parens": "注解括号不配对",
    "multiline_annotation": "注解行含换行/TAB(必须单行,TSV 契约)",
    "empty_annotation_line": "注解行为空(未注解的段应原样抄源文)",
}


def strip_annotations(text: str) -> str:
    """剥掉顶层括号段(含嵌套),返回骨架。括号不配对时返回 None。"""
    out: List[str] = []
    stack: List[str] = []
    for ch in text:
        if ch in _OPEN:
            stack.append(_PAIRS[ch])
        elif ch in _CLOSE:
            if not stack or ch != stack[-1]:
                return None
            stack.pop()
        elif not stack:
            out.append(ch)
    return None if stack else "".join(out)


def _group_end(text: str, start: int) -> Optional[int]:
    """返回 start 处完整括号组之后的位置；括号不配对时返回 None。"""
    stack = [_PAIRS[text[start]]]
    for index in range(start + 1, len(text)):
        ch = text[index]
        if ch in _OPEN:
            stack.append(_PAIRS[ch])
        elif ch in _CLOSE:
            if ch != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return index + 1
    return None


def _preserves_source(source_text: str, annotated_text: str) -> bool:
    """只允许在原文字符之间插入完整括号组，原文自身括号也必须逐字保留。"""
    pending = [(0, 0)]
    seen = set()
    while pending:
        source_index, annotated_index = pending.pop()
        if (source_index, annotated_index) in seen:
            continue
        seen.add((source_index, annotated_index))
        if annotated_index == len(annotated_text):
            if source_index == len(source_text):
                return True
            continue
        if (
            source_index < len(source_text)
            and source_text[source_index] == annotated_text[annotated_index]
        ):
            pending.append((source_index + 1, annotated_index + 1))
        if annotated_text[annotated_index] in _OPEN:
            end = _group_end(annotated_text, annotated_index)
            if end is not None:
                pending.append((source_index, end))
    return False


def _findings(source_text: str, text: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    def err(code: str) -> None:
        findings.append({"severity": "error", "code": code, "message": _FINDING_MESSAGES[code]})

    if not text.strip():
        err("empty_annotation_line")
        return findings
    if "\n" in text or "\t" in text:
        err("multiline_annotation")
        return findings
    if strip_annotations(text) is None:
        err("unbalanced_parens")
        return findings
    if not _preserves_source(source_text, text):
        err("skeleton_mismatch")
    return findings


def evaluate_annotation_candidate(
    candidate: Dict[str, Any], source_text: str, created_at: str = "1970-01-01T00:00:00Z"
) -> Dict[str, Any]:
    """对一个注解 Candidate 跑硬规则,返回 schema 合法的 Evaluation(与翻译评估同构)。"""
    schema_errors = validate_artifact("candidate", candidate)
    if schema_errors:
        raise ValueError(f"candidate schema invalid: {schema_errors}")
    identity_errors = validate_candidate_identity(candidate)
    if identity_errors:
        raise ValueError(f"candidate identity invalid: {identity_errors}")
    if _source_hash(source_text) != candidate["source_hash"]:
        raise ValueError(
            f"source_text hash mismatch for candidate {candidate['candidate_id']}"
        )
    findings = _findings(source_text, candidate["text"])
    verdict = "fail" if any(f["severity"] == "error" for f in findings) else "pass"
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
