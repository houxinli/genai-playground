#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把存量 bilingual 目录按显式标签导入为 Candidate v3 + legacy Attestation(迁移不丢历史)。

- 以 source_identity 从源构建 DocumentRevision;以源 segment 作锚点反解 bilingual
  逐 segment 译文(锚点法不依赖 bilingual 空行布局,且保留空译文槽、不串段)。
- 每个 segment 生成一个**内容寻址**的 Candidate v3(纯内容);译文经 normalization_version=1
  归一化后取 64-hex content id → 同译文跨标签自动去重。
- 每个 (标签, candidate) 生成一条 legacy Attestation(append-only 来源),attestation_id 确定性派生 →
  重复导入幂等、零新增;created_at 取源 published_at(稳定)。
- 写入做冲突检测(同 id 不同内容报错)与原子 rename。
不写发布版本,不切主路径(那是 P1)。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from . import document_qa
    from .artifact_schemas import (
        build_attestation,
        candidate_id_v3,
        normalize_text,
        validate_artifact,
        validate_candidate_identity,
    )
    from .artifact_store import ArtifactStore
    from .source_identity import _PROVIDER_SPEC, build_document_revision
except ImportError:  # 作为脚本运行:把 tasks/translation/src 加入 path,走 core.* 以解析 utils
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import document_qa
    from core.artifact_schemas import (
        build_attestation,
        candidate_id_v3,
        normalize_text,
        validate_artifact,
        validate_candidate_identity,
    )
    from core.artifact_store import ArtifactStore
    from core.source_identity import _PROVIDER_SPEC, build_document_revision

_FALLBACK_CREATED_AT = "1970-01-01T00:00:00Z"


