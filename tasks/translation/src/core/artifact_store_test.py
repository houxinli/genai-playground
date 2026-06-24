#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ArtifactStore:分片路径、原子批写、幂等/冲突、candidate 身份 gate、cross-artifact integrity。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import artifact_store as astore
    from .artifact_schemas import build_attestation, candidate_id_v3, normalize_text, version_id_for
    from .source_identity import _source_hash
except ImportError:  # core/ 在 sys.path 上
    import artifact_store as astore
    from artifact_schemas import build_attestation, candidate_id_v3, normalize_text, version_id_for
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

    def test_put_many_rejects_tampered_attestation_id(self):
        # #77:store 写入 gate 对 attestation 也重算 id,篡改 id 必拒
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            cand = make_candidate()
            att = make_attestation(cand["candidate_id"])
            att["attestation_id"] = "att_" + "0" * 64  # 与内容不符
            with self.assertRaises(ValueError):
                store.put_many(DOC, [make_revision(), cand, att])

    def test_shard_files_are_per_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            cand = make_candidate()
            store.put_many(DOC, [make_revision(), cand, make_attestation(cand["candidate_id"])])
            self.assertTrue(store.shard_path("candidate", DOC).exists())
            self.assertTrue(store.shard_path("attestation", DOC).exists())
            # 没有遗留临时文件
            self.assertEqual([], list(Path(tmp).rglob("*.tmp")))

    def test_same_text_two_labels_dedup_one_candidate_two_attestations(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            cand = make_candidate()
            store.put_many(DOC, [make_revision(), cand, make_attestation(cand["candidate_id"], "dir_bilingual")])
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
            store.put_many(DOC, [make_revision(), cand])
            self.assertTrue(store.exists("candidate", DOC, cand["candidate_id"]))
            self.assertEqual(cand, store.get("candidate", DOC, cand["candidate_id"]))
            self.assertFalse(store.exists("candidate", DOC, "cand_" + "0" * 64))

    def test_integrity_gate_rejects_candidate_without_revision(self):
        # 写入边界强制 integrity:没有对应 DocumentRevision 的 candidate 整批拒绝,零落盘
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            with self.assertRaises(astore.StoreIntegrityError):
                store.put_many(DOC, [make_candidate()])
            self.assertEqual([], list(Path(tmp).rglob("*.jsonl")))

    def test_document_id_mismatch_rejected(self):
        # 工件自带 document_id 与分片键不一致 → 拒绝(防污染错误文档 shard)
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            with self.assertRaises(ValueError):
                store.put_many("pixiv:999:888", [make_revision()])  # revision.document_id == DOC

    def test_all_or_nothing_across_shards_on_conflict(self):
        # 一批跨多 shard:某 shard 冲突时,不得留下其它 shard 的半批提交
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            store.put_many(DOC, [make_revision()])  # 先有 revision
            new_cand = make_candidate("另一句译文")           # 合法、身份自洽、revision 已在 store
            corrupt_rev = make_revision()
            corrupt_rev["metadata"] = {"title": "被改的标题"}  # 同 revision_id 不同内容 → 冲突
            with self.assertRaises(astore.StoreConflictError):
                store.put_many(DOC, [new_cand, corrupt_rev])
            # candidate 不得因另一个 shard 冲突而落盘
            self.assertFalse(store.exists("candidate", DOC, new_cand["candidate_id"]))


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
            "schema_version": 2, "version_id": "version_" + "a2" * 6,
            "document_id": DOC, "revision_id": REV, "parent_version_id": None,
            "knowledge_snapshot_id": None,
            "selections": {other_seg: cand["candidate_id"]},  # key segment 与 candidate.segment 不符
            "selection_decisions": {other_seg: {
                "selected_by": "policy", "outcome": "select_challenger",
                "reason_code": "initial_single_passing_candidate",
                "incumbent_candidate_id": None, "evaluation_ids": [],
            }},
            "decision": {"policy_id": "conservative-select-v1", "created_by": "workflow"},
            "status": "reviewed", "created_at": "2026-01-01T00:00:00Z",
        }
        errors = astore.verify_references(version, store.resolver_for(DOC))
        self.assertTrue(any("segment" in e for e in errors), errors)

    def test_version_decision_evaluation_for_other_segment_detected(self):
        # decision 引用的 evaluation 评的是别的 segment 的候选 → 借用证据,必须报错
        _, cand = self._seeded_store()
        other_seg = f"{REV}:000009:" + SRC_HASH[:8]
        other_cand = dict(make_candidate(text="另一句"))
        other_cand["segment_id"] = other_seg
        other_cand["candidate_id"] = candidate_id_v3(REV, other_seg, SRC_HASH, normalize_text("另一句"))
        evaluation = {
            "schema_version": 1, "evaluation_id": "eval_" + "c7" * 6,
            "candidate_id": other_cand["candidate_id"],
            "evaluator": {"type": "rule", "name": "deterministic-qa", "version": "qa-v1"},
            "verdict": "pass", "findings": [], "scores": {},
            "created_at": "2026-01-01T00:00:00Z",
        }
        artifacts = {
            ("candidate", cand["candidate_id"]): cand,
            ("candidate", other_cand["candidate_id"]): other_cand,
            ("evaluation", evaluation["evaluation_id"]): evaluation,
        }
        resolver = lambda kind, art_id: artifacts.get((kind, art_id))  # noqa: E731
        version = {
            "schema_version": 2, "version_id": "version_" + "a2" * 6,
            "document_id": DOC, "revision_id": REV, "parent_version_id": None,
            "knowledge_snapshot_id": None,
            "selections": {SEG: cand["candidate_id"]},
            "selection_decisions": {SEG: {
                "selected_by": "policy", "outcome": "select_challenger",
                "reason_code": "initial_single_passing_candidate",
                "incumbent_candidate_id": None,
                "evaluation_ids": [evaluation["evaluation_id"]],  # 评的是 other_seg 的候选
            }},
            "decision": {"policy_id": "conservative-select-v1", "created_by": "workflow"},
            "status": "draft", "created_at": "2026-01-01T00:00:00Z",
        }
        errors = astore.verify_references(version, resolver)
        self.assertTrue(any("segment" in e for e in errors), errors)

    def test_version_dangling_parent_detected(self):
        store, cand = self._seeded_store()
        version = {
            "schema_version": 2, "version_id": "version_" + "a2" * 6,
            "document_id": DOC, "revision_id": REV,
            "parent_version_id": "version_" + "9" * 12,  # 不存在的父版本
            "knowledge_snapshot_id": None,
            "selections": {SEG: cand["candidate_id"]},
            "selection_decisions": {SEG: {
                "selected_by": "policy", "outcome": "select_challenger",
                "reason_code": "initial_single_passing_candidate",
                "incumbent_candidate_id": None, "evaluation_ids": [],
            }},
            "decision": {"policy_id": "conservative-select-v1", "created_by": "workflow"},
            "status": "reviewed", "created_at": "2026-01-01T00:00:00Z",
        }
        errors = astore.verify_references(version, store.resolver_for(DOC))
        self.assertTrue(any("parent" in e for e in errors), errors)

    def _annotation(self, target, segment_id=SEG):
        return {
            "schema_version": 1, "annotation_id": "annotation_" + "a3" * 6,
            "document_id": DOC, "revision_id": REV, "segment_id": segment_id,
            "target_candidate_id": target, "type": "wrong_reference",
            "comment": "x", "created_by": "user", "created_at": "2026-01-01T00:00:00Z",
        }

    def test_annotation_consistent_passes(self):
        store, cand = self._seeded_store()
        self.assertEqual([], astore.verify_references(self._annotation(cand["candidate_id"]), store.resolver_for(DOC)))

    def test_annotation_target_segment_mismatch_detected(self):
        # target candidate 真实存在,但 annotation 声明的 segment 与其不符 → 必须抓住(防反馈应用到错句)
        store, cand = self._seeded_store()
        other_seg = f"{REV}:000009:" + SRC_HASH[:8]
        errors = astore.verify_references(self._annotation(cand["candidate_id"], other_seg), store.resolver_for(DOC))
        self.assertTrue(any("segment" in e for e in errors), errors)

    def test_annotation_null_target_still_checks_segment(self):
        store, _ = self._seeded_store()
        other_seg = f"{REV}:000009:" + SRC_HASH[:8]
        errors = astore.verify_references(self._annotation(None, other_seg), store.resolver_for(DOC))
        self.assertTrue(any("segment" in e for e in errors), errors)


