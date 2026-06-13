#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result 导入:Task+Result → Candidate(校验/幂等/stale 隔离/跨执行独立)。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import result_import as ri
    from .artifact_schemas import canonical_digest, validate_artifact
except ImportError:  # core/ 在 sys.path 上
    import result_import as ri
    from artifact_schemas import canonical_digest, validate_artifact


REV = "rev_" + "a" * 16
SEG = f"{REV}:000042:" + "b" * 8
HASH = "c" * 16
KNOW = "knowledge_" + "d" * 16


def make_task():
    return {
        "schema_version": 1,
        "task_id": "task_" + "f" * 12,
        "task_type": "translate",
        "document_id": "pixiv:50235390:12430834",
        "revision_id": REV,
        "segment_ids": [SEG],
        "source_hashes": {SEG: HASH},
        "context_digest": "3" * 16,
        "knowledge_snapshot_id": KNOW,
        "constraints": {"output_language": "zh-CN"},
        "existing_candidate_ids": [],
        "annotation_ids": [],
        "expected_result_schema": 1,
    }


def make_result(text="她转过身来。"):
    return {
        "schema_version": 1,
        "task_id": "task_" + "f" * 12,
        "task_digest": canonical_digest(make_task()),
        "producer": {"type": "harness", "name": "codex", "model": "grok-4"},
        "candidates": [
            {"result_candidate_key": "option-a", "segment_id": SEG, "source_hash": HASH, "text": text}
        ],
        "findings": [],
        "recommended_candidate_keys": ["option-a"],
        "completed_at": "2026-06-13T00:00:00Z",
    }


class ImportResultTest(unittest.TestCase):
    def test_happy_path_writes_valid_candidates(self):
        candidates = ri.build_candidates_from_result(make_task(), make_result())
        self.assertEqual(1, len(candidates))
        c = candidates[0]
        self.assertEqual([], validate_artifact("candidate", c))
        self.assertEqual(SEG, c["segment_id"])
        self.assertEqual("她转过身来。", c["text"])
        self.assertEqual("codex", c["producer"]["harness"])
        self.assertEqual(c["provenance"]["task_digest"], make_result()["task_digest"])
        self.assertTrue(c["candidate_id"].startswith("cand_"))

    def test_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            r1 = ri.import_result(make_task(), make_result(), store)
            self.assertEqual((1, 0), (r1["written"], r1["skipped"]))
            r2 = ri.import_result(make_task(), make_result(), store)
            self.assertEqual((0, 1), (r2["written"], r2["skipped"]))
            self.assertEqual(r1["candidate_ids"], r2["candidate_ids"])

    def test_stale_source_hash_quarantined_no_write(self):
        result = make_result()
        result["candidates"][0]["source_hash"] = "9" * 16
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            report = ri.import_result(make_task(), result, store)
            self.assertTrue(report["quarantined"])
            self.assertTrue(any("stale source_hash" in r for r in report["reasons"]))
            self.assertEqual([], list(store.glob("*.json")))

    def test_changed_task_digest_quarantined(self):
        result = make_result()
        result["task_digest"] = "0" * 16  # 与当前 task canonical digest 不符
        report = ri.import_result(make_task(), result, Path("/nonexistent-should-not-be-used"))
        self.assertTrue(report["quarantined"])
        self.assertTrue(any("task_digest mismatch" in r for r in report["reasons"]))

    def test_different_execution_yields_independent_candidate(self):
        a = ri.build_candidates_from_result(make_task(), make_result("译文甲"))[0]["candidate_id"]
        b = ri.build_candidates_from_result(make_task(), make_result("译文乙"))[0]["candidate_id"]
        self.assertNotEqual(a, b)  # 不同执行(result_digest 变)= 独立 candidate

    def test_same_result_same_candidate_id(self):
        a = ri.build_candidates_from_result(make_task(), make_result())[0]["candidate_id"]
        b = ri.build_candidates_from_result(make_task(), make_result())[0]["candidate_id"]
        self.assertEqual(a, b)


    def test_duplicate_candidate_key_quarantined_before_write(self):
        result = make_result()
        dup = dict(result["candidates"][0]); dup["text"] = "不同文本"
        result["candidates"].append(dup)  # 同 (key, segment) 不同文本
        result["task_digest"] = canonical_digest(make_task())  # 保持对齐
        # 重算 task_digest 不变(task 未变);触发重复键检查
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            report = ri.import_result(make_task(), result, store)
            self.assertTrue(report["quarantined"])
            self.assertTrue(any("duplicate" in r for r in report["reasons"]))
            self.assertEqual([], list(store.glob("*.json")))  # 写入前拒绝,零落盘

    def test_oversized_text_quarantined(self):
        result = make_result("x" * (ri.MAX_TEXT_LEN + 1))
        report = ri.import_result(make_task(), result, Path("/unused"))
        self.assertTrue(report["quarantined"])
        self.assertTrue(any("exceeds" in r for r in report["reasons"]))

    def test_oversized_file_rejected_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big.json"
            big.write_text("{}" + " " * 100, encoding="utf-8")
            with self.assertRaises(ri.QuarantineError):
                ri._load(big, max_bytes=10)


if __name__ == "__main__":
    unittest.main()
