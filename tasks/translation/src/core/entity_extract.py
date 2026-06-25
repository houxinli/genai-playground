#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entity 自动抽取器(#83 P1b-2b):从 revision 正文/标题启发式抽人名 mention 候选。

**抽取是不可信候选生产者**(§8.2):产 proposals 喂 `entity_review.import_proposals` 链接入 review,
准度由 review 闸门兜——不跑 LLM、确定性、可测。启发式:
- **称谓锚点**(高置信 0.9):汉字/片假名名 + さん/ちゃん/くん/様/先生 等(精度高)。
- **复现片假名串**(中置信 0.6):长度 ≥3 且在本篇出现 ≥2 次的片假名串(人名会复现,一次性拟声词不会)。

抽 body + metadata.title/caption(跳过 tags 主题词);proposals 不带 suggested_target(译名由 review 给)。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

try:
    from . import entity_review
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import entity_review

HONORIFICS = ("さん", "ちゃん", "くん", "君", "様", "さま", "先生", "せんせい", "殿")
# 称谓前的人名只取 汉字/片假名(排除平假名,避免「おじさん/おにいちゃん」等普通词误判)。
_HON_NAME = r"[一-鿿々ァ-ヴー]{1,8}"
_HONORIFIC_RE = re.compile(rf"({_HON_NAME}?)(?:{'|'.join(HONORIFICS)})")
_KATAKANA_RE = re.compile(r"[ァ-ヴー]{3,}")
# 常见非人名片假名(拟声/泛指),降噪;余下交 review。
_STOPWORDS = {"コト", "モノ", "ヤツ", "ソレ", "コレ", "アレ", "ドコ", "ナニ", "ダメ", "セックス", "ペニス", "チンポ", "オマンコ"}
_EXTRACT_KINDS = ("body", "metadata.title", "metadata.caption")


def _katakana_counts(texts: List[str]) -> Counter:
    c: Counter = Counter()
    for t in texts:
        for m in _KATAKANA_RE.findall(t):
            if m not in _STOPWORDS:
                c[m] += 1
    return c


def extract_from_text(text: str, katakana_counts: Counter) -> List[Dict[str, Any]]:
    """单段抽取 → [{mention, confidence}]。katakana_counts 是全篇频次(用于复现过滤)。"""
    hits: Dict[str, float] = {}
    for name in _HONORIFIC_RE.findall(text):
        name = name.strip()
        if len(name) >= 2 and name not in _STOPWORDS:  # 称谓锚点,排除空/单字噪声
            hits[name] = max(hits.get(name, 0.0), 0.9)
    for m in _KATAKANA_RE.findall(text):
        if m not in _STOPWORDS and katakana_counts.get(m, 0) >= 2:  # 复现的片假名串
            hits[m] = max(hits.get(m, 0.0), 0.6)
    return [{"mention": k, "confidence": v} for k, v in hits.items()]


def extract_mentions(revision: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 revision 抽 proposals(每个唯一 mention 一条,取首次出现的 segment + 上下文,置信取最高)。"""
    document_id = revision["document_id"]
    segs = [s for s in revision["segments"] if s.get("kind") in _EXTRACT_KINDS]
    counts = _katakana_counts([s["source_text"] for s in segs])
    seen: Dict[str, Dict[str, Any]] = {}
    for seg in segs:
        for hit in extract_from_text(seg["source_text"], counts):
            mention = hit["mention"]
            prev = seen.get(mention)
            if prev is None:
                seen[mention] = {
                    "mention": mention,
                    "document_id": document_id,
                    "segment_id": seg["segment_id"],
                    "confidence": hit["confidence"],
                    "context": seg["source_text"][:80],
                }
            else:  # 已见:只抬升置信,不改首次位置
                prev["confidence"] = max(prev["confidence"], hit["confidence"])
    return sorted(seen.values(), key=lambda p: (-p["confidence"], p["mention"]))


def extract_and_link(
    revision: Dict[str, Any], scope_ctx: Dict[str, Any],
    entity_store, queue, **kw,
) -> List[Dict[str, Any]]:
    """抽取 → 喂 import_proposals(链接/入 review)。返回新建/更新的 review 项。"""
    return entity_review.import_proposals(extract_mentions(revision), scope_ctx, entity_store, queue, **kw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, type=Path, help="document-revision JSON")
    parser.add_argument("--entity-store", required=True, type=Path)
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--creator-id", required=True)
    parser.add_argument("--link", action="store_true", help="抽取后喂 import_proposals 入 review")
    args = parser.parse_args()
    revision = json.loads(args.revision.read_text(encoding="utf-8"))
    proposals = extract_mentions(revision)
    if not args.link:
        print(json.dumps({"proposals": proposals, "count": len(proposals)}, ensure_ascii=False, indent=2))
        return 0
    try:
        from .entity_store import EntityStore
    except ImportError:
        from entity_store import EntityStore
    scope_ctx = {"provider": args.provider, "creator_id": args.creator_id, "document_id": revision["document_id"]}
    reviews = extract_and_link(revision, scope_ctx, EntityStore(args.entity_store),
                               entity_review.ReviewQueue(args.queue))
    print(json.dumps({"proposals": len(proposals), "reviews": len(reviews)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
