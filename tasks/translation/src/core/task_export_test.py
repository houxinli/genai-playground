#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export-job:Task 生成 + 与 import_result 的端到端往返。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import result_import as ri
    from . import source_identity as si
    from . import task_export as te
    from .artifact_schemas import canonical_digest, validate_artifact
except ImportError:  # core/ 在 sys.path 上
    import result_import as ri
    import source_identity as si
    import task_export as te
    from artifact_schemas import canonical_digest, validate_artifact


SRC = Path(__file__).resolve().parent / "testdata" / "fixtures" / "pixiv" / "700001" / "700001.txt"


def _revision():
    return si.build_document_revision("pixiv", SRC)


def _body_ids(rev):
    return [s["segment_id"] for s in rev["segments"] if s["kind"] == "body"]


class TaskExportTest(unittest.TestCase):
    def test_export_task_is_valid_and_deterministic(self):
        rev = _revision()
        ids = _body_ids(rev)
        t1 = te.export_task(rev, ids)
        t2 = te.export_task(rev, list(reversed(ids)))  # 顺序无关(内部 sort)
        self.assertEqual([], validate_artifact("task", t1))
        self.assertEqual(t1, t2)  # 同一 job 确定性
        self.assertTrue(t1["task_id"].startswith("task_"))
        self.assertEqual(sorted(ids), t1["segment_ids"])

    def test_unknown_segment_rejected(self):
        rev = _revision()
        with self.assertRaises(ValueError):
            te.export_task(rev, ["rev_deadbeef:000000:00000000"])

    def test_job_bundle_carries_source_text(self):
        rev = _revision()
        bundle = te.export_job(rev, _body_ids(rev))
        self.assertEqual(canonical_digest(bundle["task"]), bundle["task_digest"])
        texts = {s["segment_id"]: s["source_text"] for s in bundle["segments"]}
        for sid in bundle["task"]["segment_ids"]:
            self.assertTrue(texts[sid])  # 执行器拿得到源文本

    def test_export_then_import_round_trip(self):
        # 端到端:导出 job -> 模拟执行器翻译 -> import_result 落 candidate(agent 路线证明)
        rev = _revision()
        bundle = te.export_job(rev, _body_ids(rev))
        task = bundle["task"]

        # 模拟执行器(编码 agent / Grok 4):对每个 segment 产出译文
        fake_tr = {"「おはよう」": "「早上好」", "今日はいい天気だ。": "今天天气真好。"}
        result = {
            "schema_version": 1,
            "task_id": task["task_id"],
            "task_digest": bundle["task_digest"],
            "producer": {"type": "harness", "name": "claude-code", "model": None},
            "candidates": [
                {
                    "result_candidate_key": "option-a",
                    "segment_id": s["segment_id"],
                    "source_hash": task["source_hashes"][s["segment_id"]],
                    "text": fake_tr[s["source_text"]],
                }
                for s in bundle["segments"]
            ],
            "findings": [],
            "recommended_candidate_keys": ["option-a"],
            "completed_at": "2026-06-13T00:00:00Z",
        }
        self.assertEqual([], validate_artifact("result", result))
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            report = ri.import_result(task, result, store)
            self.assertFalse(report["quarantined"], report)
            self.assertEqual(len(bundle["segments"]), report["written"])
            self.assertEqual(len(bundle["segments"]), len(list(store.glob("*.json"))))


if __name__ == "__main__":
    unittest.main()