class CommitOrderTest(unittest.TestCase):
    def test_full_batch_commits_referenced_before_referencing(self):
        # 依赖序提交:被引用者(revision)先于引用方(candidate/attestation)。校验全批一次落盘且自洽。
        with tempfile.TemporaryDirectory() as tmp:
            store = astore.ArtifactStore(Path(tmp))
            cand = make_candidate()
            report = store.put_many(DOC, [make_attestation(cand["candidate_id"]), cand, make_revision()])
            self.assertEqual(1, report["kinds"]["document-revision"]["written"])
            self.assertEqual(1, report["kinds"]["candidate"]["written"])
            self.assertEqual(1, report["kinds"]["attestation"]["written"])
            # 提交顺序固定(被引用者先),与传入顺序无关
            self.assertLess(
                astore.COMMIT_ORDER.index("document-revision"),
                astore.COMMIT_ORDER.index("candidate"),
            )


def _version(cand, created_at="2026-01-01T00:00:00Z"):
    content = {
        "schema_version": 2, "document_id": DOC, "revision_id": REV,
        "parent_version_id": None, "knowledge_snapshot_id": None,
        "selections": {SEG: cand["candidate_id"]},
        "selection_decisions": {SEG: {
            "selected_by": "policy", "outcome": "select_challenger",
            "reason_code": "initial_single_passing_candidate",
            "incumbent_candidate_id": None, "evaluation_ids": [],
        }},
        "decision": {"policy_id": "conservative-select-v1", "created_by": "workflow"},
        "status": "draft", "created_at": created_at,
    }
    return {"version_id": version_id_for(content), **content}


