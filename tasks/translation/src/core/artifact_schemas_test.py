#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七类业务工件 schema 的校验、round-trip 与 stale-result 测试。"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from .artifact_schemas import (
        ARTIFACT_KINDS,
        attestation_id_for,
        build_attestation,
        candidate_id_v3,
        canonical_digest,
        check_result_against_task,
        load_schema,
        main,
        normalize_text,
        validate_artifact,
        validate_candidate_identity,
    )
except ImportError:  # unittest discover may import as top-level core.artifact_schemas_test
    from artifact_schemas import (
        ARTIFACT_KINDS,
        attestation_id_for,
        build_attestation,
        candidate_id_v3,
        canonical_digest,
        check_result_against_task,
        load_schema,
        main,
        normalize_text,
        validate_artifact,
        validate_candidate_identity,
    )


REV = "rev_" + "a" * 16
SEG = f"{REV}:000042:" + "b" * 8
HASH = "c" * 16
KNOW = "knowledge_" + "d" * 16


def make_revision():
    return {
        "schema_version": 1,
        "document_id": "pixiv:50235390:12430834",
        "revision_id": REV,
        "source": {
            "provider": "pixiv",
            "creator_id": "50235390",
            "source_id": "12430834",
            "url": "https://example.invalid/12430834",
        },
        "metadata": {"title": "原始标题", "series_title": "系列名"},
        "segments": [
            {
                "segment_id": SEG,
                "ordinal": 42,
                "kind": "body",
                "source_text": "彼女は振り返った。",
                "source_hash": HASH,
            }
        ],
    }


CAND_TEXT = "她转过身来。"


def make_candidate():
    return {
        "schema_version": 3,
        "candidate_id": candidate_id_v3(REV, SEG, HASH, CAND_TEXT),
        "document_id": "pixiv:50235390:12430834",
        "revision_id": REV,
        "segment_id": SEG,
        "source_hash": HASH,
        "normalization_version": 1,
        "text": CAND_TEXT,
    }


def make_attestation():
    return build_attestation({
        "candidate_id": candidate_id_v3(REV, SEG, HASH, CAND_TEXT),
        "producer": {"type": "api", "name": "openrouter", "model": "model-slug", "harness": None},
        "purpose": "translate",
        "parent_candidate_id": None,
        "task_id": "task_" + "f" * 12,
        "task_digest": "1" * 16,
        "result_digest": "2" * 16,
        "result_candidate_key": "option-a",
        "legacy_label": None,
        "knowledge_snapshot_id": KNOW,
        "created_at": "2026-06-12T00:00:00Z",
    })


def make_evaluation():
    return {
        "schema_version": 1,
        "evaluation_id": "eval_" + "a1" * 6,
        "candidate_id": candidate_id_v3(REV, SEG, HASH, CAND_TEXT),
        "evaluator": {"type": "rule", "name": "deterministic-qa", "version": "qa-v2"},
        "verdict": "fail",
        "findings": [
            {"code": "kana_residue", "severity": "error", "message": "译文残留假名", "evidence": "振り"}
        ],
        "scores": {},
        "created_at": "2026-06-12T00:00:01Z",
    }


def make_version():
    return {
        "schema_version": 1,
        "version_id": "version_" + "a2" * 6,
        "document_id": "pixiv:50235390:12430834",
        "revision_id": REV,
        "parent_version_id": None,
        "knowledge_snapshot_id": KNOW,
        "selections": {SEG: candidate_id_v3(REV, SEG, HASH, CAND_TEXT)},
        "decision": {"selected_by": "user", "reason": "accepted after comparison"},
        "status": "reviewed",
        "created_at": "2026-06-12T00:10:00Z",
    }


def make_annotation():
    return {
        "schema_version": 1,
        "annotation_id": "annotation_" + "a3" * 6,
        "document_id": "pixiv:50235390:12430834",
        "revision_id": REV,
        "segment_id": SEG,
        "target_candidate_id": candidate_id_v3(REV, SEG, HASH, CAND_TEXT),
        "type": "wrong_reference",
        "comment": "这里的「彼女」指小雪,不是由纪。",
        "created_by": "user",
        "created_at": "2026-06-12T00:12:00Z",
    }


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
        "constraints": {"output_language": "zh-CN", "preserve_line_count": True},
        "existing_candidate_ids": [],
        "annotation_ids": [],
        "expected_result_schema": 1,
    }


