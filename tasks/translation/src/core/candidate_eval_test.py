#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""candidate QA 评估:好/坏 candidate 的 verdict 与 findings。"""

from __future__ import annotations

import unittest

try:
    from . import candidate_eval as ce
    from .artifact_schemas import candidate_id_v3, normalize_text, validate_artifact
    from .source_identity import _source_hash
except ImportError:  # core/ 在 sys.path 上
    import candidate_eval as ce
    from artifact_schemas import candidate_id_v3, normalize_text, validate_artifact
    from source_identity import _source_hash


SOURCE = "彼女は振り返った。"
_H = _source_hash(SOURCE)
_REV = "rev_" + "a" * 16
_SEG = f"{_REV}:000000:" + _H[:8]


def _candidate(text):
    """构建内容寻址自洽的 v3 candidate(text 归一化、id 由内容重算),满足 validate_candidate_identity。"""
    normalized = normalize_text(text)
    return {
        "schema_version": 3,
        "candidate_id": candidate_id_v3(_REV, _SEG, _H, normalized),
        "document_id": "pixiv:1:2",
        "revision_id": _REV,
        "segment_id": _SEG,
        "source_hash": _H,
        "normalization_version": 1,
        "text": normalized,
    }


def _candidate_for(text, source):
    """绑定到任意 source 的自洽 candidate(用于非默认源的用例)。"""
    h = _source_hash(source)
    rev = "rev_" + "b" * 16
    seg = f"{rev}:000000:" + h[:8]
    normalized = normalize_text(text)
    return {
        "schema_version": 3,
        "candidate_id": candidate_id_v3(rev, seg, h, normalized),
        "document_id": "pixiv:1:2",
        "revision_id": rev,
        "segment_id": seg,
        "source_hash": h,
        "normalization_version": 1,
        "text": normalized,
    }


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

    def test_findings_codes_match_shared_hard_rule_hits(self):
        # R1:candidate_eval 的 finding code 必须与共享 hard_rule_hits 完全一致(单一真相源)
        try:
            from .qa_gate import hard_rule_hits
        except ImportError:
            from qa_gate import hard_rule_hits
        cases = [("彼女は振り返った。", "她转过身来。"), ("今日", "今日"),
                 ("＊　＊　＊", "＊　＊　＊"), ("ねえ", "ねえ"), ("x", "  ")]
        for src, txt in cases:
            shared = [h["code"] for h in hard_rule_hits(src, txt)]
            mine = [f["code"] for f in ce._findings(src, txt)]
            self.assertEqual(shared, mine, (src, txt))

    def test_nontranslatable_separator_same_as_source_exempt(self):
        # #124:纯符号分隔符段译==原是正确的,不应判 same_as_source
        for sep in ("＊　＊　＊", "* * *", "――――", "..."):
            cand = _candidate_for(sep, sep)
            ev = ce.evaluate_candidate(cand, sep)
            self.assertEqual("pass", ev["verdict"], f"{sep!r} 应 pass: {ev['findings']}")
            self.assertNotIn("same_as_source", {f["code"] for f in ev["findings"]})

    def test_translatable_same_as_source_still_fails(self):
        # 回归:源含汉字/假名时,译==原仍判 same_as_source
        src = "今日"
        ev = ce.evaluate_candidate(_candidate_for(src, src), src)
        self.assertEqual("fail", ev["verdict"])
        self.assertIn("same_as_source", {f["code"] for f in ev["findings"]})

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


    def test_source_hash_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            ce.evaluate_candidate(_candidate("她转过身来。"), "完全不同的原文")

    def test_created_at_in_identity(self):
        a = ce.evaluate_candidate(_candidate("她转过身来。"), SOURCE, created_at="2026-01-01T00:00:00Z")
        b = ce.evaluate_candidate(_candidate("她转过身来。"), SOURCE, created_at="2026-02-02T00:00:00Z")
        self.assertNotEqual(a["evaluation_id"], b["evaluation_id"])  # created_at 不同 -> id 不同


if __name__ == "__main__":
    unittest.main()
