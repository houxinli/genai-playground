#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""紧凑译文组装(#134):tsv 解析 + 从 bundle 回填身份产 schema 合法 result。"""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    from . import result_assemble as ra, source_identity as si, task_export as te
    from .artifact_schemas import check_result_against_task, validate_artifact
except ImportError:  # core/ 在 sys.path 上
    import result_assemble as ra
    import source_identity as si
    import task_export as te
    from artifact_schemas import check_result_against_task, validate_artifact


SRC = Path(__file__).resolve().parent / "testdata" / "fixtures" / "pixiv" / "700001" / "700001.txt"


def _bundle():
    rev = si.build_document_revision("pixiv", SRC)
    return te.export_job(rev, [s["segment_id"] for s in rev["segments"]])


class ParseTsvTest(unittest.TestCase):
    def test_parses_index_text_and_skips_blanks(self):
        out = ra.parse_translations_tsv("0\t你好\n\n1\t世界\n2\t")
        self.assertEqual({0: "你好", 1: "世界", 2: ""}, out)  # 空译文保留

    def test_missing_tab_errors(self):
        with self.assertRaises(ValueError):
            ra.parse_translations_tsv("0 没有制表符")

    def test_non_int_index_errors(self):
        with self.assertRaises(ValueError):
            ra.parse_translations_tsv("x\t译文")

    def test_duplicate_index_errors(self):
        with self.assertRaises(ValueError):
            ra.parse_translations_tsv("0\t甲\n0\t乙")


class AssembleTest(unittest.TestCase):
    def test_assembles_schema_valid_result_and_backfills(self):
        bundle = _bundle()
        n = len(bundle["segments"])
        translations = {i: f"译文{i}" for i in range(n)}
        result = ra.assemble_result(bundle, translations, producer_name="claude-code",
                                    completed_at="2026-06-13T00:00:00Z")
        self.assertEqual([], validate_artifact("result", result))
        # source_hash 由 harness 从 bundle 回填,agent 不碰
        for i, c in enumerate(result["candidates"]):
            sid = bundle["segments"][i]["segment_id"]
            self.assertEqual(bundle["task"]["source_hashes"][sid], c["source_hash"])
        # task_digest 原样 → 不触发 stale 防护
        self.assertEqual([], check_result_against_task(bundle["task"], result))

    def test_missing_segment_rejected(self):
        bundle = _bundle()
        with self.assertRaises(ValueError):
            ra.assemble_result(bundle, {0: "只翻了第一段"})

    def test_out_of_range_index_rejected(self):
        bundle = _bundle()
        full = {i: "x" for i in range(len(bundle["segments"]))}
        full[999] = "越界"
        with self.assertRaises(ValueError):
            ra.assemble_result(bundle, full)


if __name__ == "__main__":
    unittest.main()
