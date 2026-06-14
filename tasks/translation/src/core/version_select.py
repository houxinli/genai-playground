#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保守择优:recommend_selection / build_document_version / render_version。

硬规则 QA 只做 gate 和证据,不作语义质量排名。判定基于重算后的 blocking finding 集合
(比较键 = evaluator.name, version, severity, code),自动替换仅在 challenger 通过全部
blocking gate 且证据可比时发生;无法证明严格改善时保留 incumbent。判定对候选输入顺序无关。
设计见 system-design §2.5/§2.6/§6.4 与 issue #50 收敛判定表。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .artifact_schemas import canonical_digest, validate_artifact
    from .renderer import render_bilingual
except ImportError:  # core/ 在 sys.path 上
    from artifact_schemas import canonical_digest, validate_artifact
    from renderer import render_bilingual


POLICY_ID = "conservative-select-v1"
_VERSION_ID_HEX = 40


class UnresolvedSelectionError(Exception):
    """build_document_version 在存在无 selection 的 segment(无 incumbent 且未决)时抛出。
    携带未决 segment id,调用方据此产出 recommendation report 而非建版。"""

    def __init__(self, segment_ids: List[str]):
        self.segment_ids = segment_ids
        super().__init__(f"无法建版:{len(segment_ids)} 个 segment 未决: {segment_ids}")


