#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从源文件(YAML front matter + 正文)计算稳定 revision/segment ID 并构建 DocumentRevision。

身份规则见 docs/system-design.md §5.2/§5.3:revision 固定原文、结构化 metadata、source URL、
adapter 版本与 segmentation 版本;算法版本变化必须产生新 revision。本模块只覆盖身份与最小
行级 segmentation;源格式适配与 renderer shadow path 属 P0.5。
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from .artifact_schemas import canonical_dumps, validate_artifact
except ImportError:  # core/ 目录直接在 sys.path 上
    from artifact_schemas import canonical_dumps, validate_artifact

try:
    from ..utils.file import parse_yaml_front_matter
except ImportError:  # tasks/translation/src 在 sys.path 上
    from utils.file import parse_yaml_front_matter

# 算法版本:任一变化都会改变 revision_id —— 这是设计要求,不是 bug。
ADAPTER_VERSION = "source-adapter-v1"
SEGMENTATION_VERSION = "nonempty-lines-v1"

# 各 provider 的 front matter 字段名不同(见 scripts/batch_download_v1.py 与 fanbox_download.py)。
_PROVIDER_SPEC = {
    "pixiv": {
        "source_id_key": "novel_id",
        "creator_container": "author",
        "caption_key": "caption",
        "published_key": "create_date",
        "updated_key": "update_date",
    },
    "fanbox": {
        "source_id_key": "post_id",
        "creator_container": "creator",
        "caption_key": "excerpt",
        "published_key": "published_at",
        "updated_key": "updated_at",
    },
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source_hash(line: str) -> str:
    return _sha256(line.strip())


def _coerce(value: Any) -> Any:
    """把 YAML 自动解析出的 date/datetime 归一成 ISO 字符串,保证 canonical 可序列化且稳定。"""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _tags_text(meta: Dict[str, Any]) -> str | None:
    """把 tags(YAML 解析成 list)还原成源行内的方括号形式,无 tags 返回 None。"""
    tags = meta.get("tags")
    if not isinstance(tags, list) or not tags:
        return None
    return "[" + ", ".join(str(t).strip() for t in tags) + "]"


def _structured_metadata(provider: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """按 provider 映射出参与身份的稳定 metadata,统一成 provider 无关的键。"""
    spec = _PROVIDER_SPEC[provider]
    series = meta.get("series") if isinstance(meta.get("series"), dict) else {}
    out = {
        "title": _coerce(meta.get("title")),
        "caption": _coerce(meta.get(spec["caption_key"])),
        "series_title": (_coerce(series.get("title")) or None),
        "tags": _tags_text(meta),
        "published_at": _coerce(meta.get(spec["published_key"])),
        "updated_at": _coerce(meta.get(spec["updated_key"])),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def parse_source(path: Path) -> Tuple[Dict[str, Any], List[str]]:
    """返回 (front matter dict, 非空正文行列表)。"""
    content = Path(path).read_text(encoding="utf-8")
    meta, body = parse_yaml_front_matter(content)
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: 缺少 YAML front matter")
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    return meta, body_lines


def _required_str(value: Any, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text or text == "None":
        raise ValueError(f"missing required identity field: {field}")
    return text


def _identity(provider: str, meta: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    if provider not in _PROVIDER_SPEC:
        raise ValueError(f"unknown provider: {provider!r}")
    spec = _PROVIDER_SPEC[provider]
    source_id = _required_str(meta.get(spec["source_id_key"]), spec["source_id_key"])
    container = meta.get(spec["creator_container"])
    creator = container if isinstance(container, dict) else {}
    creator_id = _required_str(creator.get("id"), f"{spec['creator_container']}.id")
    url = meta.get("source_url") or meta.get("url") or "about:blank"
    document_id = f"{provider}:{creator_id}:{source_id}"
    source = {"provider": provider, "creator_id": creator_id, "source_id": source_id, "url": url}
    return document_id, source


def compute_revision_id(provider: str, meta: Dict[str, Any], body_lines: List[str]) -> str:
    document_id, source = _identity(provider, meta)
    payload = {
        "adapter_version": ADAPTER_VERSION,
        "segmentation_version": SEGMENTATION_VERSION,
        "document_id": document_id,
        "source": source,
        "metadata": _structured_metadata(provider, meta),
        "body": body_lines,
    }
    return "rev_" + _sha256(canonical_dumps(payload))


def build_document_revision(provider: str, path: Path) -> Dict[str, Any]:
    """构建并校验一个 document-revision 工件(schema 来自 gh-35)。"""
    meta, body_lines = parse_source(path)
    document_id, source = _identity(provider, meta)
    revision_id = compute_revision_id(provider, meta, body_lines)

    segments: List[Dict[str, Any]] = []

    def _emit(kind: str, text: str) -> None:
        ordinal = len(segments)
        source_hash = _source_hash(text)
        segments.append({
            "segment_id": f"{revision_id}:{ordinal:06d}:{source_hash[:8]}",
            "ordinal": ordinal,
            "kind": kind,
            "source_text": text,
            "source_hash": source_hash,
        })

    structured = _structured_metadata(provider, meta)
    if structured.get("title"):
        _emit("metadata.title", structured["title"])
    if structured.get("caption"):
        _emit("metadata.caption", structured["caption"])
    if structured.get("series_title"):
        _emit("metadata.series_title", structured["series_title"])
    if structured.get("tags"):
        _emit("metadata.tags", structured["tags"])
    for line in body_lines:
        _emit("body", line)

    artifact = {
        "schema_version": 1,
        "document_id": document_id,
        "revision_id": revision_id,
        "source": source,
        "metadata": structured,
        "segments": segments,
    }
    errors = validate_artifact("document-revision", artifact)
    if errors:
        raise ValueError(f"built document-revision is invalid: {errors}")
    return artifact


def verify_revision_identity(revision: Dict[str, Any]) -> List[str]:
    """核对 revision 工件身份自洽:revision_id 与各 segment 的 source_hash/segment_id/ordinal 均由内容重算一致。

    Schema 合法但被编辑过的 revision(改了 source_text/metadata 却没更新 id)不可写入唯一真相源:
    否则坏 payload 落盘,且日后正确 revision 因同 revision_id 不同 payload 被 StoreConflictError 永久拒绝。
    """
    errors: List[str] = []
    body_lines = [s["source_text"] for s in revision.get("segments", []) if s.get("kind") == "body"]
    payload = {
        "adapter_version": ADAPTER_VERSION,
        "segmentation_version": SEGMENTATION_VERSION,
        "document_id": revision.get("document_id"),
        "source": revision.get("source"),
        "metadata": revision.get("metadata"),
        "body": body_lines,
    }
    expected_rev = "rev_" + _sha256(canonical_dumps(payload))
    if revision.get("revision_id") != expected_rev:
        errors.append(f"revision_id {revision.get('revision_id')} != 由内容重算 {expected_rev}")
    declared_rev = revision.get("revision_id")
    for ordinal, seg in enumerate(revision.get("segments", [])):
        expected_hash = _source_hash(seg.get("source_text", ""))
        if seg.get("source_hash") != expected_hash:
            errors.append(f"segment {seg.get('segment_id')}: source_hash != sha256(source_text)")
        expected_sid = f"{declared_rev}:{ordinal:06d}:{expected_hash[:8]}"
        if seg.get("segment_id") != expected_sid:
            errors.append(f"segment[{ordinal}] segment_id {seg.get('segment_id')} != {expected_sid}")
        if seg.get("ordinal") != ordinal:
            errors.append(f"segment {seg.get('segment_id')}: ordinal {seg.get('ordinal')} != {ordinal}")
    return errors
