#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Document-level translation QA for cross-segment alignment failures."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

_NORMALIZE_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _NORMALIZE_RE.sub("", text or "")


def _low_information(text: str) -> bool:
    chars = [c for c in _norm(text) if not c.isdigit()]
    if len(chars) <= 2:
        return True
    return len(set(chars)) <= 2 and len(chars) >= 4


def audit_document_translations(
    segments: Sequence[Dict[str, Any]], translations_by_segment: Dict[str, str], *, min_run: int = 3
) -> List[Dict[str, Any]]:
    """Audit an entire segment→translation mapping and return warning/error findings."""
    ordered = [s for s in segments if s["segment_id"] in translations_by_segment]
    duplicate_findings = _duplicate_translation_findings(ordered, translations_by_segment)
    block_findings = _block_paste_findings(ordered, translations_by_segment, min_run=min_run)
    return duplicate_findings + block_findings


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