def _rule_evaluation(candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """取候选唯一的、确实绑定到该候选的 deterministic rule evaluation;0 条或多于 1 条 → None
    (不可比较)。强校验 evaluation.candidate_id == candidate.candidate_id,杜绝失败候选借用其它
    候选的 pass evaluation 被错误自动替换。"""
    cid = candidate["candidate_id"]
    rules = [
        e
        for e in candidate.get("evaluations", [])
        if e.get("evaluator", {}).get("type") == "rule" and e.get("candidate_id") == cid
    ]
    return rules[0] if len(rules) == 1 else None


def _evaluator_identity(evaluation: Dict[str, Any]) -> tuple:
    ev = evaluation["evaluator"]
    return (ev["name"], ev["version"])


def _blocking_keys(evaluation: Dict[str, Any]) -> frozenset:
    """error-severity finding 的比较键集合 (name, version, severity, code)。"""
    name, version = _evaluator_identity(evaluation)
    return frozenset(
        (name, version, f["severity"], f["code"])
        for f in evaluation.get("findings", [])
        if f["severity"] == "error"
    )


def _verdict_consistent(evaluation: Dict[str, Any]) -> bool:
    """verdict 必须与重算 blocking 自洽:pass⇔无 blocking,fail⇔有 blocking。"""
    has_blocking = bool(_blocking_keys(evaluation))
    return evaluation.get("verdict") == ("fail" if has_blocking else "pass")


def _decision(
    segment_id: str,
    outcome: str,
    reason_code: str,
    selected_candidate_id: Optional[str],
    incumbent_candidate_id: Optional[str],
    evaluation_ids: List[str],
) -> Dict[str, Any]:
    return {
        "segment_id": segment_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "selected_candidate_id": selected_candidate_id,
        "incumbent_candidate_id": incumbent_candidate_id,
        "evaluation_ids": sorted(set(evaluation_ids)),
        "selected_by": "policy",
    }


def _recommend_segment(segment: Dict[str, Any]) -> Dict[str, Any]:
    segment_id = segment["segment_id"]
    incumbent = segment.get("incumbent")
    challengers = list(segment.get("challengers", []))
    incumbent_id = incumbent["candidate_id"] if incumbent else None

    participants = ([incumbent] if incumbent else []) + challengers
    evals = {c["candidate_id"]: _rule_evaluation(c) for c in participants}
    all_eval_ids = [e["evaluation_id"] for e in evals.values() if e is not None]

    def review(reason_code: str) -> Dict[str, Any]:
        # incumbent 存在 → 保留;不存在 → 无 selection(未决)
        return _decision(segment_id, "review_required", reason_code, incumbent_id, incumbent_id, all_eval_ids)

    # 证据可比性:每个参与候选恰有一条 rule evaluation
    if any(e is None for e in evals.values()):
        return review("incomparable_evaluations")
    # 同一 (evaluator name, version) 才能做集合比较
    if len({_evaluator_identity(e) for e in evals.values()}) > 1:
        return review("evaluator_mismatch")
    # verdict 必须与 blocking 自洽,不只信输入 verdict
    if any(not _verdict_consistent(e) for e in evals.values()):
        return review("verdict_blocking_inconsistent")

    def passed(cand: Dict[str, Any]) -> bool:
        return not _blocking_keys(evals[cand["candidate_id"]])

    passing_challengers = [c for c in challengers if passed(c)]

    if incumbent is None:
        if len(passing_challengers) == 1:
            cid = passing_challengers[0]["candidate_id"]
            return _decision(
                segment_id, "select_challenger", "initial_single_passing_candidate",
                cid, None, all_eval_ids,
            )
        if len(passing_challengers) >= 2:
            return _decision(
                segment_id, "review_required", "multiple_passing_distinct_texts",
                None, None, all_eval_ids,
            )
        return _decision(segment_id, "review_required", "no_passing_candidate", None, None, all_eval_ids)

    if passed(incumbent):
        if not passing_challengers:
            reason = "incumbent_passes_no_challenger" if not challengers else "incumbent_passes_challenger_not_better"
            return _decision(segment_id, "keep_incumbent", reason, incumbent_id, incumbent_id, all_eval_ids)
        return review("multiple_passing_distinct_texts")

    # incumbent fail
    if len(passing_challengers) == 1:
        cid = passing_challengers[0]["candidate_id"]
        return _decision(
            segment_id, "select_challenger", "incumbent_failed_single_passing_challenger",
            cid, incumbent_id, all_eval_ids,
        )
    if len(passing_challengers) >= 2:
        return review("incumbent_failed_multiple_passing_challengers")
    return review("incumbent_failing_no_challenger" if not challengers else "unresolved_failing_candidates")


def recommend_selection(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """逐 segment 聚合判定(对候选顺序无关),产出保守择优建议。不写盘。

    segments: 每项 {segment_id, incumbent: None|{candidate_id, evaluations:[...]},
    challengers: [{candidate_id, evaluations:[...]}, ...]}。challenger 为内容寻址去重后的
    不同候选(distinct candidate_id ⇒ distinct text)。
    返回逐 segment dict:outcome / reason_code / selected_candidate_id(None=无可渲染选择)/
    incumbent_candidate_id / evaluation_ids / selected_by。
    """
    return [_recommend_segment(seg) for seg in segments]


def _version_id(payload: Dict[str, Any]) -> str:
    return "version_" + canonical_digest(payload)[:_VERSION_ID_HEX]


def build_document_version(
    revision: Dict[str, Any],
    recommendations: List[Dict[str, Any]],
    decided_by: str,
    created_at: str,
    *,
    parent_version_id: Optional[str] = None,
    knowledge_snapshot_id: Optional[str] = None,
    policy_id: str = POLICY_ID,
) -> Dict[str, Any]:
    """由 recommendation 创建不可变 DocumentVersion v2。

    要求 recommendations 覆盖 revision 全部 segment 且每段有可落地 selection;任一 segment 未决
    (无 incumbent 的 review_required/无 pass)→ 抛 UnresolvedSelectionError,由调用方取 report。
    created_at 由调用方传入以保持本函数确定性(version_id 内容寻址、同选择幂等)。status 一律 draft
    (版本创建≠发布)。
    """
    by_segment = {r["segment_id"]: r for r in recommendations}
    revision_segments = [s["segment_id"] for s in revision["segments"]]

    missing = [sid for sid in revision_segments if sid not in by_segment]
    if missing:
        raise UnresolvedSelectionError(missing)
    unresolved = [sid for sid in revision_segments if by_segment[sid]["selected_candidate_id"] is None]
    if unresolved:
        raise UnresolvedSelectionError(unresolved)

    selections: Dict[str, str] = {}
    selection_decisions: Dict[str, Any] = {}
    for sid in revision_segments:
        rec = by_segment[sid]
        selections[sid] = rec["selected_candidate_id"]
        selection_decisions[sid] = {
            "selected_by": rec["selected_by"],
            "outcome": rec["outcome"],
            "reason_code": rec["reason_code"],
            "incumbent_candidate_id": rec["incumbent_candidate_id"],
            "evaluation_ids": rec["evaluation_ids"],
        }

    content = {
        "schema_version": 2,
        "document_id": revision["document_id"],
        "revision_id": revision["revision_id"],
        "parent_version_id": parent_version_id,
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "selections": selections,
        "selection_decisions": selection_decisions,
        "decision": {"policy_id": policy_id, "created_by": decided_by},
        "status": "draft",
        "created_at": created_at,
    }
    # version_id 覆盖除自身外的全部不可变 payload(含 created_at/policy_id/created_by),保证
    # id ↔ payload 一一对应,杜绝同 ID 不同 payload 写 ArtifactStore 时的 fatal 冲突。
    version = {"version_id": _version_id(content), **content}
    errors = validate_artifact("document-version", version)
    if errors:
        raise ValueError(f"DocumentVersion v2 校验失败: {errors}")
    return version


def render_version(
    revision: Dict[str, Any],
    version: Dict[str, Any],
    candidates_by_id: Dict[str, Dict[str, Any]],
    source_text: str,
) -> str:
    """从显式 version 渲染 bilingual(复用 #37 renderer)。

    source_text 是 renderer 固有所需的原始来源文本(revision 不保存),由调用方提供。
    """
    if version["revision_id"] != revision["revision_id"]:
        raise ValueError(
            f"version.revision_id {version['revision_id']} != revision {revision['revision_id']}"
        )
    translations: Dict[str, str] = {}
    for segment_id, candidate_id in version["selections"].items():
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            raise KeyError(f"missing candidate {candidate_id} for segment {segment_id}")
        # 绕过 Store 时 candidates_by_id 可能装错候选;核对身份字段,杜绝把别的 revision/segment
        # 的译文渲染进该句。
        if candidate["revision_id"] != revision["revision_id"]:
            raise ValueError(
                f"candidate {candidate_id} revision {candidate['revision_id']} "
                f"!= revision {revision['revision_id']}"
            )
        if candidate["segment_id"] != segment_id:
            raise ValueError(
                f"candidate {candidate_id} segment {candidate['segment_id']} != selection key {segment_id}"
            )
        translations[segment_id] = candidate["text"]
    return render_bilingual(revision, source_text, translations)