def make_result():
    return {
        "schema_version": 1,
        "task_id": "task_" + "f" * 12,
        "task_digest": canonical_digest(make_task()),
        "producer": {"type": "harness", "name": "codex", "model": "reported-model"},
        "candidates": [
            {
                "result_candidate_key": "option-a",
                "segment_id": SEG,
                "source_hash": HASH,
                "text": "她转过身来。",
                "rationale": "保持前文人物指代",
            }
        ],
        "findings": [],
        "recommended_candidate_keys": ["option-a"],
        "completed_at": "2026-06-12T00:00:00Z",
    }


FIXTURES = {
    "document-revision": make_revision,
    "candidate": make_candidate,
    "attestation": make_attestation,
    "evaluation": make_evaluation,
    "document-version": make_version,
    "annotation": make_annotation,
    "task": make_task,
    "result": make_result,
}


class SchemaValidationTest(unittest.TestCase):
    def test_all_schemas_load_and_cover_all_kinds(self):
        self.assertEqual(set(ARTIFACT_KINDS), set(FIXTURES))
        for kind in ARTIFACT_KINDS:
            load_schema(kind)

    def test_valid_fixture_per_kind(self):
        for kind, factory in FIXTURES.items():
            self.assertEqual([], validate_artifact(kind, factory()), kind)

    def test_round_trip_per_kind(self):
        for kind, factory in FIXTURES.items():
            doc = factory()
            restored = json.loads(json.dumps(doc, ensure_ascii=False))
            self.assertEqual(doc, restored, kind)
            self.assertEqual([], validate_artifact(kind, restored), kind)
            self.assertEqual(canonical_digest(doc), canonical_digest(restored), kind)

    def test_wrong_schema_version_rejected(self):
        for kind, factory in FIXTURES.items():
            doc = factory()
            doc["schema_version"] = 99
            self.assertNotEqual([], validate_artifact(kind, doc), kind)

    def test_missing_required_field_rejected(self):
        for kind, factory in FIXTURES.items():
            doc = factory()
            doc.pop(sorted(k for k in doc if k != "schema_version")[0])
            self.assertNotEqual([], validate_artifact(kind, doc), kind)

    def test_extra_property_rejected(self):
        for kind, factory in FIXTURES.items():
            doc = factory()
            doc["unexpected_field"] = 1
            self.assertNotEqual([], validate_artifact(kind, doc), kind)

    def test_attestation_requires_idempotency_fields_present(self):
        # api/harness 自动产出:task/result digest/key 必须存在且非 null
        doc = make_attestation()
        doc["task_digest"] = None
        self.assertNotEqual([], validate_artifact("attestation", doc))
        # 人工/遗留来源:幂等字段可为 null
        doc = make_attestation()
        doc["producer"]["type"] = "legacy"
        for key in ("task_id", "task_digest", "result_digest", "result_candidate_key"):
            doc[key] = None
        doc["legacy_label"] = "dir_bilingual"
        doc["attestation_id"] = attestation_id_for(
            {k: v for k, v in doc.items() if k not in ("attestation_id", "schema_version")}
        )
        self.assertEqual([], validate_artifact("attestation", doc))

    def test_candidate_has_no_provenance_fields(self):
        # v3 candidate 是纯内容:不得再带 producer/provenance/purpose/parent/created_at
        doc = make_candidate()
        for forbidden in ("producer", "provenance", "purpose", "parent_candidate_id", "created_at"):
            tampered = dict(doc)
            tampered[forbidden] = None
            self.assertNotEqual([], validate_artifact("candidate", tampered), forbidden)

    def test_bad_identity_patterns_rejected(self):
        doc = make_revision()
        doc["document_id"] = "twitter:1:2"
        self.assertNotEqual([], validate_artifact("document-revision", doc))
        doc = make_task()
        doc["segment_ids"] = ["not-a-segment-id"]
        self.assertNotEqual([], validate_artifact("task", doc))

    def test_task_existing_candidate_ids_accept_v3_reject_legacy(self):
        # Task.existing_candidate_ids 必须能引用本提交所产的 v3 candidate(64-hex),否则
        # export_task 引用真实 candidate 会被判非法(Codex PR#64 P1)
        v3 = candidate_id_v3(REV, SEG, HASH, CAND_TEXT)
        ok = make_task()
        ok["existing_candidate_ids"] = [v3]
        self.assertEqual([], validate_artifact("task", ok))
        bad = make_task()
        bad["existing_candidate_ids"] = ["cand_" + "e" * 16]  # 旧 16-hex 不再合法
        self.assertNotEqual([], validate_artifact("task", bad))


