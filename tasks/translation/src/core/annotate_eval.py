#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注解候选的硬规则评估(#174 陪读)。

注解 candidate 的 text = 「注解后的源文行」——源文行插入若干 `(…)` 注解段而成。
核心不变量:**把注解行中的括号段剥掉后必须逐字等于源文**(注解只能插括号,不得增删改原文字符)。
这是确定性机械检查,与翻译的 candidate_eval(假名残留/拒绝模板)按 task_type 分开。
"""

from __future__ import annotations

from typing import Any, Dict, List

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
_OPEN = {"(", "("}
_CLOSE = {")", ")"}

_FINDING_MESSAGES = {
    "skeleton_mismatch": "剥掉注解括号后与源文不一致(注解只能插入括号,不得增删改原文)",
    "unbalanced_parens": "注解括号不配对",
    "multiline_annotation": "注解行含换行/TAB(必须单行,TSV 契约)",
    "empty_annotation_line": "注解行为空(未注解的段应原样抄源文)",
}


def strip_annotations(text: str) -> str:
    """剥掉顶层括号段(含嵌套),返回骨架。括号不配对时返回 None。"""
    out: List[str] = []
    depth = 0
    for ch in text:
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            if depth == 0:
                return None  # 多余的闭括号
            depth -= 1
        elif depth == 0:
            out.append(ch)
    if depth != 0:
        return None  # 未闭合
    return "".join(out)


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
    skeleton = strip_annotations(text)
    if skeleton is None:
        err("unbalanced_parens")
        return findings
    # 源文自身可能含括号:剥源文括号后同口径比对(注解行剥完 = 源文剥完 才算骨架一致——
    # 源文括号内的文字也在注解行里原样保留,两边同剥不影响判定)。
    src_skeleton = strip_annotations(source_text)
    if src_skeleton is None:
        src_skeleton = source_text  # 源文括号不配对(罕见),退化为原文比对
        skeleton_cmp = text
    else:
        skeleton_cmp = skeleton
    if skeleton_cmp != src_skeleton:
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
