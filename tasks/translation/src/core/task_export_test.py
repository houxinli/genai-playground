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
    from .artifact_store import ArtifactStore
except ImportError:  # core/ 在 sys.path 上
    import result_import as ri
    import source_identity as si
    import task_export as te
    from artifact_schemas import canonical_digest, validate_artifact
    from artifact_store import ArtifactStore


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
            store = ArtifactStore(Path(tmp))
            store.put_many(rev["document_id"], [rev])  # 先入源 revision,供 integrity gate
            report = ri.import_result(task, result, store)
            self.assertFalse(report["quarantined"], report)
            self.assertEqual(len(bundle["segments"]), report["written"])
            doc = task["document_id"]
            self.assertEqual(len(bundle["segments"]), len(store.list_shard("candidate", doc)))
            self.assertEqual(len(bundle["segments"]), len(store.list_shard("attestation", doc)))


    def test_ingest_revision_closes_loop_for_new_document(self):
        # 全新文档:仅靠 export 端的 ingest_revision 入库(无手动 seed),import_result 即不再 quarantine
        rev = _revision()
        bundle = te.export_job(rev, _body_ids(rev))
        task = bundle["task"]
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
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp))
            te.ingest_revision(rev, store)  # 生产入库点,取代手动 seed
            report = ri.import_result(task, result, store)
            self.assertFalse(report["quarantined"], report)
            doc = task["document_id"]
            self.assertEqual(1, len(store.list_shard("document-revision", doc)))
            self.assertEqual(len(bundle["segments"]), len(store.list_shard("candidate", doc)))
            self.assertEqual(len(bundle["segments"]), len(store.list_shard("attestation", doc)))

    def test_ingest_revision_is_idempotent(self):
        rev = _revision()
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp))
            first = te.ingest_revision(rev, store)
            second = te.ingest_revision(rev, store)
            self.assertEqual(1, first["kinds"]["document-revision"]["written"])
            self.assertEqual(1, second["kinds"]["document-revision"]["skipped"])
            self.assertEqual(1, len(store.list_shard("document-revision", rev["document_id"])))

    def test_ingest_rejects_tampered_revision_before_write(self):
        # schema 仍合法但 source_text 被改、id 未更新 → 入库前拒绝,store 不被污染
        rev = _revision()
        rev["segments"][-1]["source_text"] = "被篡改的原文。"  # source_hash/segment_id/revision_id 都不再自洽
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp))
            with self.assertRaises(ValueError):
                te.ingest_revision(rev, store)
            self.assertEqual([], store.list_shard("document-revision", rev["document_id"]))

    def test_ingest_rejects_stale_revision_id(self):
        # metadata 漂移但 revision_id 保持旧值 → 必须拒绝(否则日后正确 revision 同 ID 冲突)
        rev = _revision()
        rev["metadata"]["title"] = (rev["metadata"].get("title") or "") + "X"
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp))
            with self.assertRaises(ValueError):
                te.ingest_revision(rev, store)

    def test_verify_revision_identity_passes_for_built_revision(self):
        self.assertEqual([], si.verify_revision_identity(_revision()))

    def test_tampered_revision_rejected(self):
        # source_text 被改但 source_hash 没同步 -> 导出必须拒绝(防绕过 stale 防护)
        rev = _revision()
        rev["segments"][-1]["source_text"] = "被篡改的原文。"
        with self.assertRaises(ValueError):
            te.export_task(rev, _body_ids(rev))

    def test_task_id_covers_reference_fields(self):
        rev = _revision(); ids = _body_ids(rev)
        base = te.export_task(rev, ids)
        with_ann = te.export_task(rev, ids, annotation_ids=["annotation_" + "a" * 12])
        self.assertNotEqual(base["task_id"], with_ann["task_id"])  # 引用不同 -> id 不同

    def test_export_job_rejects_unsupported_until_context_builder(self):
        rev = _revision(); ids = _body_ids(rev)
        with self.assertRaises(ValueError):
            te.export_job(rev, ids, task_type="repair")
        with self.assertRaises(ValueError):
            te.export_job(rev, ids, annotation_ids=["annotation_" + "a" * 12])


    def test_revision_from_source(self):
        # 从 fixture 源目录适配出指定 document 的 revision
        rev = te.revision_from_source(
            "pixiv", SRC.parent, "pixiv:700000:700001")
        self.assertEqual("pixiv:700000:700001", rev["document_id"])
        self.assertEqual([], validate_artifact("document-revision", rev))
        with self.assertRaises(ValueError):
            te.revision_from_source("pixiv", SRC.parent, "pixiv:0:0")

    def test_revision_from_source_ignores_unrelated_bad_file(self):
        import tempfile, shutil
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            shutil.copy(SRC, tmp / "700001.txt")
            (tmp / "junk.txt").write_text("不是合法 front matter", encoding="utf-8")  # 无关坏文件
            rev = te.revision_from_source("pixiv", tmp, "pixiv:700000:700001")
            self.assertEqual("pixiv:700000:700001", rev["document_id"])


