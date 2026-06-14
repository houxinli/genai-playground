#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""version_select:保守择优判定表逐行、版本审计完整性、从版本渲染 bilingual。"""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

try:
    from . import source_identity as si
    from .artifact_schemas import validate_artifact
    from .version_select import (
        UnresolvedSelectionError,
        build_document_version,
        recommend_selection,
        render_version,
    )
except ImportError:  # core/ 在 sys.path 上
    import source_identity as si
    from artifact_schemas import validate_artifact
    from version_select import (
        UnresolvedSelectionError,
        build_document_version,
        recommend_selection,
        render_version,
    )


TESTDATA = Path(__file__).resolve().parent / "testdata"
FIXTURES = TESTDATA / "fixtures"
GOLDEN = TESTDATA / "golden"

TRANSLATIONS = {
    "朝の挨拶": "早晨的问候",
    "テスト用の短い文章です。": "用于测试的简短文章。",
    "[テスト, 日常]": "[テスト / 测试, 日常 / 日常]",
    "「おはよう」": "「早上好」",
    "今日はいい天気だ。": "今天天气真好。",
    "散歩": "散步",
    "フィクスチャ用のサンプル。": "fixture 用的样本。",
    "公園を歩いた。": "在公园里散步了。",
    "犬がいた。": "有一只狗。",
}


def _cand_id(text: str) -> str:
    return "cand_" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _eval_id(tag: str) -> str:
    return "eval_" + hashlib.sha256(tag.encode("utf-8")).hexdigest()[:16]


def _evaluation(tag: str, verdict: str, error_codes=(), name="rule-qa", version="1") -> dict:
    findings = [{"code": c, "severity": "error", "message": c} for c in error_codes]
    return {
        "schema_version": 1,
        "evaluation_id": _eval_id(tag),
        "candidate_id": _cand_id(tag),
        "evaluator": {"type": "rule", "name": name, "version": version},
        "verdict": verdict,
        "findings": findings,
        "scores": {},
        "created_at": "2026-06-13T00:00:00Z",
    }


def _candidate(text: str, verdict: str, error_codes=(), **kw) -> dict:
    ev = _evaluation(text, verdict, error_codes, **kw)
    ev["candidate_id"] = _cand_id(text)
    return {"candidate_id": _cand_id(text), "text": text, "evaluations": [ev]}


def _seg(incumbent=None, challengers=()):
    return {
        "segment_id": "rev_" + "a" * 8 + ":000001:dead",
        "incumbent": incumbent,
        "challengers": list(challengers),
    }


def _only(segments):
    return recommend_selection(segments)[0]


