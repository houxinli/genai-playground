#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 DocumentRevision + 逐 segment 译文渲染 bilingual 输出(shadow path)。

目标:复刻现有流水线的 bilingual 格式——front matter 里可翻译键(title、caption/excerpt)的
译文行紧跟在源行后插入,其余键透传;正文每个非空源行后紧跟译文行,源文件空行结构原样保留。
译文按 segment_id 提供(将来由 DocumentVersion 选定的 candidate 给出);此处不含 candidate/version
模型,也不渲染 zh(zh 需复刻 extract_chinese 的字段变换,单列 follow-up)。
"""

from __future__ import annotations

from typing import Any, Dict, List

try:
    from .source_identity import _PROVIDER_SPEC
except ImportError:  # core/ 在 sys.path 上
    from source_identity import _PROVIDER_SPEC


def _split_front_matter(text: str):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, lines
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return lines[: idx + 1], lines[idx + 1 :]
    return None, lines


def render_bilingual(revision: Dict[str, Any], source_text: str, translations: Dict[str, str]) -> str:
    """返回 bilingual 文本。translations:segment_id -> 译文(metadata 与 body 段都需提供)。"""
    provider = revision["source"]["provider"]
    caption_key = _PROVIDER_SPEC[provider]["caption_key"]

    segs_by_kind: Dict[str, Dict[str, Any]] = {}
    body_segs: List[Dict[str, Any]] = []
    for seg in revision["segments"]:
        if seg["kind"] == "body":
            body_segs.append(seg)
        else:
            segs_by_kind[seg["kind"]] = seg

    def _tr(seg: Dict[str, Any]) -> str:
        key = seg["segment_id"]
        if key not in translations:
            raise KeyError(f"missing translation for segment {key}")
        return translations[key]

    # 顶层可翻译键 -> metadata segment kind(复刻旧流水线 pipeline.py 的配对集合)
    top_keys = {"title": "metadata.title", caption_key: "metadata.caption", "tags": "metadata.tags"}

    out: List[str] = []
    front, body = _split_front_matter(source_text)
    if front is not None:
        in_series = False
        for line in front:
            out.append(line)
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]
            key = stripped.split(":", 1)[0] if ":" in stripped else ""
            if not indent:  # 顶层键
                in_series = key == "series"
                kind = top_keys.get(key)
                if kind and kind in segs_by_kind:
                    out.append(f"{key}: {_tr(segs_by_kind[kind])}")
            elif in_series and key == "title" and "metadata.series_title" in segs_by_kind:
                # series.title 在缩进层配对,沿用源行缩进
                out.append(f"{indent}title: {_tr(segs_by_kind['metadata.series_title'])}")

    body_idx = 0
    for line in body:
        if not line.strip():
            out.append(line)
            continue
        if body_idx >= len(body_segs):
            raise ValueError("source_text has more body lines than revision segments")
        seg = body_segs[body_idx]
        if line.strip() != seg["source_text"]:
            raise ValueError(
                f"source line {body_idx} does not match revision segment "
                f"{seg['segment_id']}: {line.strip()!r} != {seg['source_text']!r}"
            )
        out.append(line)
        out.append(_tr(seg))
        body_idx += 1
    if body_idx != len(body_segs):
        raise ValueError(
            f"source_text consumed {body_idx} body lines but revision has {len(body_segs)} segments"
        )

    return "\n".join(out) + "\n"
