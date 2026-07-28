#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Document-level translation QA for cross-segment alignment failures."""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Sequence

_NORMALIZE_RE = re.compile(r"\s+")
_CONTEXT_MARKER_RE = re.compile(r"\[(?:上文|下文|翻译这一段|tags|原词\s*/\s*中文)\]", re.IGNORECASE)
# 邻段窜入:本段译文开头其实是上一段的(再)翻译。小模型拿到 `[上文]` 邻句时高发(deepseek 实测约半数段),
# 而整段并不相同,duplicate_translation / block_paste 都漏检。两档阈值:
# EXECUTOR 档给执行器内联复检用——误判成本只是多一次 API 调用,宁可宽;
# REPORT 档给 finish QA 用——要进 findings 给人看,必须窄,否则连续拟声词/承接省略句会刷屏。
NEIGHBOR_OVERLAP_EXECUTOR = 0.35
NEIGHBOR_OVERLAP_REPORT = 0.55


def _norm(text: str) -> str:
    return _NORMALIZE_RE.sub("", text or "")


def _low_information(text: str) -> bool:
    chars = [c for c in _norm(text) if not c.isdigit()]
    if len(chars) <= 2:
        return True
    return len(set(chars)) <= 2 and len(chars) >= 4


def head_overlap_ratio(previous: str, current: str) -> float:
    """本段译文**开头**与上一段译文的相似度(0–1):判「上一段被重复翻译进本段」。

    只比 current 的前 len(previous) 左右一段(邻段窜入总是发生在开头),整段比会被本段正文稀释。
    """
    prev, cur = _norm(previous), _norm(current)
    if not prev or not cur:
        return 0.0
    window = cur[: int(len(prev) * 1.25) + 4]
    return difflib.SequenceMatcher(None, prev, window).ratio()


def neighbor_leak_suspect(previous: str, current: str, *, threshold: float) -> bool:
    """current 是否疑似把 previous 的内容也译了进来。

    两条判据取或——上一段很短时相似度判据会失灵(窗口太小,噪声淹没信号,实测漏掉 4 段):
    ①开头相似度过阈;②上一段译文近乎原样出现在本段开头,且本段明显更长(不是纯重复而是"前缀+正文")。
    """
    prev, cur = _norm(previous), _norm(current)
    if len(prev) < 3 or len(cur) - len(prev) < 4:
        # 本段没比上一段多出实质内容 → 不是"上一段 + 本段"的拼接(整段雷同归 duplicate_translation 管)。
        return False
    if head_overlap_ratio(previous, current) >= threshold:
        return True
    core = prev.rstrip("♡。、,，…!！?？~～ ")
    return len(core) >= 6 and core in cur[: len(prev) * 2]


def _neighbor_overlap_findings(
    segments: Sequence[Dict[str, Any]], translations_by_segment: Dict[str, str]
) -> List[Dict[str, Any]]:
    body = [s for s in segments if s.get("kind") == "body"]
    hits = [
        (index, seg["segment_id"])
        for index, seg in enumerate(body)
        if index > 0 and neighbor_leak_suspect(
            translations_by_segment[body[index - 1]["segment_id"]],
            translations_by_segment[seg["segment_id"]],
            threshold=NEIGHBOR_OVERLAP_REPORT,
        )
    ]
    if not hits:
        return []
    return [{
        "code": "neighbor_overlap",
        "severity": "warning",
        "message": "本段译文开头疑似重复了上一段的内容(执行器把邻句上下文也翻译了)",
        "segments": [sid for _, sid in hits],
        "indices": [index for index, _ in hits],
    }]


def audit_document_translations(
    segments: Sequence[Dict[str, Any]], translations_by_segment: Dict[str, str], *, min_run: int = 3
) -> List[Dict[str, Any]]:
    """Audit an entire segment→translation mapping and return warning/error findings."""
    ordered = [s for s in segments if s["segment_id"] in translations_by_segment]
    shape_findings = _translation_shape_findings(ordered, translations_by_segment)
    duplicate_findings = _duplicate_translation_findings(ordered, translations_by_segment)
    block_findings = _block_paste_findings(ordered, translations_by_segment, min_run=min_run)
    neighbor_findings = _neighbor_overlap_findings(ordered, translations_by_segment)
    return shape_findings + duplicate_findings + block_findings + neighbor_findings