class StaleResultTest(unittest.TestCase):
    def test_matching_result_passes(self):
        self.assertEqual([], check_result_against_task(make_task(), make_result()))

    def test_stale_source_hash_quarantined(self):
        result = make_result()
        result["candidates"][0]["source_hash"] = "9" * 16
        errors = check_result_against_task(make_task(), result)
        self.assertTrue(any("stale source_hash" in e for e in errors), errors)

    def test_unknown_segment_quarantined(self):
        other_seg = f"{REV}:000099:" + "b" * 8
        result = make_result()
        result["candidates"][0]["segment_id"] = other_seg
        errors = check_result_against_task(make_task(), result)
        self.assertTrue(any("not in task.segment_ids" in e for e in errors), errors)

    def test_changed_task_content_invalidates_result_digest(self):
        # task 内容变化(如 context_digest)时,旧 result 的 task_digest 必须失配进 quarantine
        task = make_task()
        task["context_digest"] = "9" * 16
        errors = check_result_against_task(task, make_result())
        self.assertTrue(any("task_digest mismatch" in e for e in errors), errors)

    def test_task_id_and_schema_mismatch(self):
        result = make_result()
        result["task_id"] = "task_" + "0" * 12
        result["schema_version"] = 7
        errors = check_result_against_task(make_task(), result)
        self.assertEqual(2, len(errors), errors)


# 钉死的已知向量(Codex 与 Claude Code 独立核算一致):canonical 字段/序列化口径被意外改动会立刻红。
PINNED_CANDIDATE_ID = "cand_8b41fbda2bda4b1a34ff8c828d903e342916ff718ab90f66d8a9850539ca86eb"
PINNED_ATTESTATION_ID = "att_04cca1ff478923a8e141c911657e33045dc74555ff02af036325f2b7e30f9eaf"


class CandidateIdDerivationTest(unittest.TestCase):
    def test_content_address_is_stable_full_hex(self):
        cid = candidate_id_v3(REV, SEG, HASH, CAND_TEXT)
        self.assertRegex(cid, r"^cand_[0-9a-f]{64}$")
        self.assertEqual(cid, candidate_id_v3(REV, SEG, HASH, CAND_TEXT))

    def test_pinned_known_vector(self):
        # 不只是"两次调用相等",而是钉死具体摘要 → 抓 canonical 字段/序列化口径漂移
        self.assertEqual(PINNED_CANDIDATE_ID, candidate_id_v3(REV, SEG, HASH, CAND_TEXT))
        self.assertEqual(PINNED_ATTESTATION_ID, make_attestation()["attestation_id"])

    def test_same_text_dedup_across_producers(self):
        # 内容寻址:同 (revision, segment, source_hash, 归一化文本) → 同 id,与 producer 无关
        a = candidate_id_v3(REV, SEG, HASH, CAND_TEXT)
        b = candidate_id_v3(REV, SEG, HASH, CAND_TEXT)
        self.assertEqual(a, b)

    def test_different_text_yields_new_candidate(self):
        a = candidate_id_v3(REV, SEG, HASH, "译文甲")
        b = candidate_id_v3(REV, SEG, HASH, "译文乙")
        self.assertNotEqual(a, b)

    def test_identity_depends_on_each_component(self):
        base = candidate_id_v3(REV, SEG, HASH, CAND_TEXT)
        other_seg = f"{REV}:000099:" + "b" * 8
        self.assertNotEqual(base, candidate_id_v3(REV, other_seg, HASH, CAND_TEXT))
        self.assertNotEqual(base, candidate_id_v3(REV, SEG, "9" * 16, CAND_TEXT))
        self.assertNotEqual(base, candidate_id_v3("rev_" + "9" * 16, SEG, HASH, CAND_TEXT))

    def test_derived_id_passes_candidate_schema(self):
        doc = make_candidate()
        doc["candidate_id"] = candidate_id_v3(REV, SEG, HASH, CAND_TEXT)
        self.assertEqual([], validate_artifact("candidate", doc))