class DecisionTableTest(unittest.TestCase):
    def test_incumbent_fail_single_passing_challenger_selects(self):
        inc = _candidate("旧译", "fail", ["same_as_source"])
        ch = _candidate("新译", "pass")
        rec = _only([_seg(inc, [ch])])
        self.assertEqual("select_challenger", rec["outcome"])
        self.assertEqual("incumbent_failed_single_passing_challenger", rec["reason_code"])
        self.assertEqual(_cand_id("新译"), rec["selected_candidate_id"])
        self.assertEqual(_cand_id("旧译"), rec["incumbent_candidate_id"])

    def test_incumbent_fail_multiple_passing_challengers_review(self):
        inc = _candidate("旧译", "fail", ["same_as_source"])
        rec = _only([_seg(inc, [_candidate("甲", "pass"), _candidate("乙", "pass")])])
        self.assertEqual("review_required", rec["outcome"])
        self.assertEqual("incumbent_failed_multiple_passing_challengers", rec["reason_code"])
        self.assertEqual(_cand_id("旧译"), rec["selected_candidate_id"])  # 保留 fail 的 incumbent

    def test_incumbent_pass_challenger_fail_keeps_incumbent(self):
        inc = _candidate("当前译", "pass")
        rec = _only([_seg(inc, [_candidate("更差", "fail", ["kana_residue"])])])
        self.assertEqual("keep_incumbent", rec["outcome"])
        self.assertEqual("incumbent_passes_challenger_not_better", rec["reason_code"])
        self.assertEqual(_cand_id("当前译"), rec["selected_candidate_id"])

    def test_both_pass_distinct_text_review(self):
        inc = _candidate("当前译", "pass")
        rec = _only([_seg(inc, [_candidate("另一译", "pass")])])
        self.assertEqual("review_required", rec["outcome"])
        self.assertEqual("multiple_passing_distinct_texts", rec["reason_code"])
        self.assertEqual(_cand_id("当前译"), rec["selected_candidate_id"])

    def test_both_fail_review_keeps_incumbent(self):
        inc = _candidate("旧译", "fail", ["same_as_source"])
        rec = _only([_seg(inc, [_candidate("也坏", "fail", ["kana_residue"])])])
        self.assertEqual("review_required", rec["outcome"])
        self.assertEqual("unresolved_failing_candidates", rec["reason_code"])
        self.assertEqual(_cand_id("旧译"), rec["selected_candidate_id"])

    def test_no_incumbent_single_pass_initial_select(self):
        rec = _only([_seg(None, [_candidate("初译", "pass")])])
        self.assertEqual("select_challenger", rec["outcome"])
        self.assertEqual("initial_single_passing_candidate", rec["reason_code"])
        self.assertEqual(_cand_id("初译"), rec["selected_candidate_id"])
        self.assertIsNone(rec["incumbent_candidate_id"])

    def test_no_incumbent_multiple_pass_review_no_selection(self):
        rec = _only([_seg(None, [_candidate("甲", "pass"), _candidate("乙", "pass")])])
        self.assertEqual("review_required", rec["outcome"])
        self.assertEqual("multiple_passing_distinct_texts", rec["reason_code"])
        self.assertIsNone(rec["selected_candidate_id"])

    def test_no_incumbent_no_pass_no_renderable(self):
        rec = _only([_seg(None, [_candidate("坏译", "fail", ["same_as_source"])])])
        self.assertEqual("review_required", rec["outcome"])
        self.assertEqual("no_passing_candidate", rec["reason_code"])
        self.assertIsNone(rec["selected_candidate_id"])

    def test_incumbent_pass_no_challenger_keeps(self):
        rec = _only([_seg(_candidate("当前译", "pass"), [])])
        self.assertEqual("keep_incumbent", rec["outcome"])
        self.assertEqual("incumbent_passes_no_challenger", rec["reason_code"])

    def test_incumbent_fail_no_challenger_review(self):
        rec = _only([_seg(_candidate("旧译", "fail", ["same_as_source"]), [])])
        self.assertEqual("review_required", rec["outcome"])
        self.assertEqual("incumbent_failing_no_challenger", rec["reason_code"])


class ComparabilityGateTest(unittest.TestCase):
    def test_missing_rule_evaluation_is_incomparable(self):
        ch = _candidate("新译", "pass")
        ch["evaluations"] = []  # 无 rule evaluation
        rec = _only([_seg(_candidate("旧译", "fail", ["x"]), [ch])])
        self.assertEqual("review_required", rec["outcome"])
        self.assertEqual("incomparable_evaluations", rec["reason_code"])

    def test_evaluator_version_mismatch_is_incomparable(self):
        inc = _candidate("旧译", "fail", ["x"], version="1")
        ch = _candidate("新译", "pass", version="2")
        rec = _only([_seg(inc, [ch])])
        self.assertEqual("review_required", rec["outcome"])
        self.assertEqual("evaluator_mismatch", rec["reason_code"])

    def test_verdict_blocking_inconsistent_is_review(self):
        # 声明 pass 但带 error finding → 不自洽
        bad = _candidate("可疑", "pass", ["same_as_source"])
        rec = _only([_seg(None, [bad])])
        self.assertEqual("review_required", rec["outcome"])
        self.assertEqual("verdict_blocking_inconsistent", rec["reason_code"])

    def test_decision_is_order_independent(self):
        inc = _candidate("旧译", "fail", ["same_as_source"])
        a, b = _candidate("甲", "pass"), _candidate("乙", "pass")
        first = _only([_seg(inc, [a, b])])
        second = _only([_seg(inc, [b, a])])
        self.assertEqual(first, second)


