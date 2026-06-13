#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七类业务工件 schema 的校验、round-trip 与 stale-result 测试。"""

from __future__ import annotations

import copy
import json
import unittest

try:
    from .artifact_schemas import (
        ARTIFACT_KINDS,
        candidate_id_for,
        canonical_digest,
        check_result_against_task,
        load_schema,
        validate_artifact,
    )
except ImportError:  # unittest discover may import as top-level core.artifact_schemas_test
    from artifact_schemas import (
        ARTIFACT_KINDS,
        candidate_id_for,
        canonical_digest,
        check_result_against_task,
        load_schema,
        validate_artifact,
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


def make_candidate():
    return {
        "schema_version": 2,
        "candidate_id": "cand_" + "e" * 16,
        "document_id": "pixiv:50235390:12430834",
        "revision_id": REV,
        "segment_id": SEG,
        "source_hash": HASH,
        "text": "她转过身来。",
        "purpose": "initial",
        "parent_candidate_id": None,
        "producer": {"type": "api", "name": "openrouter", "model": "model-slug", "harness": None},
        "provenance": {
            "task_id": "task_" + "f" * 12,
            "task_digest": "1" * 16,
            "result_digest": "2" * 16,
            "result_candidate_key": "option-a",
            "prompt_version": "body-v3",
            "recipe_id": "fanbox-default-v2",
            "knowledge_snapshot_id": KNOW,
        },
        "created_at": "2026-06-12T00:00:00Z",
    }


def make_evaluation():
    return {
        "schema_version": 1,
        "evaluation_id": "eval_" + "a1" * 6,
        "candidate_id": "cand_" + "e" * 16,
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
        "selections": {SEG: "cand_" + "e" * 16},
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
        "target_candidate_id": "cand_" + "e" * 16,
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

    def test_candidate_requires_idempotency_fields_present(self):
        doc = make_candidate()
        del doc["provenance"]["result_digest"]
        errors = validate_artifact("candidate", doc)
        self.assertTrue(any("result_digest" in e for e in errors), errors)
        # 人工/遗留候选:字段必须存在但可为 null
        doc = make_candidate()
        doc["producer"]["type"] = "human"
        for key in ("task_id", "task_digest", "result_digest", "result_candidate_key"):
            doc["provenance"][key] = None
        self.assertEqual([], validate_artifact("candidate", doc))
        # api/harness 自动生成候选:幂等字段不得为 null
        doc = make_candidate()
        doc["producer"]["type"] = "api"
        doc["provenance"]["task_digest"] = None
        self.assertNotEqual([], validate_artifact("candidate", doc))

    def test_bad_identity_patterns_rejected(self):
        doc = make_revision()
        doc["document_id"] = "twitter:1:2"
        self.assertNotEqual([], validate_artifact("document-revision", doc))
        doc = make_task()
        doc["segment_ids"] = ["not-a-segment-id"]
        self.assertNotEqual([], validate_artifact("task", doc))


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


class CandidateIdDerivationTest(unittest.TestCase):
    def test_known_vector_is_stable(self):
        cid = candidate_id_for("1" * 16, "2" * 16, "option-a", SEG)
        self.assertRegex(cid, r"^cand_[0-9a-f]{16}$")
        self.assertEqual(cid, candidate_id_for("1" * 16, "2" * 16, "option-a", SEG))

    def test_different_execution_yields_new_candidate(self):
        a = candidate_id_for("1" * 16, "2" * 16, "option-a", SEG)
        b = candidate_id_for("1" * 16, "3" * 16, "option-a", SEG)
        self.assertNotEqual(a, b)

    def test_derived_id_passes_candidate_schema(self):
        doc = make_candidate()
        doc["candidate_id"] = candidate_id_for("1" * 16, "2" * 16, "option-a", SEG)
        self.assertEqual([], validate_artifact("candidate", doc))


if __name__ == "__main__":
    unittest.main()
