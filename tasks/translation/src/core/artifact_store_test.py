#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ArtifactStore:分片路径、原子批写、幂等/冲突、candidate 身份 gate、cross-artifact integrity。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import artifact_store as astore
    from .artifact_schemas import build_attestation, candidate_id_v3, normalize_text
    from .source_identity import _source_hash
except ImportError:  # core/ 在 sys.path 上
    import artifact_store as astore
    from artifact_schemas import build_attestation, candidate_id_v3, normalize_text
    from source_identity import _source_hash


DOC = "pixiv:111:222"
REV = "rev_" + "a" * 16
SOURCE = "彼女は振り返った。"
SRC_HASH = _source_hash(SOURCE)
SEG = f"{REV}:000000:" + SRC_HASH[:8]
TEXT = "她转过身来。"


def make_revision():
    return {
        "schema_version": 1,
        "document_id": DOC,
        "revision_id": REV,
        "source": {"provider": "pixiv", "creator_id": "111", "source_id": "222",
                   "url": "https://example.invalid/222"},
        "metadata": {"title": "标题"},
        "segments": [{
            "segment_id": SEG, "ordinal": 0, "kind": "body",
            "source_text": SOURCE, "source_hash": SRC_HASH,
        }],
    }


def make_candidate(text=TEXT):
    normalized = normalize_text(text)
    return {
        "schema_version": 3,
        "candidate_id": candidate_id_v3(REV, SEG, SRC_HASH, normalized),
        "document_id": DOC,
        "revision_id": REV,
        "segment_id": SEG,
        "source_hash": SRC_HASH,
        "normalization_version": 1,
        "text": normalized,
    }


def make_attestation(candidate_id, label="dir_bilingual"):
    return build_attestation({
        "candidate_id": candidate_id,
        "producer": {"type": "legacy", "name": label, "model": None, "harness": None},
        "purpose": "legacy",
        "parent_candidate_id": None,
        "task_id": None, "task_digest": None, "result_digest": None,
        "result_candidate_key": None, "legacy_label": label, "knowledge_snapshot_id": None,
        "created_at": "2026-01-01T00:00:00Z",
    })


class ShardPathTest(unittest.TestCase):
    def test_shard_path_from_document_id(self):
        store = astore.ArtifactStore(Path("/tmp/store"))
        p = store.shard_path("candidate", DOC)
        self.assertEqual(Path("/tmp/store/candidate/pixiv/111/222.jsonl"), p)

    def test_unsafe_document_id_rejected(self):
        store = astore.ArtifactStore(Path("/tmp/store"))
        for bad in ("pixiv:..:222", "pixiv:111", "pixiv:a/b:222", "x:y:z:w"):
            with self.assertRaises(ValueError, msg=bad):
                store.shard_path("candidate", bad)

    def test_kind_inference(self):
        self.assertEqual("candidate", astore.kind_of(make_candidate()))
        self.assertEqual("attestation", astore.kind_of(make_attestation(make_candidate()["candidate_id"])))
        self.assertEqual("document-revision", astore.kind_of(make_revision()))


