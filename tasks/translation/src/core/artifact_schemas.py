#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""业务工件 JSON Schema 的加载、校验、stale-result 防护与 candidate 幂等键派生。

schema 真相源在 tasks/translation/schemas/;协议语义见 docs/system-design.md §5/§6/§9。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

ARTIFACT_KINDS = (
    "document-revision",
    "candidate",
    "evaluation",
    "document-version",
    "annotation",
    "task",
    "result",
)


@lru_cache(maxsize=None)
def load_schema(kind: str) -> Dict[str, Any]:
    if kind not in ARTIFACT_KINDS:
        raise ValueError(f"unknown artifact kind: {kind!r}; expected one of {ARTIFACT_KINDS}")
    schema = json.loads((SCHEMA_DIR / f"{kind}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=None)
def _validator(kind: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(kind), format_checker=FormatChecker())


def validate_artifact(kind: str, document: Any) -> List[str]:
    """返回 schema 校验错误;空列表表示通过。"""
    errors = []
    for error in sorted(_validator(kind).iter_errors(document), key=lambda e: list(e.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def canonical_dumps(document: Any) -> str:
    """稳定序列化:sorted-key、紧凑分隔、保留 Unicode(digest 与 round-trip 的统一口径)。"""
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_digest(document: Any) -> str:
    return hashlib.sha256(canonical_dumps(document).encode("utf-8")).hexdigest()


def candidate_id_for(
    task_digest: str, result_digest: str, result_candidate_key: str, segment_id: str
) -> str:
    """system-design §9.2 的确定性幂等键派生。"""
    payload = f"{task_digest}:{result_digest}:{result_candidate_key}:{segment_id}"
    return "cand_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def check_result_against_task(task: Dict[str, Any], result: Dict[str, Any]) -> List[str]:
    """stale-result 防护(system-design §5.4):任一不匹配的结果必须进 quarantine。"""
    errors: List[str] = []
    if result.get("task_id") != task.get("task_id"):
        errors.append(f"task_id mismatch: result={result.get('task_id')} task={task.get('task_id')}")
    if result.get("schema_version") != task.get("expected_result_schema"):
        errors.append(
            "result schema_version "
            f"{result.get('schema_version')} != expected_result_schema {task.get('expected_result_schema')}"
        )
    task_segments = set(task.get("segment_ids", []))
    source_hashes = task.get("source_hashes", {})
    for index, candidate in enumerate(result.get("candidates", [])):
        segment_id = candidate.get("segment_id")
        if segment_id not in task_segments:
            errors.append(f"candidates[{index}]: segment {segment_id} not in task.segment_ids")
            continue
        expected_hash = source_hashes.get(segment_id)
        if candidate.get("source_hash") != expected_hash:
            errors.append(
                f"candidates[{index}]: stale source_hash {candidate.get('source_hash')} "
                f"!= {expected_hash} for segment {segment_id}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=ARTIFACT_KINDS)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    document = json.loads(args.path.read_text(encoding="utf-8"))
    errors = validate_artifact(args.kind, document)
    if errors:
        print(f"{args.path}: validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"{args.path}: valid {args.kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
