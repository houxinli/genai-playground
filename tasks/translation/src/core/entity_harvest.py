#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""翻译后 LLM 专名收割：归一本篇候选，并把跨篇提案送入既有 entity-review 闸门。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

try:
    from . import entity_review
    from .entity_store import EntityStore
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import entity_review
    from core.entity_store import EntityStore


_ENTITY_TYPES = {"person", "org", "place", "term"}
_EXTRACT_SYS = (
    "你是日中翻译的专名校对。下面给你一篇小说的若干「日文源 / 中文译」对照行。"
    "请找出其中的人名、角色名和专有名词；不要收普通名词、拟声词、身体部位、服饰或道具。"
    "每项输出 source(日文原写法)、target(全篇统一的中文译名)、type(person/org/place/term)、"
    "confidence(0到1)，以及 variants(译文中出现过、需要替换成 target 的其它中文写法)。"
    "只输出 JSON 数组，例如 "
    '[{"source":"カルア","target":"卡尔亚","type":"person","confidence":0.9,'
    '"variants":["卡露亚"]}]。没有专名就输出 []，不要解释。'
)


def build_extract_messages(
    revision: Dict[str, Any],
    translations_by_segment: Dict[str, str],
    max_pairs: int = 120,
) -> List[Dict[str, str]]:
    """组装抽取请求，只携带有译文的正文源/译对照。"""
    pairs = []
    for segment in revision["segments"]:
        translation = translations_by_segment.get(segment["segment_id"], "")
        if translation and segment.get("kind") == "body":
            pairs.append(f"{segment['source_text']}  /  {translation}")
    return [
        {"role": "system", "content": _EXTRACT_SYS},
        {"role": "user", "content": "\n".join(pairs[:max_pairs])},
    ]


def parse_llm_entities(response: str) -> List[Dict[str, Any]]:
    """解析 LLM JSON 数组；同一 source 给出冲突 target 时整项丢弃。"""
    if not response:
        return []
    match = re.search(r"\[.*\]", response, re.S)
    if not match:
        return []
    try:
        payload = json.loads(match.group(0))
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, list):
        return []

    parsed: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    conflicts = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        if not source or not target:
            continue
        variants = item.get("variants") or []
        if not isinstance(variants, list):
            variants = []
        clean_variants = []
        for variant in variants:
            if isinstance(variant, str):
                variant = variant.strip()
                if variant and variant != target and variant not in clean_variants:
                    clean_variants.append(variant)
        entity_type = item.get("type", "person")
        if entity_type not in _ENTITY_TYPES:
            entity_type = "person"
        confidence = item.get("confidence", 0.5)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            confidence = 0.5
        entity = {
            "source": source,
            "target": target,
            "type": entity_type,
            "confidence": float(confidence),
            "variants": clean_variants,
        }
        if source not in parsed:
            parsed[source] = entity
            order.append(source)
        elif parsed[source]["target"] != target:
            conflicts.add(source)
        else:
            for variant in clean_variants:
                if variant not in parsed[source]["variants"]:
                    parsed[source]["variants"].append(variant)
            parsed[source]["confidence"] = max(parsed[source]["confidence"], float(confidence))
    return [parsed[source] for source in order if source not in conflicts]


def extract_entities_via_llm(
    revision: Dict[str, Any],
    translations_by_segment: Dict[str, str],
    call_fn: Callable[[List[Dict[str, str]]], str],
) -> List[Dict[str, Any]]:
    """用注入的 LLM call_fn 抽取专名；非关键抽取失败时返回空列表。"""
    try:
        response = call_fn(build_extract_messages(revision, translations_by_segment))
    except Exception:
        return []
    return parse_llm_entities(response)


def enforce_context_targets(
    entities: List[Dict[str, Any]],
    context_entities: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """既有 approved/locked Context Pack 译名优先于本轮 LLM 建议。"""
    known_targets = {entity["source"]: entity["target"] for entity in context_entities}
    out = []
    for entity in entities:
        normalized = dict(entity)
        normalized["variants"] = list(entity.get("variants", []))
        known_target = known_targets.get(entity["source"])
        if known_target is not None and known_target != entity["target"]:
            normalized["variants"] = [entity["target"], *normalized["variants"]]
            normalized["variants"] = list(dict.fromkeys(
                variant for variant in normalized["variants"] if variant != known_target
            ))
            normalized["target"] = known_target
        out.append(normalized)
    return out


def apply_entity_variants(
    segments: List[Dict[str, Any]],
    translations_by_segment: Dict[str, str],
    entities: List[Dict[str, Any]],
) -> int:
    """仅在源文含该实体的段内，把 LLM 明示的中文 variants 替换成 canonical target。"""
    normalized_segments = 0
    for segment in segments:
        segment_id = segment["segment_id"]
        translation = translations_by_segment.get(segment_id)
        if not translation:
            continue
        original = translation
        for entity in entities:
            if entity["source"] not in segment["source_text"]:
                continue
            for variant in entity.get("variants", []):
                translation = translation.replace(variant, entity["target"])
        if translation != original:
            translations_by_segment[segment_id] = translation
            normalized_segments += 1
    return normalized_segments


def enqueue_entity_reviews(
    revision: Dict[str, Any],
    entities: List[Dict[str, Any]],
    entity_store_root: Path,
    review_queue_root: Path,
) -> List[Dict[str, Any]]:
    """把源文中确实出现的 LLM 提案交给 entity-review；不自动 approve。"""
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