def _split_front_matter(text: str) -> Tuple[List[str], List[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return [], lines
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return lines[: idx + 1], lines[idx + 1 :]
    return [], lines


def _raw_body(text: str) -> List[str]:
    """正文行(含空行,保留布局)。"""
    _, body = _split_front_matter(text)
    return body


def parse_bilingual_translations(
    revision: Dict[str, Any], bilingual_text: str
) -> Tuple[Dict[str, str], List[str]]:
    """以源 segment 作锚点反解 bilingual,返回 (segment_id -> 译文, issues)。

    正文用 revision 的 body segment 顺序在 bilingual 非空行里定位:每个源锚点后的非空行即译文,
    但若它正好等于"下一个源锚点"则说明该句译文为空(基线含 112 个 empty)——既不依赖 bilingual
    的空行布局(真实流水线与源不一致),又不会因空译文串段。metadata 源值若与 segment 不一致
    (bilingual 生成后源被改)报 issue 不导入。
    """
    provider = revision["source"]["provider"]
    caption_key = _PROVIDER_SPEC[provider]["caption_key"]
    top_keys = {"title": "metadata.title", caption_key: "metadata.caption", "tags": "metadata.tags"}

    segs_by_kind: Dict[str, Dict[str, Any]] = {}
    body_segs: List[Dict[str, Any]] = []
    for seg in revision["segments"]:
        (body_segs.append(seg) if seg["kind"] == "body" else segs_by_kind.__setitem__(seg["kind"], seg))

    translations: Dict[str, str] = {}
    issues: List[str] = []

    def _pair_meta(seg: Dict[str, Any], src_value: str, tr_line: str) -> None:
        if src_value != seg["source_text"]:
            issues.append(f"metadata {seg['kind']} source changed; skipped")
            return
        translations[seg["segment_id"]] = tr_line.split(":", 1)[1].strip()

    bil_front = _split_front_matter(bilingual_text)[0]
    in_series = False
    i = 0
    while i < len(bil_front):
        line = bil_front[i]
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        key = stripped.split(":", 1)[0] if ":" in stripped else ""
        nxt = bil_front[i + 1] if i + 1 < len(bil_front) else ""
        if not indent:
            in_series = key == "series"
            kind = top_keys.get(key)
            if kind and kind in segs_by_kind and nxt == nxt.lstrip() and nxt.startswith(f"{key}:"):
                _pair_meta(segs_by_kind[kind], stripped.split(":", 1)[1].strip(), nxt)
                i += 2
                continue
        elif in_series and key == "title" and "metadata.series_title" in segs_by_kind and nxt.lstrip().startswith("title:"):
            _pair_meta(segs_by_kind["metadata.series_title"], stripped.split(":", 1)[1].strip(), nxt)
            i += 2
            continue
        i += 1

    # 正文:源 segment 作锚点,在 bilingual 非空行里逐句定位译文(空行布局不参与)
    nonblank = [l for l in _raw_body(bilingual_text) if l.strip()]
    k = 0
    for seg_idx, seg in enumerate(body_segs):
        if k >= len(nonblank):
            issues.append(f"body truncated at segment {seg['segment_id']}")
            break
        if nonblank[k] != seg["source_text"]:
            issues.append(f"body misaligned at segment {seg['segment_id']}")
            break
        nxt_seg = body_segs[seg_idx + 1] if seg_idx + 1 < len(body_segs) else None
        if k + 1 >= len(nonblank):
            translations[seg["segment_id"]] = ""  # 末句无译文行 = 空译文
            k += 1
        elif nxt_seg is not None and nonblank[k + 1] == nxt_seg["source_text"]:
            translations[seg["segment_id"]] = ""  # 下一非空行已是下一个源锚点 = 本句空译文
            k += 1
        else:
            translations[seg["segment_id"]] = nonblank[k + 1]
            k += 2
    return translations, issues


def _legacy_created_at(revision: Dict[str, Any]) -> str:
    """稳定 created_at:取源 published_at,缺失则用固定迁移 epoch。"""
    return revision.get("metadata", {}).get("published_at") or _FALLBACK_CREATED_AT


def build_legacy_candidates(
    provider: str, source_path: Path, bilingual_path: Path, label: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """对一个 bilingual 文件构建 (Candidate v3 列表, legacy Attestation 列表, issues)(schema 已校验)。"""
    revision = build_document_revision(provider, Path(source_path))
    bilingual_text = Path(bilingual_path).read_text(encoding="utf-8", errors="ignore")
    translations, issues = parse_bilingual_translations(revision, bilingual_text)
    created_at = _legacy_created_at(revision)
    document_findings = document_qa.audit_document_translations(revision["segments"], translations)
    for finding in document_findings:
        issues.append(f"document_qa {finding['severity']} {finding['code']}: {finding.get('message', '')}")
    if any(f["severity"] == "error" for f in document_findings):
        return [], [], issues

    segs = {s["segment_id"]: s for s in revision["segments"]}
    candidates: List[Dict[str, Any]] = []
    attestations: List[Dict[str, Any]] = []
    for segment_id, text in translations.items():
        seg = segs[segment_id]
        normalized = normalize_text(text)
        candidate_id = candidate_id_v3(
            revision["revision_id"], segment_id, seg["source_hash"], normalized
        )
        candidate = {
            "schema_version": 3,
            "candidate_id": candidate_id,
            "document_id": revision["document_id"],
            "revision_id": revision["revision_id"],
            "segment_id": segment_id,
            "source_hash": seg["source_hash"],
            "normalization_version": 1,
            "text": normalized,
        }
        errors = validate_artifact("candidate", candidate)
        if errors:
            raise ValueError(f"built legacy candidate invalid: {errors}")
        id_errors = validate_candidate_identity(candidate)
        if id_errors:
            raise ValueError(f"built legacy candidate identity invalid: {id_errors}")
        candidates.append(candidate)

        attestation = build_attestation({
            "candidate_id": candidate_id,
            "producer": {"type": "legacy", "name": label, "model": None, "harness": None},
            "purpose": "legacy",
            "parent_candidate_id": None,
            "task_id": None,
            "task_digest": None,
            "result_digest": None,
            "result_candidate_key": None,
            "legacy_label": label,
            "knowledge_snapshot_id": None,
            "created_at": created_at,
        })
        errors = validate_artifact("attestation", attestation)
        if errors:
            raise ValueError(f"built legacy attestation invalid: {errors}")
        attestations.append(attestation)
    return candidates, attestations, issues


def import_directory(
    provider: str, source_dir: Path, bilingual_dir: Path, label: str, store: ArtifactStore
) -> Dict[str, Any]:
    """把一个 bilingual 目录整体导入分片 ArtifactStore(按文件名配对源),返回导入报告。
    每篇连同 DocumentRevision 一并入库,供 candidate↔revision 引用完整性校验。"""
    source_dir, bilingual_dir = Path(source_dir), Path(bilingual_dir)
    report: Dict[str, Any] = {
        "label": label, "posts": 0, "candidates": 0,
        "candidates_written": 0, "candidates_skipped": 0,
        "attestations_written": 0, "attestations_skipped": 0,
        "posts_with_issues": [], "missing_source": [],
    }
    for bilingual_path in sorted(bilingual_dir.glob("*.txt")):
        source_path = source_dir / bilingual_path.name
        if not source_path.exists():
            report["missing_source"].append(bilingual_path.name)
            continue
        report["posts"] += 1
        revision = build_document_revision(provider, source_path)
        candidates, attestations, issues = build_legacy_candidates(
            provider, source_path, bilingual_path, label
        )
        result = store.put_many(revision["document_id"], [revision, *candidates, *attestations])
        kinds = result["kinds"]
        report["candidates"] += len(candidates)
        report["candidates_written"] += kinds.get("candidate", {}).get("written", 0)
        report["candidates_skipped"] += kinds.get("candidate", {}).get("skipped", 0)
        report["attestations_written"] += kinds.get("attestation", {}).get("written", 0)
        report["attestations_skipped"] += kinds.get("attestation", {}).get("skipped", 0)
        if issues:
            report["posts_with_issues"].append({"post": bilingual_path.name, "issues": issues})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=tuple(_PROVIDER_SPEC))
    parser.add_argument("--source", required=True, type=Path, help="源 .txt")
    parser.add_argument("--bilingual", required=True, type=Path, help="存量 bilingual .txt")
    parser.add_argument("--label", required=True, help="目录标签(producer.name / recipe_id)")
    parser.add_argument("--store", required=True, type=Path, help="ArtifactStore 根目录")
    args = parser.parse_args()

    revision = build_document_revision(args.provider, args.source)
    candidates, attestations, issues = build_legacy_candidates(
        args.provider, args.source, args.bilingual, args.label
    )
    store = ArtifactStore(args.store)
    result = store.put_many(revision["document_id"], [revision, *candidates, *attestations])
    kinds = result["kinds"]
    print(
        f"candidates={len(candidates)} "
        f"written={kinds.get('candidate', {}).get('written', 0)} "
        f"skipped={kinds.get('candidate', {}).get('skipped', 0)} "
        f"attestations={len(attestations)} "
        f"att_written={kinds.get('attestation', {}).get('written', 0)} "
        f"issues={len(issues)}"
    )
    for issue in issues:
        print(f"- {issue}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