def translation_shape_errors(text: str) -> List[str]:
    """返回违反单 segment/扁平 TSV 输出契约的结构错误码。"""
    errors: List[str] = []
    if "\n" in text or "\r" in text:
        errors.append("multiline_translation")
    if _CONTEXT_MARKER_RE.search(text):
        errors.append("context_marker_leak")
    return errors


def _translation_shape_findings(
    segments: Sequence[Dict[str, Any]], translations_by_segment: Dict[str, str]
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, List[Any]]] = {}
    for idx, seg in enumerate(segments):
        for code in translation_shape_errors(translations_by_segment[seg["segment_id"]]):
            bucket = grouped.setdefault(code, {"segments": [], "indices": []})
            bucket["segments"].append(seg["segment_id"])
            bucket["indices"].append(idx)
    messages = {
        "multiline_translation": "单段译文含物理换行，无法进入扁平 TSV，疑似混入邻段",
        "context_marker_leak": "译文泄漏上/下文或 tags 等执行器上下文标记",
    }
    return [
        {
            "code": code,
            "severity": "error",
            "message": messages[code],
            "segments": grouped[code]["segments"],
            "indices": grouped[code]["indices"],
        }
        for code in ("multiline_translation", "context_marker_leak")
        if code in grouped
    ]


def _duplicate_translation_findings(
    segments: Sequence[Dict[str, Any]], translations_by_segment: Dict[str, str]
) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    findings: List[Dict[str, Any]] = []
    for idx, seg in enumerate(segments):
        text = translations_by_segment[seg["segment_id"]]
        key = _norm(text)
        if not key or _low_information(key):
            continue
        prev = seen.get(key)
        if prev is None:
            seen[key] = {"index": idx, "segment": seg}
            continue
        if _norm(prev["segment"]["source_text"]) == _norm(seg["source_text"]):
            continue
        findings.append({
            "code": "duplicate_translation_distinct_source",
            "severity": "warning",
            "message": "相同译文绑定到不同源文段",
            "segments": [prev["segment"]["segment_id"], seg["segment_id"]],
            "indices": [prev["index"], idx],
        })
    return findings


def _block_paste_findings(
    segments: Sequence[Dict[str, Any]], translations_by_segment: Dict[str, str], *, min_run: int
) -> List[Dict[str, Any]]:
    texts = [_norm(translations_by_segment[s["segment_id"]]) for s in segments]
    findings: List[Dict[str, Any]] = []
    covered_until = -1
    for start in range(len(segments)):
        if start <= covered_until:
            continue
        best = None
        for prev in range(start):
            run = 0
            while start + run < len(segments) and prev + run < start and texts[start + run] and texts[start + run] == texts[prev + run]:
                run += 1
            if run >= min_run and _sources_distinct_enough(segments, prev, start, run):
                if best is None or run > best[1]:
                    best = (prev, run)
        if best is None:
            continue
        prev, run = best
        covered_until = start + run - 1
        findings.append({
            "code": "block_paste_run",
            "severity": "error",
            "message": "连续译文块复制到不同源文段，疑似吞译/错位",
            "source_range": [start, start + run - 1],
            "copied_from_range": [prev, prev + run - 1],
            "offset": start - prev,
            "segments": [s["segment_id"] for s in segments[start:start + run]],
        })
    return findings


def _sources_distinct_enough(segments: Sequence[Dict[str, Any]], prev: int, start: int, run: int) -> bool:
    distinct = 0
    for i in range(run):
        if _norm(segments[prev + i]["source_text"]) != _norm(segments[start + i]["source_text"]):
            distinct += 1
    return distinct / run >= 0.8
