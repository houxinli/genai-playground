#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""篇内实体记忆：首次译名锁定，后续批次只携带 canonical target。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from . import entity_review
    from .entity_store import EntityStore
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import entity_review
    from core.entity_store import EntityStore


ENTITY_FINDING_CODE = "entity_first_use"


def parse_executor_response(response: str) -> Tuple[str, List[Dict[str, str]]]:
    """解析 API 的简单行协议：首行 ``T<TAB>译文``，随后零到多行 ``E<TAB>源名<TAB>译名``。

    所有响应都必须使用 T/E 协议，避免 API 路线静默跳过篇内名字记忆。
    """
    content = response.strip("\r\n")
    lines = content.splitlines()
    if not lines or not lines[0].startswith("T\t"):
        raise ValueError("响应首行必须是 `T<TAB>译文`")
    translation = lines[0].split("\t", 1)[1].strip()
    observations: List[Dict[str, str]] = []
    for line_number, line in enumerate(lines[1:], 2):
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] != "E":
            raise ValueError(f"响应第 {line_number} 行必须是 `E<TAB>日文名<TAB>中文名`")
        source, target = parts[1].strip(), parts[2].strip()
        if not source or not target:
            raise ValueError(f"响应第 {line_number} 行实体 source/target 不得为空")
        observations.append({"source": source, "target": target})
    return translation, observations


def context_targets(context_pack: Dict[str, Any]) -> Dict[str, str]:
    """取已批准 Context Pack 实体；调用方可在其上追加本文首次译名。"""
    return {entity["source"]: entity["target"] for entity in context_pack.get("entities", [])}


def apply_observations(
    source_text: str,
    translation: str,
    observations: List[Dict[str, str]],
    locked_targets: Dict[str, str],
) -> Tuple[str, List[Dict[str, str]], List[Dict[str, str]]]:
    """按出现顺序合并本段观察；已锁定 target 永不改变，冲突只纠正当前译文。

    ``locked_targets`` 原地追加首次观察。只接受 source 确实在本段源文、target 确实在本段译文中的
    记录，防止模型把提示里的其它名字重新报告进本文记忆。
    """
    first_uses: List[Dict[str, str]] = []
    conflicts: List[Dict[str, str]] = []
    for observation in observations:
        source = observation["source"].strip()
        observed_target = observation["target"].strip()
        if not source or not observed_target or source not in source_text or observed_target not in translation:
            continue
        canonical = locked_targets.get(source)
        if canonical is None:
            locked_targets[source] = observed_target
            first_uses.append({"source": source, "target": observed_target})
            continue
        if observed_target == canonical:
            continue
        if canonical not in translation or observed_target not in canonical:
            translation = translation.replace(observed_target, canonical)
        conflicts.append({"source": source, "target": canonical, "observed_target": observed_target})
    return translation, first_uses, conflicts


def entity_finding(source: str, target: str, segment_id: str, line: int) -> Dict[str, Any]:
    """把本文首次译名装进 Result 既有 findings，避免扩展 Result schema。"""
    evidence = json.dumps(
        {"source": source, "target": target, "segment_id": segment_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "code": ENTITY_FINDING_CODE,
        "severity": "info",
        "message": f"本篇首次译名锁定：{source} => {target}",
        "evidence": evidence,
        "line": line,
    }


def entities_from_result(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 Result findings 恢复可送 entity-review 的最小提案。"""
    entities: List[Dict[str, Any]] = []
    seen = set()
    for finding in result.get("findings", []):
        if finding.get("code") != ENTITY_FINDING_CODE or not finding.get("evidence"):
            continue
        try:
            evidence = json.loads(finding["evidence"])
        except (TypeError, ValueError):
            continue
        source = str(evidence.get("source", "")).strip()
        target = str(evidence.get("target", "")).strip()
        if not source or not target or source in seen:
            continue
        seen.add(source)
        entities.append({
            "source": source,
            "target": target,
            "type": "person",
            "confidence": 1.0,
            "variants": [],
        })
    return entities


def parse_locked_names_tsv(content: str) -> Dict[str, str]:
    """解析 Agent 的两列篇内锁定表；同 source 出现不同 target 时拒绝。"""
    locked: Dict[str, str] = {}
    for line_number, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            raise ValueError(f"names.tsv 第 {line_number} 行应为 `日文名<TAB>中文名`")
        source, target = parts[0].strip(), parts[1].strip()
        if not source or not target:
            raise ValueError(f"names.tsv 第 {line_number} 行 source/target 不得为空")
        previous = locked.get(source)
        if previous is not None and previous != target:
            raise ValueError(
                f"names.tsv 第 {line_number} 行违反 first-wins：{source!r} 已锁定为 {previous!r}，"
                f"不得再写 {target!r}"
            )
        locked[source] = target
    return locked


def apply_locked_names(
    bundle: Dict[str, Any],
    translations: Dict[int, str],
    local_targets: Dict[str, str],
) -> Tuple[Dict[int, str], List[Dict[str, Any]]]:
    """Agent finish 时让 approved target 覆盖冲突本地记录，并为真实首次用法生成 findings。"""
    normalized = dict(translations)
    approved = context_targets(bundle.get("context_pack", {}))
    findings: List[Dict[str, Any]] = []
    for source, observed_target in local_targets.items():
        canonical = approved.get(source, observed_target)
        first_index = None
        source_seen = False
        for index, segment in enumerate(bundle["segments"]):
            if source not in segment["source_text"]:
                continue
            source_seen = True
            text = normalized.get(index, "")
            if observed_target not in text:
                continue
            if first_index is None:
                first_index = index
            if observed_target != canonical and observed_target in text:
                if canonical not in text or observed_target not in canonical:
                    normalized[index] = text.replace(observed_target, canonical)
        if source in approved:
            continue
        if not source_seen:
            raise ValueError(f"names.tsv 的 source {source!r} 未出现在本文源文")
        if first_index is None:
            raise ValueError(f"names.tsv 的 target {observed_target!r} 未出现在该 source 对应译文")
        findings.append(entity_finding(
            source,
            canonical,
            bundle["segments"][first_index]["segment_id"],
            first_index + 1,
        ))
    return normalized, findings


def enqueue_entity_reviews(
    revision: Dict[str, Any],
    entities: List[Dict[str, Any]],
    entity_store_root: Path,
    review_queue_root: Path,
) -> List[Dict[str, Any]]:
    """把本篇首次译名交给 entity-review；不自动 approve。"""
    parts = revision["document_id"].split(":")
    if len(parts) != 3:
        raise ValueError(f"document_id 形如 provider:creator:source，实得 {revision['document_id']!r}")
    provider, creator_id, _ = parts
    scope_context = {
        "provider": provider,
        "creator_id": creator_id,
        "document_id": revision["document_id"],
    }
    proposals = []
    for entity in entities:
        segment = next(
            (item for item in revision["segments"] if entity["source"] in item["source_text"]),
            None,
        )
        if segment is None:
            continue
        proposals.append(
            {
                "mention": entity["source"],
                "document_id": revision["document_id"],
                "segment_id": segment["segment_id"],
                "suggested_target": entity["target"],
                "confidence": entity["confidence"],
                "context": segment["source_text"][:80],
                "type": entity["type"],
            }
        )
    return entity_review.import_proposals(
        proposals,
        scope_context,
        EntityStore(entity_store_root),
        entity_review.ReviewQueue(review_queue_root),
    )
