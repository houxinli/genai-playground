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


_EXTRACTION_INSTRUCTION = (
    "你是人名抽取器。读下面这部作品的全部文本,列出所有出场人物/专有人名。"
    "对每个名字输出 {mention(原文写法), readings(假名读音数组,可空), suggested_target(建议中文译名), "
    "confidence(0~1), segment_id(该名首次出现的段 id,从 segments 取)}。只输出 JSON: {\"proposals\": [...]}。"
    "不要把拟声词/普通名词/称谓本身当人名;同一人物多种写法各列一条但 suggested_target 保持一致。"
)


def build_extraction_job(revision: Dict[str, Any]) -> Dict[str, Any]:
    """导出待抽取文本 job 给 agent(Cursor)。只含 document_id + 待扫描段 + 指令引用。"""
    segs = [{"segment_id": s["segment_id"], "kind": s.get("kind"), "source_text": s["source_text"]}
            for s in revision["segments"] if s.get("kind") in _EXTRACT_KINDS]
    return {
        "task_type": "name-extraction",
        "document_id": revision["document_id"],  # agent 应在 result 里原样回带,供导回时校验
        "instruction": _EXTRACTION_INSTRUCTION,
        "segments": segs,
    }


def import_extraction_result(
    result: Dict[str, Any], scope_ctx: Dict[str, Any], entity_store, queue,
    *, valid_segment_ids=None, **kw,
) -> List[Dict[str, Any]]:
    """把 agent 产的抽取 result(proposals)喂 import_proposals。document_id 由 scope_ctx 权威回填。

    **校验 result 确实来自本 revision 的 job**(否则把名字静默导进错的作用域,#119):
    - result 若带 document_id,须与 scope 一致(防 RESULT 指向别的 job);
    - proposal.segment_id 若给,须属于本 revision(valid_segment_ids,从 revision 段集传入)。
    """
    document_id = scope_ctx["document_id"]
    rd = result.get("document_id")
    if rd is not None and rd != document_id:
        raise ValueError(f"result.document_id {rd!r} 与 revision 的 {document_id!r} 不符(RESULT 指向了别的 job?)")
    proposals = []
    for p in result.get("proposals", []):
        if not p.get("mention"):
            continue
        sid = p.get("segment_id")
        if sid is not None and valid_segment_ids is not None and sid not in valid_segment_ids:
            raise ValueError(f"proposal.segment_id {sid!r} 不属于本 revision(RESULT 与 REVISION 不匹配?)")
        prop = {
            "mention": p["mention"],
            "document_id": document_id,  # 权威来源,不信 result
            "confidence": float(p.get("confidence", 0.5)),
        }
        for k in ("segment_id", "suggested_target", "context", "readings"):
            if p.get(k) is not None:
                prop[k] = p[k]
        proposals.append(prop)
    return entity_review.import_proposals(proposals, scope_ctx, entity_store, queue, **kw)


def _scope_from_revision(revision: Dict[str, Any]) -> Dict[str, Any]:
    parts = revision["document_id"].split(":")
    if len(parts) != 3:
        raise ValueError(f"document_id 形如 provider:creator:source,实得 {revision['document_id']!r}")
    provider, creator_id, _src = parts
    return {"provider": provider, "creator_id": creator_id, "document_id": revision["document_id"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("heuristic", "job", "import"), default="heuristic",
                        help="heuristic=启发式抽取;job=导出 agent 待抽取文本;import=导回 agent 抽取结果")
    parser.add_argument("--revision", required=True, type=Path, help="document-revision JSON")
    parser.add_argument("--out", type=Path, help="mode=job 的输出 job.json")
    parser.add_argument("--result", type=Path, help="mode=import 的 agent 结果 result.json")
    parser.add_argument("--entity-store", type=Path, help="链接/导入需要")
    parser.add_argument("--queue", type=Path, help="链接/导入需要")
    parser.add_argument("--provider", help="可选;缺省由 document_id 推得,给了则须一致")
    parser.add_argument("--creator-id", help="可选;缺省由 document_id 推得,给了则须一致")
    parser.add_argument("--link", action="store_true", help="heuristic 模式抽取后喂 import_proposals 入 review")
    args = parser.parse_args()
    revision = json.loads(args.revision.read_text(encoding="utf-8"))

    if args.mode == "job":
        if not (args.out and str(args.out).strip()):
            parser.error("mode=job 需要非空 --out")
        job = build_extraction_job(revision)
        args.out.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"document_id": job["document_id"], "segments": len(job["segments"]), "out": str(args.out)}, ensure_ascii=False))
        return 0

    if args.mode == "import":
        if not (args.result and str(args.result).strip()):
            parser.error("mode=import 需要非空 --result")
        if not (args.entity_store and str(args.entity_store).strip()) or not (args.queue and str(args.queue).strip()):
            parser.error("mode=import 需要非空 --entity-store 与 --queue")
        try:
            scope_ctx = _scope_from_revision(revision)
        except ValueError as exc:
            parser.error(str(exc))
        if args.creator_id and args.creator_id != scope_ctx["creator_id"]:
            parser.error(f"--creator-id {args.creator_id!r} 与 document_id 的 {scope_ctx['creator_id']!r} 不一致")
        result = json.loads(args.result.read_text(encoding="utf-8"))
        try:
            from .entity_store import EntityStore
        except ImportError:
            from entity_store import EntityStore
        valid_sids = {s["segment_id"] for s in revision["segments"]}
        try:
            reviews = import_extraction_result(result, scope_ctx, EntityStore(args.entity_store),
                                               entity_review.ReviewQueue(args.queue), valid_segment_ids=valid_sids)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps({"proposals": len(result.get("proposals", [])), "reviews": len(reviews)}, ensure_ascii=False))
        return 0

    proposals = extract_mentions(revision)
    if not args.link:
        print(json.dumps({"proposals": proposals, "count": len(proposals)}, ensure_ascii=False, indent=2))
        return 0
    # 作用域权威来源是 document_id,而非 caller flags(误填/空 CREATOR_ID 会搜错作用域 → 漏既有实体)。
    parts = revision["document_id"].split(":")
    if len(parts) != 3:
        parser.error(f"document_id 形如 provider:creator:source,实得 {revision['document_id']!r}")
    provider, creator_id, _source = parts
    if args.provider and args.provider != provider:
        parser.error(f"--provider {args.provider!r} 与 document_id 的 {provider!r} 不一致")
    if args.creator_id and args.creator_id != creator_id:
        parser.error(f"--creator-id {args.creator_id!r} 与 document_id 的 {creator_id!r} 不一致")
    if not (args.entity_store and str(args.entity_store).strip()) or not (args.queue and str(args.queue).strip()):
        parser.error("--link 需要非空 --entity-store 与 --queue")
    try:
        from .entity_store import EntityStore
    except ImportError:
        from entity_store import EntityStore
    scope_ctx = {"provider": provider, "creator_id": creator_id, "document_id": revision["document_id"]}
    reviews = extract_and_link(revision, scope_ctx, EntityStore(args.entity_store),
                               entity_review.ReviewQueue(args.queue))
    print(json.dumps({"proposals": len(proposals), "reviews": len(reviews)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
