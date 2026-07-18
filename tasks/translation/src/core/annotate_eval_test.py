#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""annotate_eval:注解候选的骨架不变量(剥括号后必须逐字等于源文)。"""

from __future__ import annotations

import unittest

try:
    from . import annotate_eval as ae
except ImportError:
    import annotate_eval as ae


class StripAnnotationsTest(unittest.TestCase):
    def test_strips_annotation_parens(self):
        self.assertEqual("映るのは、姿だ", ae.strip_annotations("映(うつ・映照)るのは、姿(すがた)だ"))

    def test_halfwidth_parens_also_stripped(self):
        self.assertEqual("映る", ae.strip_annotations("映(うつ)る"))

    def test_nested_parens(self):
        self.assertEqual("AB", ae.strip_annotations("A(x(y)z)B"))

    def test_unbalanced_returns_none(self):
        self.assertIsNone(ae.strip_annotations("映(うつる"))
        self.assertIsNone(ae.strip_annotations("映)うつ(る"))


class FindingsTest(unittest.TestCase):
    def test_valid_annotation_passes(self):
        self.assertEqual([], ae._findings("映るのは、姿だ", "映(うつ・映照)るのは、姿(すがた・身姿)だ"))

    def test_unannotated_passthrough_passes(self):
        self.assertEqual([], ae._findings("こんにちは", "こんにちは"))

    def test_source_with_own_parens_passes(self):
        # 源文自带括号:注解行原样保留源括号内容,两边同剥后一致。
        src = "彼は(小声で)言った"
        annotated = "彼は(小声で)言(い)った"
        self.assertEqual([], ae._findings(src, annotated))

    def test_altered_source_char_fails(self):
        codes = [f["code"] for f in ae._findings("映るのは", "映が(うつ)")]
        self.assertIn("skeleton_mismatch", codes)

    def test_deleted_source_char_fails(self):
        codes = [f["code"] for f in ae._findings("映るのは", "映る(うつ)")]
        self.assertIn("skeleton_mismatch", codes)

    def test_unbalanced_fails(self):
        codes = [f["code"] for f in ae._findings("映る", "映(うつる")]
        self.assertIn("unbalanced_parens", codes)

    def test_empty_fails(self):
        codes = [f["code"] for f in ae._findings("映る", "")]
        self.assertIn("empty_annotation_line", codes)

    def test_tab_or_newline_fails(self):
        codes = [f["code"] for f in ae._findings("映る", "映る\t注")]
        self.assertIn("multiline_annotation", codes)


if __name__ == "__main__":
    unittest.main()
