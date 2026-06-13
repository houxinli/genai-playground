#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把存量 bilingual 目录按显式标签导入为 legacy Candidate(迁移不丢历史)。

- 以 source_identity 从源构建 DocumentRevision;反解 bilingual 得到逐 segment 译文。
- 每个 (目录标签, segment) 生成一个 producer.type=legacy 的 Candidate,
  candidate_id 由 (标签, segment_id, 译文) 确定性派生 → 重复导入幂等、零新增。
- 不按目录名猜质量;隔离目录由调用方(基于盘点报告)跳过。
不写发布版本,不切主路径(那是 P1)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from .artifact_schemas import validate_artifact
    from .source_identity import _PROVIDER_SPEC, build_document_revision
except ImportError:  # 作为脚本运行:把 tasks/translation/src 加入 path,走 core.* 以解析 utils
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.artifact_schemas import validate_artifact
    from core.source_identity import _PROVIDER_SPEC, build_document_revision


def legacy_candidate_id(label: str, segment_id: str, text: str) -> str:
    """legacy candidate 无 task/result,身份由 目录标签 + segment + 译文 确定性派生。"""
    payload = f"legacy:{label}:{segment_id}:{text}"
    return "cand_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _split_front_matter(text: str) -> Tuple[List[str], List[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return [], lines
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return lines[: idx + 1], lines[idx + 1 :]
    return [], lines


def parse_bilingual_translations(
    revision: Dict[str, Any], bilingual_text: str
) -> Tuple[Dict[str, str], List[str]]:
    """反解 bilingual,返回 (segment_id -> 译文, issues)。well-formed 文件可完整恢复;
    错位或截断只恢复能对齐的部分并在 issues 记录。"""
    provider = revision["source"]["provider"]
    caption_key = _PROVIDER_SPEC[provider]["caption_key"]
    top_keys = {"title": "metadata.title", caption_key: "metadata.caption", "tags": "metadata.tags"}

    segs_by_kind: Dict[str, Dict[str, Any]] = {}
    body_segs: List[Dict[str, Any]] = []
    for seg in revision["segments"]:
        (body_segs.append(seg) if seg["kind"] == "body" else segs_by_kind.__setitem__(seg["kind"], seg))

    translations: Dict[str, str] = {}
    issues: List[str] = []
    front, body = _split_front_matter(bilingual_text)

    # front matter:源键行后紧跟同键译文行
    in_series = False
    i = 0
    while i < len(front):
        line = front[i]
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        key = stripped.split(":", 1)[0] if ":" in stripped else ""
        nxt = front[i + 1] if i + 1 < len(front) else ""
        if not indent:
            in_series = key == "series"
            kind = top_keys.get(key)
            if kind and kind in segs_by_kind and nxt.startswith(f"{key}:") and nxt.lstrip() == nxt:
                translations[segs_by_kind[kind]["segment_id"]] = nxt.split(":", 1)[1].strip()
                i += 2
                continue
        elif in_series and key == "title" and "metadata.series_title" in segs_by_kind and nxt.lstrip().startswith("title:"):
            translations[segs_by_kind["metadata.series_title"]["segment_id"]] = nxt.split(":", 1)[1].strip()
            i += 2
            continue
        i += 1

    # body:非空行成对(源, 译)
    nonblank = [l for l in body if l.strip()]
    for k, seg in enumerate(body_segs):
        src_idx = k * 2
        if src_idx >= len(nonblank):
            issues.append(f"body truncated at segment {seg['segment_id']}")
            break
        if nonblank[src_idx].strip() != seg["source_text"]:
            issues.append(f"body misaligned at segment {seg['segment_id']}")
            break
        if src_idx + 1 < len(nonblank):
            translations[seg["segment_id"]] = nonblank[src_idx + 1]
        else:
            issues.append(f"missing translation for segment {seg['segment_id']}")
    return translations, issues


def build_legacy_candidates(
    provider: str, source_path: Path, bilingual_path: Path, label: str, created_at: str
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """对一个 bilingual 文件构建 legacy Candidate 列表(schema 已校验)。"""
    revision = build_document_revision(provider, Path(source_path))
    bilingual_text = Path(bilingual_path).read_text(encoding="utf-8", errors="ignore")
    translations, issues = parse_bilingual_translations(revision, bilingual_text)

    segs = {s["segment_id"]: s for s in revision["segments"]}
    candidates: List[Dict[str, Any]] = []
    for segment_id, text in translations.items():
        seg = segs[segment_id]
        candidate = {
            "schema_version": 2,
            "candidate_id": legacy_candidate_id(label, segment_id, text),
            "document_id": revision["document_id"],
            "revision_id": revision["revision_id"],
            "segment_id": segment_id,
            "source_hash": seg["source_hash"],
            "text": text,
            "purpose": "legacy",
            "parent_candidate_id": None,
            "producer": {"type": "legacy", "name": label, "model": None, "harness": None},
            "provenance": {
                "task_id": None, "task_digest": None, "result_digest": None,
                "result_candidate_key": None, "prompt_version": None,
                "recipe_id": label, "knowledge_snapshot_id": None,
            },
            "created_at": created_at,
        }
        errors = validate_artifact("candidate", candidate)
        if errors:
            raise ValueError(f"built legacy candidate invalid: {errors}")
        candidates.append(candidate)
    return candidates, issues


def write_candidates(candidates: List[Dict[str, Any]], store_dir: Path) -> Tuple[int, int]:
    """写入 candidate 工件;按 candidate_id 幂等(已存在则跳过),返回 (written, skipped)。"""
    store = Path(store_dir)
    store.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for candidate in candidates:
        path = store / f"{candidate['candidate_id']}.json"
        if path.exists():
            skipped += 1
            continue
        path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
    return written, skipped


def import_directory(
    provider: str, source_dir: Path, bilingual_dir: Path, label: str, store_dir: Path, created_at: str
) -> Dict[str, Any]:
    """把一个 bilingual 目录整体导入(按文件名配对源),返回导入报告。"""
    source_dir, bilingual_dir = Path(source_dir), Path(bilingual_dir)
    report: Dict[str, Any] = {
        "label": label, "posts": 0, "candidates": 0, "written": 0, "skipped": 0,
        "posts_with_issues": [], "missing_source": [],
    }
    for bilingual_path in sorted(bilingual_dir.glob("*.txt")):
        source_path = source_dir / bilingual_path.name
        if not source_path.exists():
            report["missing_source"].append(bilingual_path.name)
            continue
        report["posts"] += 1
        candidates, issues = build_legacy_candidates(
            provider, source_path, bilingual_path, label, created_at
        )
        written, skipped = write_candidates(candidates, store_dir)
        report["candidates"] += len(candidates)
        report["written"] += written
        report["skipped"] += skipped
        if issues:
            report["posts_with_issues"].append({"post": bilingual_path.name, "issues": issues})
    return report


def main() -> int:
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=tuple(_PROVIDER_SPEC))
    parser.add_argument("--source", required=True, type=Path, help="源 .txt")
    parser.add_argument("--bilingual", required=True, type=Path, help="存量 bilingual .txt")
    parser.add_argument("--label", required=True, help="目录标签(producer.name / recipe_id)")
    parser.add_argument("--store", required=True, type=Path, help="candidate 工件输出目录")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidates, issues = build_legacy_candidates(
        args.provider, args.source, args.bilingual, args.label, now
    )
    written, skipped = write_candidates(candidates, args.store)
    print(f"candidates={len(candidates)} written={written} skipped={skipped} issues={len(issues)}")
    for issue in issues:
        print(f"- {issue}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