class PublishTest(unittest.TestCase):
    def _seeded(self, tmp):
        store = astore.ArtifactStore(Path(tmp))
        cand = make_candidate()
        store.put_many(DOC, [make_revision(), cand, make_attestation(cand["candidate_id"])])
        return store, cand

    def test_publish_sets_current_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, cand = self._seeded(tmp)
            v = _version(cand); store.put_many(DOC, [v])
            self.assertIsNone(store.current_ref(DOC))
            ref = store.publish(DOC, v["version_id"], published_at="2026-02-02T00:00:00Z")
            self.assertEqual(v["version_id"], ref["version_id"])
            self.assertIsNone(ref["parent_version_id"])
            self.assertEqual(v["version_id"], store.current_ref(DOC)["version_id"])

    def test_publish_cas_success_records_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, cand = self._seeded(tmp)
            v1 = _version(cand, "2026-01-01T00:00:00Z"); store.put_many(DOC, [v1])
            v2 = _version(cand, "2026-03-03T00:00:00Z"); store.put_many(DOC, [v2])
            store.publish(DOC, v1["version_id"])
            ref = store.publish(DOC, v2["version_id"], expected_version_id=v1["version_id"])
            self.assertEqual(v2["version_id"], ref["version_id"])
            self.assertEqual(v1["version_id"], ref["parent_version_id"])  # CAS 记录 parent

    def test_publish_cas_conflict_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, cand = self._seeded(tmp)
            v1 = _version(cand, "2026-01-01T00:00:00Z"); store.put_many(DOC, [v1])
            v2 = _version(cand, "2026-03-03T00:00:00Z"); store.put_many(DOC, [v2])
            store.publish(DOC, v1["version_id"])
            with self.assertRaises(astore.StoreConflictError):
                store.publish(DOC, v2["version_id"], expected_version_id="version_" + "0" * 40)
            self.assertEqual(v1["version_id"], store.current_ref(DOC)["version_id"])  # 未被覆盖

    def test_publish_defaults_to_real_timestamp(self):
        # 不传 published_at 时记真实 UTC,不留 1970 占位(current ref 是审计/排序依据)
        with tempfile.TemporaryDirectory() as tmp:
            store, cand = self._seeded(tmp)
            v = _version(cand); store.put_many(DOC, [v])
            ref = store.publish(DOC, v["version_id"])
            self.assertNotIn("1970", ref["published_at"])
            self.assertTrue(ref["published_at"].startswith("20"))

    def test_publish_unknown_version_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _ = self._seeded(tmp)
            with self.assertRaises(ValueError):
                store.publish(DOC, "version_" + "0" * 40)  # 不在 store(发布≠创建)
            self.assertIsNone(store.current_ref(DOC))


if __name__ == "__main__":
    unittest.main()
