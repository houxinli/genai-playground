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
