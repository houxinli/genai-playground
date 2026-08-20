#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest

try:
    from . import document_qa
except ImportError:
    import document_qa


def _segments(texts):
    return [{"segment_id": f"s{i}", "source_text": text} for i, text in enumerate(texts)]


class DocumentQATest(unittest.TestCase):
    def test_multiline_and_context_markers_are_document_errors(self):
        segs = _segments(["源0", "源1", "源2"])
        translations = {
            "s0": "译文0\n\n混入的邻段",
            "s1": "译文1 [tags] 术语",
            "s2": "译文2",
        }
        findings = document_qa.audit_document_translations(segs, translations)
        by_code = {finding["code"]: finding for finding in findings}
        self.assertEqual([0], by_code["multiline_translation"]["indices"])
        self.assertEqual([1], by_code["context_marker_leak"]["indices"])
        self.assertEqual("error", by_code["multiline_translation"]["severity"])

    def test_single_line_translation_shape_is_clean(self):
        self.assertEqual([], document_qa.translation_shape_errors("只有当前段的译文。"))

    def test_block_paste_run_is_error(self):
        segs = _segments(["源0", "源1", "源2", "源3", "新0", "新1", "新2"])
        translations = {f"s{i}": text for i, text in enumerate(["译0", "译1", "译2", "译3", "译1", "译2", "译3"])}
        findings = document_qa.audit_document_translations(segs, translations)
        block = [f for f in findings if f["code"] == "block_paste_run"]
        self.assertEqual(1, len(block))
        self.assertEqual("error", block[0]["severity"])
        self.assertEqual([4, 6], block[0]["source_range"])
        self.assertEqual([1, 3], block[0]["copied_from_range"])

    def test_repeated_source_run_is_not_block_error(self):
        segs = _segments(["同", "同", "同", "同", "同", "同"])
        translations = {f"s{i}": text for i, text in enumerate(["译", "译", "译", "译", "译", "译"])}
        findings = document_qa.audit_document_translations(segs, translations)
        self.assertFalse([f for f in findings if f["code"] == "block_paste_run"])

    def test_single_duplicate_distinct_source_is_warning(self):
        segs = _segments(["今日は何するの？", "今日は何するんだ？"])
        translations = {"s0": "今天做什么？", "s1": "今天做什么？"}
        findings = document_qa.audit_document_translations(segs, translations)
        self.assertEqual(["warning"], [f["severity"] for f in findings])


if __name__ == "__main__":
    unittest.main()


class UndertranslationTest(unittest.TestCase):
    """系统性缩写:每段都翻了、没有假名/照抄/窜入,但整篇被砍掉一半——现有判据全部漏检。"""

    @staticmethod
    def _doc(ratio: float, n: int = 40):
        segs, tr = [], {}
        for i in range(n):
            sid = f"rev:{i:06d}:x"
            src = "友達とLINEしてただけよ、そんなに楽しそうに見えたの？"
            segs.append({"segment_id": sid, "kind": "body", "source_text": src})
            tr[sid] = "译" * max(1, int(len(src) * ratio))
        return segs, tr

    def test_flags_systematic_compression(self):
        segs, tr = self._doc(0.45)
        codes = [f["code"] for f in document_qa.audit_document_translations(segs, tr)]
        self.assertIn("undertranslation", codes)
        self.assertNotIn("same_as_source", codes)   # 旧判据确实抓不到

    def test_normal_ratio_is_clean(self):
        segs, tr = self._doc(0.72)
        self.assertEqual([], [f for f in document_qa.audit_document_translations(segs, tr)
                              if f["code"] == "undertranslation"])

    def test_short_document_is_not_judged(self):
        segs, tr = self._doc(0.30, n=5)     # 段数太少,均值没有统计意义
        self.assertIsNone(document_qa.translation_length_ratio(segs, tr))
        self.assertEqual([], [f for f in document_qa.audit_document_translations(segs, tr)
                              if f["code"] == "undertranslation"])

    def test_severity_is_warning_not_blocking(self):
        segs, tr = self._doc(0.30)
        f = [x for x in document_qa.audit_document_translations(segs, tr) if x["code"] == "undertranslation"][0]
        self.assertEqual("warning", f["severity"])   # 质量问题不阻断发布


class OvertranslationTest(unittest.TestCase):
    """判据此前只有下限:实测 9 篇 deepseek 译文 0.99–1.85 一路绿灯,含 29 字→4095 字的重复循环段。"""

    @staticmethod
    def _doc(ratio: float, n: int = 40):
        segs, tr = [], {}
        src = "友達とLINEしてただけよ、そんなに楽しそうに見えたの？"
        for i in range(n):
            sid = f"rev:{i:06d}:x"
            segs.append({"segment_id": sid, "kind": "body", "source_text": src})
            tr[sid] = "译" * max(1, int(len(src) * ratio))
        return segs, tr

    def test_flags_whole_document_inflation(self):
        segs, tr = self._doc(1.5)
        codes = [f["code"] for f in document_qa.audit_document_translations(segs, tr)]
        self.assertIn("overtranslation", codes)

    def test_normal_ratio_is_clean(self):
        segs, tr = self._doc(0.72)
        codes = [f["code"] for f in document_qa.audit_document_translations(segs, tr)]
        self.assertNotIn("overtranslation", codes)
        self.assertNotIn("segment_overlong", codes)

    def test_flags_single_runaway_segment(self):
        # 整篇均值会被正常段稀释,极端段必须单独抓
        segs, tr = self._doc(0.72)
        segs.append({"segment_id": "rev:999999:x", "kind": "body", "source_text": "──ぶびゅッッッ♡♡♡"})
        tr["rev:999999:x"] = "噗" * 4095
        f = [x for x in document_qa.audit_document_translations(segs, tr) if x["code"] == "segment_overlong"]
        self.assertEqual(1, len(f))
        self.assertIn("rev:999999:x", f[0]["segments"])

    def test_short_expansion_is_not_flagged(self):
        # 「はい♡」→「好的呢♡」这类短段正常膨胀不该报
        segs, tr = self._doc(0.72)
        segs.append({"segment_id": "rev:888888:x", "kind": "body", "source_text": "はい♡"})
        tr["rev:888888:x"] = "好的呢♡"
        codes = [f["code"] for f in document_qa.audit_document_translations(segs, tr)]
        self.assertNotIn("segment_overlong", codes)