class ContextPackTest(unittest.TestCase):
    ENTITY = {"source": "ユキ", "target": "小雪", "forbidden": ["雪"]}
    TERM = {"source": "魔法", "target": "魔法"}

    def test_bundle_carries_context_pack_with_derived_neighbors(self):
        rev = _revision()
        ids = _body_ids(rev)
        bundle = te.export_job(rev, ids, terminology=[self.TERM], entities=[self.ENTITY])
        pack = bundle["context_pack"]
        self.assertEqual([self.ENTITY], pack["entities"])
        self.assertEqual([self.TERM], pack["terminology"])
        # 两个 body segment 互为邻句:首段有 next、末段有 prev
        first, last = ids[0], ids[-1]
        self.assertIn("next", pack["neighbors"][first])
        self.assertIn("prev", pack["neighbors"][last])
        self.assertNotIn("prev", pack["neighbors"][first])

    def test_neighbors_use_full_body_order_even_for_subset(self):
        # 只选末段,邻句仍能取到文档里它前面的 body 源句
        rev = _revision()
        ids = _body_ids(rev)
        bundle = te.export_job(rev, [ids[-1]])
        self.assertEqual(
            rev["segments"][[s["segment_id"] for s in rev["segments"]].index(ids[0])]["source_text"],
            bundle["context_pack"]["neighbors"][ids[-1]]["prev"],
        )

    def test_context_changes_task_id_and_is_deterministic(self):
        rev = _revision()
        ids = _body_ids(rev)
        plain = te.export_job(rev, ids)["task"]["task_id"]
        with_ent = te.export_job(rev, ids, entities=[self.ENTITY])["task"]["task_id"]
        with_ent2 = te.export_job(rev, ids, entities=[self.ENTITY])["task"]["task_id"]
        self.assertNotEqual(plain, with_ent)  # 上下文进身份
        self.assertEqual(with_ent, with_ent2)  # 同上下文确定性

    def test_entities_order_independent_identity(self):
        rev = _revision()
        ids = _body_ids(rev)
        e2 = {"source": "マホ", "target": "真秀"}
        a = te.export_job(rev, ids, entities=[self.ENTITY, e2])["task"]["task_id"]
        b = te.export_job(rev, ids, entities=[e2, self.ENTITY])["task"]["task_id"]
        self.assertEqual(a, b)  # entities 按 canonical 排序 → 与输入顺序无关

    def test_no_context_bundle_round_trips_without_regression(self):
        # 无 context 输入:bundle 仍带 context_pack(空约束),import_result 不读它 → 不回退
        rev = _revision()
        bundle = te.export_job(rev, _body_ids(rev))
        self.assertEqual([], bundle["context_pack"]["entities"])
        task = bundle["task"]
        fake_tr = {"「おはよう」": "「早上好」", "今日はいい天気だ。": "今天天气真好。"}
        result = {
            "schema_version": 1, "task_id": task["task_id"], "task_digest": bundle["task_digest"],
            "producer": {"type": "harness", "name": "claude-code", "model": None},
            "candidates": [
                {"result_candidate_key": "option-a", "segment_id": s["segment_id"],
                 "source_hash": task["source_hashes"][s["segment_id"]], "text": fake_tr[s["source_text"]]}
                for s in bundle["segments"]
            ],
            "findings": [], "recommended_candidate_keys": ["option-a"],
            "completed_at": "2026-06-13T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp))
            te.ingest_revision(rev, store)
            report = ri.import_result(task, result, store)
            self.assertFalse(report["quarantined"], report)
            self.assertEqual(len(bundle["segments"]), report["written"])

    def test_export_job_still_rejects_external_refs(self):
        rev = _revision(); ids = _body_ids(rev)
        with self.assertRaises(ValueError):
            te.export_job(rev, ids, knowledge_snapshot_id="knowledge_" + "a" * 16)


if __name__ == "__main__":
    unittest.main()