def _revision():
    return si.build_document_revision("pixiv", FIXTURES / "pixiv" / "700001" / "700001.txt")


def _initial_recommendations(revision):
    """每 segment 一个 pass 候选(译文取自 TRANSLATIONS),无 incumbent → 初始择优。"""
    segments, candidates_by_id = [], {}
    for seg in revision["segments"]:
        text = TRANSLATIONS[seg["source_text"]]
        cand = _candidate(text, "pass")
        cand["evaluations"][0]["candidate_id"] = cand["candidate_id"]
        candidates_by_id[cand["candidate_id"]] = cand
        segments.append({"segment_id": seg["segment_id"], "incumbent": None, "challengers": [cand]})
    return recommend_selection(segments), candidates_by_id


class BuildAndRenderTest(unittest.TestCase):
    def test_build_version_is_schema_valid_and_consistent(self):
        rev = _revision()
        recs, _ = _initial_recommendations(rev)
        version = build_document_version(rev, recs, "workflow", "2026-06-13T00:00:00Z")
        self.assertEqual([], validate_artifact("document-version", version))
        self.assertEqual(2, version["schema_version"])
        self.assertEqual("draft", version["status"])
        # selections 与 selection_decisions key 完全一致
        self.assertEqual(set(version["selections"]), set(version["selection_decisions"]))
        # 覆盖 revision 全部 segment
        self.assertEqual({s["segment_id"] for s in rev["segments"]}, set(version["selections"]))

    def test_build_version_id_is_deterministic(self):
        rev = _revision()
        recs, _ = _initial_recommendations(rev)
        v1 = build_document_version(rev, recs, "workflow", "2026-06-13T00:00:00Z")
        v2 = build_document_version(rev, recs, "workflow", "2026-06-13T00:00:00Z")
        self.assertEqual(v1["version_id"], v2["version_id"])

    def test_unresolved_segment_refuses_build(self):
        rev = _revision()
        recs, _ = _initial_recommendations(rev)
        recs[0]["selected_candidate_id"] = None  # 制造未决
        with self.assertRaises(UnresolvedSelectionError):
            build_document_version(rev, recs, "workflow", "2026-06-13T00:00:00Z")

    def test_missing_segment_refuses_build(self):
        rev = _revision()
        recs, _ = _initial_recommendations(rev)
        with self.assertRaises(UnresolvedSelectionError):
            build_document_version(rev, recs[:-1], "workflow", "2026-06-13T00:00:00Z")

    def test_render_version_matches_golden(self):
        rev = _revision()
        recs, candidates_by_id = _initial_recommendations(rev)
        version = build_document_version(rev, recs, "workflow", "2026-06-13T00:00:00Z")
        path = FIXTURES / "pixiv" / "700001" / "700001.txt"
        out = render_version(rev, version, candidates_by_id, path.read_text(encoding="utf-8"))
        golden = (GOLDEN / "pixiv-700001.render.bilingual.txt").read_text(encoding="utf-8")
        self.assertEqual(golden, out)

    def test_render_rejects_revision_mismatch(self):
        rev = _revision()
        recs, candidates_by_id = _initial_recommendations(rev)
        version = build_document_version(rev, recs, "workflow", "2026-06-13T00:00:00Z")
        version["revision_id"] = "rev_" + "f" * 16
        with self.assertRaises(ValueError):
            render_version(rev, version, candidates_by_id, "irrelevant")


if __name__ == "__main__":
    unittest.main()