class PutManyTest(unittest.TestCase):
    def test_put_many_writes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            cand = make_candidate()
            att = make_attestation(cand["candidate_id"])
            r1 = store.put_many(DOC, [make_revision(), cand, att])
            self.assertEqual(1, r1["kinds"]["candidate"]["written"])
            self.assertEqual(1, r1["kinds"]["attestation"]["written"])
            self.assertEqual(1, r1["kinds"]["document-revision"]["written"])
            # 重放:全部命中去重,零新增
            r2 = store.put_many(DOC, [make_revision(), cand, att])
            self.assertEqual(0, r2["kinds"]["candidate"]["written"])
            self.assertEqual(1, r2["kinds"]["candidate"]["skipped"])
            self.assertEqual(0, r2["kinds"]["attestation"]["written"])

    def test_shard_files_are_per_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            cand = make_candidate()
            store.put_many(DOC, [cand, make_attestation(cand["candidate_id"])])
            self.assertTrue(store.shard_path("candidate", DOC).exists())
            self.assertTrue(store.shard_path("attestation", DOC).exists())
            # 没有遗留临时文件
            self.assertEqual([], list(Path(tmp).rglob("*.tmp")))

    def test_same_text_two_labels_dedup_one_candidate_two_attestations(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            cand = make_candidate()
            store.put_many(DOC, [cand, make_attestation(cand["candidate_id"], "dir_bilingual")])
            store.put_many(DOC, [cand, make_attestation(cand["candidate_id"], "dir_bilingual_v2")])
            self.assertEqual(1, len(store.list_shard("candidate", DOC)))
            self.assertEqual(2, len(store.list_shard("attestation", DOC)))

    def test_conflict_same_id_different_payload_is_fatal(self):
        # 同 id 不同 payload(content-addressing 不免存储损坏/算法漂移)。用 document-revision:
        # 它的 id 不被 store 重算,可构造"同 revision_id 不同内容"的冲突,纯测冲突机制(candidate
        # 会先被身份 gate 拦在前面,无法走到这里)。
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            store.put_many(DOC, [make_revision()])
            corrupt = make_revision()
            corrupt["metadata"] = {"title": "被改的标题"}  # 同 revision_id 不同内容
            with self.assertRaises(astore.StoreConflictError):
                store.put_many(DOC, [corrupt])

    def test_candidate_identity_gate_rejects_tampered_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            bad = make_candidate()
            bad["text"] = "和 id 不一致的译文"  # text 改了但 candidate_id 没变
            with self.assertRaises(ValueError):
                store.put_many(DOC, [bad])
            self.assertFalse(store.shard_path("candidate", DOC).exists())  # 零落盘

    def test_get_and_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            cand = make_candidate()
            store.put_many(DOC, [cand])
            self.assertTrue(store.exists("candidate", DOC, cand["candidate_id"]))
            self.assertEqual(cand, store.get("candidate", DOC, cand["candidate_id"]))
            self.assertFalse(store.exists("candidate", DOC, "cand_" + "0" * 64))


class VerifyReferencesTest(unittest.TestCase):
    def _seeded_store(self):
        tmp = tempfile.mkdtemp()
        store = astore.ArtifactStore(Path(tmp))
        cand = make_candidate()
        store.put_many(DOC, [make_revision(), cand, make_attestation(cand["candidate_id"])])
        return store, cand

    def test_consistent_artifacts_pass(self):
        store, cand = self._seeded_store()
        resolver = store.resolver_for(DOC)
        self.assertEqual([], astore.verify_references(make_revision(), resolver))
        self.assertEqual([], astore.verify_references(cand, resolver))
        self.assertEqual([], astore.verify_references(make_attestation(cand["candidate_id"]), resolver))

    def test_candidate_source_hash_mismatch_detected(self):
        store, cand = self._seeded_store()
        bad = dict(cand)
        bad["source_hash"] = "9" * 64  # 与 revision segment 不符(且会先触发身份不符)
        errors = astore.verify_references(bad, store.resolver_for(DOC))
        self.assertNotEqual([], errors)

    def test_attestation_dangling_candidate_detected(self):
        store, _ = self._seeded_store()
        dangling = make_attestation("cand_" + "0" * 64)
        errors = astore.verify_references(dangling, store.resolver_for(DOC))
        self.assertTrue(any("不可解析" in e for e in errors), errors)

    def test_evaluation_dangling_candidate_detected(self):
        store, _ = self._seeded_store()
        evaluation = {
            "schema_version": 1, "evaluation_id": "eval_" + "a1" * 6,
            "candidate_id": "cand_" + "0" * 64,
            "evaluator": {"type": "rule", "name": "deterministic-qa", "version": "qa-v1"},
            "verdict": "pass", "findings": [], "scores": {},
            "created_at": "2026-01-01T00:00:00Z",
        }
        errors = astore.verify_references(evaluation, store.resolver_for(DOC))
        self.assertTrue(any("不可解析" in e for e in errors), errors)

    def test_version_selection_segment_mismatch_detected(self):
        store, cand = self._seeded_store()
        other_seg = f"{REV}:000009:" + SRC_HASH[:8]
        version = {
            "schema_version": 1, "version_id": "version_" + "a2" * 6,
            "document_id": DOC, "revision_id": REV, "parent_version_id": None,
            "knowledge_snapshot_id": None,
            "selections": {other_seg: cand["candidate_id"]},  # key segment 与 candidate.segment 不符
            "decision": {"selected_by": "user", "reason": "x"},
            "status": "reviewed", "created_at": "2026-01-01T00:00:00Z",
        }
        errors = astore.verify_references(version, store.resolver_for(DOC))
        self.assertTrue(any("segment" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
