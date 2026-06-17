#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 DocumentRevision + 逐 segment 译文渲染 bilingual / zh 输出(shadow path)。

bilingual:front matter 里可翻译键(title、caption/excerpt)的译文行紧跟在源行后插入,其余键
透传;正文每个非空源行后紧跟译文行,源文件空行结构原样保留。
zh:复刻 extract_chinese 的字段变换——front matter 收窄为白名单键(ID/title/caption|excerpt/
series:+  title:/tags/日期/fee_required),按源 front matter 顺序、值换成译文(ID/日期/fee 保留
原值),只开 `---` 不闭合、隔两空行后接正文译文(只出译文行,保留空行)。
译文按 segment_id 提供(将来由 DocumentVersion 选定的 candidate 给出);此处不含 candidate/version 模型。
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


# zh front matter:保留原值的键(extract_chinese 透传,不换译文)。
_ZH_KEEP_ASIS = {"create_date", "update_date", "published_at", "updated_at", "fee_required"}
_ZH_ID_KEYS = {"novel_id", "post_id"}


def _segments_index(revision: Dict[str, Any]):
    segs_by_kind: Dict[str, Dict[str, Any]] = {}
    body_segs: List[Dict[str, Any]] = []
    for seg in revision["segments"]:
        if seg["kind"] == "body":
            body_segs.append(seg)
        else:
            segs_by_kind[seg["kind"]] = seg
    return segs_by_kind, body_segs


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


def render_zh(revision: Dict[str, Any], source_text: str, translations: Dict[str, str]) -> str:
    """返回 zh 文本(复刻 extract_chinese 字段变换)。translations:segment_id -> 译文。

    front matter 按源顺序收窄为白名单键:ID(由 novel_id/post_id)、title、caption|excerpt、
    series:+缩进 title:、tags 取译文;create_date/update_date/published_at/updated_at/fee_required
    保留原值;其余键(author/creator/series.id/order/x_restrict/source_url/lang/...)丢弃。只开 `---`
    不闭合,隔两空行接正文;正文每个非空源行只出译文行,源空行结构保留。
    """
    provider = revision["source"]["provider"]
    caption_key = _PROVIDER_SPEC[provider]["caption_key"]
    segs_by_kind, body_segs = _segments_index(revision)
    top_keys = {"title": "metadata.title", caption_key: "metadata.caption", "tags": "metadata.tags"}

    def _tr(seg: Dict[str, Any]) -> str:
        key = seg["segment_id"]
        if key not in translations:
            raise KeyError(f"missing translation for segment {key}")
        return translations[key]

    out: List[str] = []
    front, body = _split_front_matter(source_text)
    if front is not None:
        out.append("---")
        in_series = False
        for line in front[1:-1]:  # 跳过首尾 --- 围栏
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]
            key = stripped.split(":", 1)[0] if ":" in stripped else ""
            if not indent:  # 顶层键
                in_series = key == "series"
                if key in _ZH_ID_KEYS:
                    value = stripped.split(":", 1)[1].strip()
                    out.append(f"ID: {value}" if value else "ID:")
                elif key in top_keys and top_keys[key] in segs_by_kind:
                    out.append(f"{key}: {_tr(segs_by_kind[top_keys[key]])}")
                elif key == "series":
                    out.append("series:")
                elif key in _ZH_KEEP_ASIS:
                    out.append(line)
                # 其余顶层键丢弃
            elif in_series and key == "title":
                seg = segs_by_kind.get("metadata.series_title")
                out.append(f"{indent}title: {_tr(seg) if seg else ''}")
            # 其余缩进行(series.id/order、author 子键等)丢弃
        out.append("")
        out.append("")

    body_idx = 0
    for line in body:
        if not line.strip():
            out.append("")
            continue
        if body_idx >= len(body_segs):
            raise ValueError("source_text has more body lines than revision segments")
        seg = body_segs[body_idx]
        if line.strip() != seg["source_text"]:
            raise ValueError(
                f"source line {body_idx} does not match revision segment "
                f"{seg['segment_id']}: {line.strip()!r} != {seg['source_text']!r}"
            )
        out.append(_tr(seg))
        body_idx += 1
    if body_idx != len(body_segs):
        raise ValueError(
            f"source_text consumed {body_idx} body lines but revision has {len(body_segs)} segments"
        )

    return "\n".join(out) + "\n"
