#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entity Linking 的模糊 / 读音匹配(#83 P1b-2b)。

精确匹配(mention == source 或 ∈ aliases)之外的回退:
- **读音匹配**:把 mention 与实体 readings ∪ source ∪ aliases 做 kana 归一化(片假名→平假名)后比较——
  写法不同但读音相同(カナ↔かな、片/平混写)也能链上。
- **模糊匹配**:difflib 归一化相似度(stdlib,无外部依赖)≥ 阈值。

匹配结果是**证据不是结论**:近似命中一律交给 review,不在此自动改/建实体。
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Tuple

# 片假名 → 平假名(U+30A1..U+30F6 → 平假名),其余字符原样。
_KATA_START, _KATA_END, _OFFSET = 0x30A1, 0x30F6, 0x60


def normalize_kana(text: str) -> str:
    return "".join(
        chr(ord(ch) - _OFFSET) if _KATA_START <= ord(ch) <= _KATA_END else ch
        for ch in (text or "")
    )


def _surface_forms(entity: Dict[str, Any]) -> List[str]:
    """实体的所有可比写法:source + aliases(用于 fuzzy)。"""
    return [entity["source"], *entity.get("aliases", [])]


def _reading_forms(entity: Dict[str, Any]) -> List[str]:
    """实体的所有可比读音:readings + source + aliases(用于读音归一化比较)。"""
    return [*entity.get("readings", []), entity["source"], *entity.get("aliases", [])]


def is_exact(mention: str, entity: Dict[str, Any]) -> bool:
    return mention == entity["source"] or mention in entity.get("aliases", [])


def reading_equal(mention: str, entity: Dict[str, Any]) -> bool:
    m = normalize_kana(mention)
    return any(normalize_kana(f) == m for f in _reading_forms(entity))


def fuzzy_score(mention: str, entity: Dict[str, Any]) -> float:
    """mention 与实体写法的最高归一化相似度(0..1)。"""
    return max((SequenceMatcher(None, mention, f).ratio() for f in _surface_forms(entity)), default=0.0)


def best_nonexact_match(
    mention: str, entities: List[Dict[str, Any]], *, fuzzy_threshold: float = 0.82,
    pick_winner: Optional[Callable[[List[Dict[str, Any]]], Dict[str, Any]]] = None,
) -> Optional[Tuple[Dict[str, Any], str, float]]:
    """无精确匹配时的最佳近似命中 → (entity, kind, score)。优先读音(更可靠),其次模糊;都不达标返回 None。

    跳过本就精确命中的实体(那条路径由调用方先处理)。读音命中记 score=1.0、kind='reading';
    模糊命中记 score=相似度、kind='fuzzy'。先按 score 取最高分组,**同分用 pick_winner 的作用域/locked
    优先级**(与精确匹配一致,creator 覆盖不被 global 同读音抢走;Codex #113),否则按 entity_id 兜底。
    """
    reading_hits: List[Tuple[Dict[str, Any], str, float]] = []
    fuzzy_hits: List[Tuple[Dict[str, Any], str, float]] = []
    for e in entities:
        if is_exact(mention, e):
            continue
        if reading_equal(mention, e):
            reading_hits.append((e, "reading", 1.0))
            continue
        score = fuzzy_score(mention, e)
        if score >= fuzzy_threshold:
            fuzzy_hits.append((e, "fuzzy", round(score, 4)))
    pool = reading_hits or fuzzy_hits
    if not pool:
        return None
    best = max(h[2] for h in pool)
    top = [h for h in pool if h[2] == best]
    if len(top) > 1 and pick_winner is not None:
        winner_id = pick_winner([h[0] for h in top])["entity_id"]
        for h in top:
            if h[0]["entity_id"] == winner_id:
                return h
    return sorted(top, key=lambda t: (-t[2], t[0]["entity_id"]))[0]
