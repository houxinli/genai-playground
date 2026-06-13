#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result 导入:把执行器(API/Agent)产出的 Result 落成 Candidate v3 + Attestation(import-result)。

- 先做 §5.4 stale-result 校验(task_id/task_digest/schema/segment/source_hash);任一不匹配
  整份 Result 进 quarantine,不写任何工件。
- 通过后对每个候选:译文经 normalization_version=1 归一化 → 内容寻址 candidate_id(64-hex,
  跨 producer 文本等价去重);来源(producer/task/result digest/key)落一条确定性 Attestation。
- 同一 Result 重复导入零新增(candidate + attestation 均确定性);不同执行产出相同译文 →
  同一 Candidate + 各自 Attestation(去重),产出不同译文 → 不同 Candidate。
不写发布版本、不做 selection(那是 P1)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from .artifact_schemas import (
        build_attestation,
        canonical_digest,
        candidate_id_v3,
        check_result_against_task,
        normalize_text,
        validate_artifact,
        validate_candidate_identity,
    )
    from .legacy_import import write_attestations, write_candidates
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.artifact_schemas import (
        build_attestation,
        canonical_digest,
        candidate_id_v3,
        check_result_against_task,
        normalize_text,
        validate_artifact,
        validate_candidate_identity,
    )
    from core.legacy_import import write_attestations, write_candidates


# Agent/API 的 Result 是不可信输入(system-design §16):限制大小与数量,防止内存/磁盘耗尽。
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_CANDIDATES = 10_000
MAX_TEXT_LEN = 50_000


class QuarantineError(Exception):
    """Result 与 Task 不匹配/超限/重复(不可信输入),整份进 quarantine,不导入。"""

    def __init__(self, reasons: List[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def build_candidates_from_result(
    task: Dict[str, Any], result: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """校验 Result 对齐 Task 后,构建并校验 (Candidate v3 列表, Attestation 列表)。stale 抛 QuarantineError。"""
    for kind, doc in (("task", task), ("result", result)):
        errors = validate_artifact(kind, doc)
        if errors:
            raise QuarantineError([f"{kind} schema invalid: {errors}"])

    stale = check_result_against_task(task, result)
    if stale:
        raise QuarantineError(stale)

    entries = result["candidates"]
    if len(entries) > MAX_CANDIDATES:
        raise QuarantineError([f"too many candidates: {len(entries)} > {MAX_CANDIDATES}"])
    seen_keys = set()
    oversized = []
    for entry in entries:
        composite = (entry["result_candidate_key"], entry["segment_id"])
        if composite in seen_keys:
            raise QuarantineError([f"duplicate (result_candidate_key, segment_id): {composite}"])
        seen_keys.add(composite)
        if len(entry["text"]) > MAX_TEXT_LEN:
            oversized.append(entry["segment_id"])
    if oversized:
        raise QuarantineError([f"candidate text exceeds {MAX_TEXT_LEN} chars: {oversized}"])

    task_digest = result["task_digest"]
    result_digest = canonical_digest(result)
    source_hashes = task["source_hashes"]
    producer = result["producer"]

    candidates: List[Dict[str, Any]] = []
    attestations: List[Dict[str, Any]] = []
    for entry in result["candidates"]:
        segment_id = entry["segment_id"]
        source_hash = source_hashes[segment_id]
        normalized = normalize_text(entry["text"])
        candidate_id = candidate_id_v3(
            task["revision_id"], segment_id, source_hash, normalized
        )
        candidate = {
            "schema_version": 3,
            "candidate_id": candidate_id,
            "document_id": task["document_id"],
            "revision_id": task["revision_id"],
            "segment_id": segment_id,
            "source_hash": source_hash,
            "normalization_version": 1,
            "text": normalized,
        }
        errors = validate_artifact("candidate", candidate)
        if errors:
            raise ValueError(f"built candidate invalid: {errors}")
        id_errors = validate_candidate_identity(candidate)
        if id_errors:
            raise ValueError(f"built candidate identity invalid: {id_errors}")
        candidates.append(candidate)

        attestation = build_attestation({
            "candidate_id": candidate_id,
            "producer": {
                "type": producer["type"],
                "name": producer["name"],
                "model": producer.get("model"),
                "harness": producer["name"] if producer["type"] == "harness" else None,
            },
            "purpose": task["task_type"],
            "parent_candidate_id": None,
            "task_id": task["task_id"],
            "task_digest": task_digest,
            "result_digest": result_digest,
            "result_candidate_key": entry["result_candidate_key"],
            "legacy_label": None,
            "knowledge_snapshot_id": task.get("knowledge_snapshot_id"),
            "created_at": result["completed_at"],
        })
        errors = validate_artifact("attestation", attestation)
        if errors:
            raise ValueError(f"built attestation invalid: {errors}")
        attestations.append(attestation)
    return candidates, attestations


def import_result(task: Dict[str, Any], result: Dict[str, Any], store_dir: Path) -> Dict[str, Any]:
    """导入一份 Result。返回工件计数与 id 列表;stale 时返回 quarantined 报告。"""
    try:
        candidates, attestations = build_candidates_from_result(task, result)
    except QuarantineError as exc:
        return {
            "quarantined": True, "reasons": exc.reasons,
            "written": 0, "skipped": 0, "candidate_ids": [],
            "attestations_written": 0, "attestations_skipped": 0,
        }
    written, skipped = write_candidates(candidates, store_dir)
    a_written, a_skipped = write_attestations(attestations, store_dir)
    return {
        "quarantined": False,
        "written": written,
        "skipped": skipped,
        "candidate_ids": [c["candidate_id"] for c in candidates],
        "attestations_written": a_written,
        "attestations_skipped": a_skipped,
        "attestation_ids": [a["attestation_id"] for a in attestations],
    }


def _load(path: Path, max_bytes: int | None = None) -> Dict[str, Any]:
    path = Path(path)
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise QuarantineError([f"{path}: file exceeds {max_bytes} bytes"])
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path)
    args = parser.parse_args()

    try:
        task = _load(args.task, MAX_RESULT_BYTES)
        result = _load(args.result, MAX_RESULT_BYTES)
    except QuarantineError as exc:
        for reason in exc.reasons:
            print(f"- {reason}", file=sys.stderr)
        return 1
    report = import_result(task, result, args.store)
    if report["quarantined"]:
        print("quarantined:", file=sys.stderr)
        for reason in report["reasons"]:
            print(f"- {reason}", file=sys.stderr)
        return 1
    print(
        f"candidates_written={report['written']} candidates_skipped={report['skipped']} "
        f"attestations_written={report['attestations_written']} "
        f"attestations_skipped={report['attestations_skipped']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
