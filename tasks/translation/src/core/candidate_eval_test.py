#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""candidate QA 评估:好/坏 candidate 的 verdict 与 findings。"""

from __future__ import annotations

import unittest

try:
    from . import candidate_eval as ce
    from .artifact_schemas import validate_artifact
except ImportError:  # core/ 在 sys.path 上
    import candidate_eval as ce
    from artifact_schemas import validate_artifact


def _candidate(text, cid="cand_" + "e" * 16):
    return {
        "schema_version": 2,
        "candidate_id": cid,
        "document_id": "pixiv:1:2",
        "revision_id": "rev_" + "a" * 16,
        "segment_id": f"rev_{'a' * 16}:000000:" + "b" * 8,
        "source_hash": "c" * 16,
        "text": text,
        "purpose": "translate",
        "parent_candidate_id": None,
        "producer": {"type": "harness", "name": "claude-code", "model": None, "harness": "claude-code"},
        "provenance": {
            "task_id": "task_" + "f" * 12, "task_digest": "1" * 16, "result_digest": "2" * 16,
            "result_candidate_key": "option-a", "prompt_version": None, "recipe_id": None,
            "knowledge_snapshot_id": None,
        },
        "created_at": "2026-06-13T00:00:00Z",
    }


SOURCE = "彼女は振り返った。"


class CandidateEvalTest(unittest.TestCase):
    def test_good_candidate_passes(self):
        ev = ce.evaluate_candidate(_candidate("她转过身来。"), SOURCE)
        self.assertEqual([], validate_artifact("evaluation", ev))
        self.assertEqual("pass", ev["verdict"])
        self.assertEqual([], ev["findings"])
        self.assertEqual(0, ce.error_count(ev))

    def test_kana_residue_fails(self):
        ev = ce.evaluate_candidate(_candidate("她振り返了。"), SOURCE)
        self.assertEqual("fail", ev["verdict"])
        self.assertTrue(any(f["code"] == "kana_residue" for f in ev["findings"]))

    def test_same_as_source_fails(self):
        ev = ce.evaluate_candidate(_candidate(SOURCE), SOURCE)
        self.assertEqual("fail", ev["verdict"])
        codes = {f["code"] for f in ev["findings"]}
        self.assertIn("same_as_source", codes)
        self.assertIn("kana_residue", codes)  # 原文含假名 → 也触发

    def test_empty_translation_fails(self):
        ev = ce.evaluate_candidate(_candidate("   "), SOURCE)
        self.assertEqual("fail", ev["verdict"])
        self.assertEqual(["empty_translation"], [f["code"] for f in ev["findings"]])

    def test_refusal_and_failure_markers(self):
        ev = ce.evaluate_candidate(_candidate("抱歉，[翻译失败]"), SOURCE)
        codes = {f["code"] for f in ev["findings"]}
        self.assertIn("refusal_marker", codes)
        self.assertIn("failure_marker", codes)
        self.assertGreaterEqual(ce.error_count(ev), 2)

    def test_evaluation_is_deterministic(self):
        a = ce.evaluate_candidate(_candidate("她转过身来。"), SOURCE)
        b = ce.evaluate_candidate(_candidate("她转过身来。"), SOURCE)
        self.assertEqual(a["evaluation_id"], b["evaluation_id"])
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
