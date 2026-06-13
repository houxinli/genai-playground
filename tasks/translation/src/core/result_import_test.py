#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result 导入:Task+Result → Candidate v3 + Attestation(校验/幂等/stale 隔离/同文本跨执行去重)。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import result_import as ri
    from .artifact_schemas import canonical_digest, validate_artifact
    from .artifact_store import ArtifactStore
except ImportError:  # core/ 在 sys.path 上
    import result_import as ri
    from artifact_schemas import canonical_digest, validate_artifact
    from artifact_store import ArtifactStore


REV = "rev_" + "a" * 16
SEG = f"{REV}:000042:" + "b" * 8
HASH = "c" * 16
KNOW = "knowledge_" + "d" * 16
DOC = "pixiv:50235390:12430834"


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


def make_revision():
    # 与 make_task 对齐的最小 revision(document_id/revision_id/segment/source_hash 一致),
    # 供 store integrity gate 解析 candidate↔revision。
    return {
        "schema_version": 1,
        "document_id": DOC,
        "revision_id": REV,
        "source": {"provider": "pixiv", "creator_id": "50235390", "source_id": "12430834",
                   "url": "https://example.invalid/12430834"},
        "metadata": {"title": "标题"},
        "segments": [{"segment_id": SEG, "ordinal": 42, "kind": "body",
                      "source_text": "原文", "source_hash": HASH}],
    }


def _store_with_revision(tmp):
    store = ArtifactStore(Path(tmp))
    store.put_many(DOC, [make_revision()])
    return store


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
        candidates, attestations = ri.build_candidates_from_result(make_task(), make_result())
        self.assertEqual(1, len(candidates))
        self.assertEqual(1, len(attestations))
        c, a = candidates[0], attestations[0]
        self.assertEqual([], validate_artifact("candidate", c))
        self.assertEqual([], validate_artifact("attestation", a))
        self.assertEqual(SEG, c["segment_id"])
        self.assertEqual("她转过身来。", c["text"])
        self.assertEqual(3, c["schema_version"])
        self.assertEqual(1, c["normalization_version"])
        self.assertRegex(c["candidate_id"], r"^cand_[0-9a-f]{64}$")
        # 来源落在 attestation,不在 candidate
        self.assertNotIn("producer", c)
        self.assertEqual("codex", a["producer"]["harness"])
        self.assertEqual(a["candidate_id"], c["candidate_id"])
        self.assertEqual(a["task_digest"], make_result()["task_digest"])

    def test_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_with_revision(tmp)
            r1 = ri.import_result(make_task(), make_result(), store)
            self.assertEqual((1, 0), (r1["written"], r1["skipped"]))
            self.assertEqual((1, 0), (r1["attestations_written"], r1["attestations_skipped"]))
            r2 = ri.import_result(make_task(), make_result(), store)
            self.assertEqual((0, 1), (r2["written"], r2["skipped"]))
            self.assertEqual((0, 1), (r2["attestations_written"], r2["attestations_skipped"]))
            self.assertEqual(r1["candidate_ids"], r2["candidate_ids"])
            self.assertEqual(r1["attestation_ids"], r2["attestation_ids"])

    def test_missing_revision_quarantined_no_write(self):
        # 没有先入 revision 的 store:integrity gate 拒绝,整批 quarantine,零落盘
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp))  # 未 seed revision
            report = ri.import_result(make_task(), make_result(), store)
            self.assertTrue(report["quarantined"])
            self.assertEqual([], list(Path(tmp).rglob("*.jsonl")))

    def test_stale_source_hash_quarantined_no_write(self):
        result = make_result()
        result["candidates"][0]["source_hash"] = "9" * 16
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp))
            report = ri.import_result(make_task(), result, store)
            self.assertTrue(report["quarantined"])
            self.assertTrue(any("stale source_hash" in r for r in report["reasons"]))
            self.assertEqual([], list(Path(tmp).rglob("*.jsonl")))  # 零落盘

    def test_same_text_dedup_one_candidate_two_attestations(self):
        # 两次不同执行(producer/完成时刻不同)产出相同译文 → 同一 Candidate + 两条 Attestation
        result_a = make_result()
        result_b = make_result()
        result_b["producer"] = {"type": "api", "name": "openrouter", "model": "grok-4.1-fast"}
        result_b["completed_at"] = "2026-06-14T00:00:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_with_revision(tmp)
            ra = ri.import_result(make_task(), result_a, store)
            rb = ri.import_result(make_task(), result_b, store)
            self.assertEqual(ra["candidate_ids"], rb["candidate_ids"])  # 文本等价去重
            self.assertEqual((1, 0), (ra["written"], ra["skipped"]))
            self.assertEqual((0, 1), (rb["written"], rb["skipped"]))  # candidate 已存在,跳过
            self.assertNotEqual(ra["attestation_ids"], rb["attestation_ids"])  # 来源各记一条
            self.assertEqual((1, 0), (rb["attestations_written"], rb["attestations_skipped"]))
            self.assertEqual(1, len(store.list_shard("candidate", DOC)))
            self.assertEqual(2, len(store.list_shard("attestation", DOC)))

    def test_changed_task_digest_quarantined(self):
        result = make_result()
        result["task_digest"] = "0" * 16  # 与当前 task canonical digest 不符
        report = ri.import_result(make_task(), result, ArtifactStore(Path("/nonexistent")))
        self.assertTrue(report["quarantined"])
        self.assertTrue(any("task_digest mismatch" in r for r in report["reasons"]))

    def test_different_text_yields_independent_candidate(self):
        a = ri.build_candidates_from_result(make_task(), make_result("译文甲"))[0][0]["candidate_id"]
        b = ri.build_candidates_from_result(make_task(), make_result("译文乙"))[0][0]["candidate_id"]
        self.assertNotEqual(a, b)  # 内容寻址:不同译文 = 独立 candidate

    def test_same_result_same_candidate_id(self):
        a = ri.build_candidates_from_result(make_task(), make_result())[0][0]["candidate_id"]
        b = ri.build_candidates_from_result(make_task(), make_result())[0][0]["candidate_id"]
        self.assertEqual(a, b)


    def test_duplicate_candidate_key_quarantined_before_write(self):
        result = make_result()
        dup = dict(result["candidates"][0]); dup["text"] = "不同文本"
        result["candidates"].append(dup)  # 同 (key, segment) 不同文本
        result["task_digest"] = canonical_digest(make_task())  # 保持对齐
        # 重算 task_digest 不变(task 未变);触发重复键检查
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp))
            report = ri.import_result(make_task(), result, store)
            self.assertTrue(report["quarantined"])
            self.assertTrue(any("duplicate" in r for r in report["reasons"]))
            self.assertEqual([], list(Path(tmp).rglob("*.jsonl")))  # 写入前拒绝,零落盘

    def test_oversized_text_quarantined(self):
        result = make_result("x" * (ri.MAX_TEXT_LEN + 1))
        report = ri.import_result(make_task(), result, ArtifactStore(Path("/unused")))
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