class NormalizationTest(unittest.TestCase):
    def test_v1_strips_trailing_whitespace_only(self):
        self.assertEqual("你好", normalize_text("你好   "))
        self.assertEqual("你好", normalize_text("你好\t\n"))

    def test_v1_preserves_internal_whitespace_and_punctuation(self):
        # display-preserving:不折叠内部空白、不改标点/引号
        self.assertEqual("「甲  乙」", normalize_text("「甲  乙」"))
        self.assertEqual("a b\tc", normalize_text("a b\tc"))

    def test_v1_applies_nfc(self):
        decomposed = "ガ"  # カ + 浊音符 → ガ(NFC 合成)
        self.assertEqual("ガ", normalize_text(decomposed))

    def test_unsupported_version_raises(self):
        with self.assertRaises(ValueError):
            normalize_text("x", normalization_version=2)


class AttestationIdDerivationTest(unittest.TestCase):
    def test_deterministic_and_full_hex(self):
        att = make_attestation()
        self.assertRegex(att["attestation_id"], r"^att_[0-9a-f]{64}$")
        self.assertEqual(att["attestation_id"], make_attestation()["attestation_id"])

    def test_distinct_provenance_yields_distinct_attestation(self):
        a = make_attestation()
        b = make_attestation()
        b_core = {k: v for k, v in b.items() if k not in ("attestation_id", "schema_version")}
        b_core["result_digest"] = "9" * 16
        self.assertNotEqual(a["attestation_id"], attestation_id_for(b_core))

    def test_build_attestation_rejects_reserved_fields(self):
        # 公共构造函数自洽:core 不得携带生成字段(否则污染身份派生)
        for reserved in ("schema_version", "attestation_id", "attestation_identity_version"):
            core = {k: v for k, v in make_attestation().items()
                    if k not in ("attestation_id", "schema_version")}
            core[reserved] = "x"
            with self.assertRaises(ValueError, msg=reserved):
                build_attestation(core)


class CandidateIdentityValidationTest(unittest.TestCase):
    def test_self_consistent_candidate_passes(self):
        self.assertEqual([], validate_candidate_identity(make_candidate()))

    def test_tampered_text_rejected(self):
        # text 被改但 candidate_id 没变 → schema 仍过,身份校验必须抓住
        doc = make_candidate()
        doc["text"] = "完全不同的译文"
        self.assertNotEqual([], validate_candidate_identity(doc))

    def test_tampered_id_rejected(self):
        doc = make_candidate()
        doc["candidate_id"] = "cand_" + "0" * 64
        self.assertNotEqual([], validate_candidate_identity(doc))

    def test_unnormalized_text_rejected(self):
        # 带尾随空白 = 未归一化:即便重算 id 与之匹配,也要因 text != normalized 被拒
        text = CAND_TEXT + "   "
        doc = make_candidate()
        doc["text"] = text
        doc["candidate_id"] = candidate_id_v3(REV, SEG, HASH, text)
        errors = validate_candidate_identity(doc)
        self.assertTrue(any("归一化" in e for e in errors), errors)

    def test_normalization_version_other_than_1_rejected_by_schema(self):
        doc = make_candidate()
        doc["normalization_version"] = 2
        self.assertNotEqual([], validate_artifact("candidate", doc))

    def _run_cli(self, doc):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate.json"
            path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            with mock.patch("sys.argv", ["prog", "candidate", str(path)]):
                return main()

    def test_cli_enforces_candidate_identity(self):
        # 校验 CLI 是独立入口:schema 合法但身份被篡改的 candidate 也必须非零退出
        self.assertEqual(0, self._run_cli(make_candidate()))
        tampered = make_candidate()
        tampered["text"] = "完全不同的译文"  # id 没变 → schema 过、身份不过
        self.assertEqual(1, self._run_cli(tampered))


if __name__ == "__main__":
    unittest.main()
