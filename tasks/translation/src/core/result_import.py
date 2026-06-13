#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result 导入:把执行器(API/Agent)产出的 Result 落成 Candidate(import-result)。

- 先做 §5.4 stale-result 校验(task_id/task_digest/schema/segment/source_hash);任一不匹配
  整份 Result 进 quarantine,不写任何 candidate。
- 通过后按 §9.2 的 candidate_id_for(task_digest, result_digest, key, segment_id) 派生 id,
  写入 candidate store(复用 legacy_import 的幂等 + 冲突检测 + 原子写)。
- 同一 Result 重复导入零新增;同一任务不同执行(result_digest 变)落独立 candidate。
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
        canonical_digest,
        candidate_id_for,
        check_result_against_task,
        validate_artifact,
    )
    from .legacy_import import write_candidates
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.artifact_schemas import (
        canonical_digest,
        candidate_id_for,
        check_result_against_task,
        validate_artifact,
    )
    from core.legacy_import import write_candidates


# Agent/API 的 Result 是不可信输入(system-design §16):限制大小与数量,防止内存/磁盘耗尽。
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_CANDIDATES = 10_000
MAX_TEXT_LEN = 50_000


class QuarantineError(Exception):
    """Result 与 Task 不匹配/超限/重复(不可信输入),整份进 quarantine,不导入。"""

    def __init__(self, reasons: List[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def build_candidates_from_result(task: Dict[str, Any], result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """校验 Result 对齐 Task 后,构建并校验 Candidate 列表。stale 抛 QuarantineError。"""
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
    for entry in result["candidates"]:
        segment_id = entry["segment_id"]
        candidate = {
            "schema_version": 2,
            "candidate_id": candidate_id_for(
                task_digest, result_digest, entry["result_candidate_key"], segment_id
            ),
            "document_id": task["document_id"],
            "revision_id": task["revision_id"],
            "segment_id": segment_id,
            "source_hash": source_hashes[segment_id],
            "text": entry["text"],
            "purpose": task["task_type"],
            "parent_candidate_id": None,
            "producer": {
                "type": producer["type"],
                "name": producer["name"],
                "model": producer.get("model"),
                "harness": producer["name"] if producer["type"] == "harness" else None,
            },
            "provenance": {
                "task_id": task["task_id"],
                "task_digest": task_digest,
                "result_digest": result_digest,
                "result_candidate_key": entry["result_candidate_key"],
                "prompt_version": None,
                "recipe_id": None,
                "knowledge_snapshot_id": task.get("knowledge_snapshot_id"),
            },
            "created_at": result["completed_at"],
        }
        errors = validate_artifact("candidate", candidate)
        if errors:
            raise ValueError(f"built candidate invalid: {errors}")
        candidates.append(candidate)
    return candidates


def import_result(task: Dict[str, Any], result: Dict[str, Any], store_dir: Path) -> Dict[str, Any]:
    """导入一份 Result。返回 {written, skipped, candidate_ids};stale 时返回 quarantined 报告。"""
    try:
        candidates = build_candidates_from_result(task, result)
    except QuarantineError as exc:
        return {"quarantined": True, "reasons": exc.reasons, "written": 0, "skipped": 0, "candidate_ids": []}
    written, skipped = write_candidates(candidates, store_dir)
    return {
        "quarantined": False,
        "written": written,
        "skipped": skipped,
        "candidate_ids": [c["candidate_id"] for c in candidates],
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
    print(f"written={report['written']} skipped={report['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
