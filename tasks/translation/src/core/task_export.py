#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export-job:从 DocumentRevision + 选定 segment 生成 Task 与自包含 job bundle。

执行器(编码 agent / API)消费 job bundle:bundle 含 Task(身份/约束/segment 列表)与每个
segment 的源文本,执行器据此产出 Result,再经 result_import 落 candidate。
task_id 由内容确定性派生 → 同一 job 重复导出得到同一 task_id 与 task_digest(与 import 端一致)。
此处只生成 Task,不调度、不写 candidate。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .artifact_schemas import canonical_digest, canonical_dumps, validate_artifact
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.artifact_schemas import canonical_digest, canonical_dumps, validate_artifact

DEFAULT_CONSTRAINTS = {"output_language": "zh-CN", "preserve_line_count": True}


def _segments_by_id(revision: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {s["segment_id"]: s for s in revision["segments"]}


def export_task(
    revision: Dict[str, Any],
    segment_ids: List[str],
    task_type: str = "translate",
    constraints: Optional[Dict[str, Any]] = None,
    knowledge_snapshot_id: Optional[str] = None,
    existing_candidate_ids: Optional[List[str]] = None,
    annotation_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """构建一个 schema 合法的 Task。segment_ids 必须属于该 revision。"""
    segs = _segments_by_id(revision)
    if not segment_ids:
        raise ValueError("segment_ids must not be empty")
    unknown = [sid for sid in segment_ids if sid not in segs]
    if unknown:
        raise ValueError(f"segment_ids not in revision: {unknown}")
    ordered = sorted(segment_ids)
    source_hashes = {sid: segs[sid]["source_hash"] for sid in ordered}
    constraints = dict(constraints or DEFAULT_CONSTRAINTS)

    # context_digest:覆盖参与本 task 的源内容与约束,内容变即新 task。
    context_digest = canonical_digest({
        "revision_id": revision["revision_id"],
        "segments": [{"segment_id": sid, "source_text": segs[sid]["source_text"]} for sid in ordered],
        "task_type": task_type,
        "constraints": constraints,
        "knowledge_snapshot_id": knowledge_snapshot_id,
    })
    # task_id:由身份内容确定性派生 → 同一 job 重复导出稳定。
    task_id = "task_" + hashlib.sha256(
        canonical_dumps({
            "document_id": revision["document_id"],
            "revision_id": revision["revision_id"],
            "segment_ids": ordered,
            "task_type": task_type,
            "context_digest": context_digest,
        }).encode("utf-8")
    ).hexdigest()[:24]

    task = {
        "schema_version": 1,
        "task_id": task_id,
        "task_type": task_type,
        "document_id": revision["document_id"],
        "revision_id": revision["revision_id"],
        "segment_ids": ordered,
        "source_hashes": source_hashes,
        "context_digest": context_digest,
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "constraints": constraints,
        "existing_candidate_ids": sorted(existing_candidate_ids or []),
        "annotation_ids": sorted(annotation_ids or []),
        "expected_result_schema": 1,
    }
    errors = validate_artifact("task", task)
    if errors:
        raise ValueError(f"exported task invalid: {errors}")
    return task


def export_job(revision: Dict[str, Any], segment_ids: List[str], **kwargs: Any) -> Dict[str, Any]:
    """自包含 job bundle:Task + 每个 segment 的源文本(执行器据此翻译)。

    task_digest 在 bundle 内给出,供执行器原样回填到 Result.task_digest,避免重算口径不一致。
    """
    task = export_task(revision, segment_ids, **kwargs)
    segs = _segments_by_id(revision)
    return {
        "task": task,
        "task_digest": canonical_digest(task),
        "segments": [
            {"segment_id": sid, "kind": segs[sid]["kind"], "source_text": segs[sid]["source_text"]}
            for sid in task["segment_ids"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, type=Path, help="document-revision.json")
    parser.add_argument("--segment", action="append", default=None, help="repeatable;默认全部 body segment")
    parser.add_argument("--task-type", default="translate")
    parser.add_argument("--out", required=True, type=Path, help="job bundle 输出 json")
    args = parser.parse_args()

    revision = json.loads(args.revision.read_text(encoding="utf-8"))
    segment_ids = args.segment or [s["segment_id"] for s in revision["segments"] if s["kind"] == "body"]
    bundle = export_job(revision, segment_ids, task_type=args.task_type)
    args.out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"task_id={bundle['task']['task_id']} segments={len(bundle['segments'])} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
