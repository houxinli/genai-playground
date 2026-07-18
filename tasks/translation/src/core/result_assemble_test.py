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

    def test_v2_src_echo_validates_against_bundle(self):
        bundle = _bundle()
        first = bundle["segments"][0]["source_text"][:8]
        out = ra.parse_translations_tsv(f"0\t{first}\t你好", bundle)
        self.assertEqual({0: "你好"}, out)

    def test_v2_src_echo_mismatch_errors(self):
        with self.assertRaises(ValueError):
            ra.parse_translations_tsv("0\t错源\t你好", _bundle())

    def test_legacy_translation_with_tab_preserved(self):
        # Codex #143 P2:旧二列行译文含 TAB 时不得被误当 v2 截断——
        # 文件级判定:存在纯二列行 → 整份按旧格式,TAB 后全部内容原样保留。
        out = ra.parse_translations_tsv("0\t甲\t乙\n1\t丙")
        self.assertEqual({0: "甲\t乙", 1: "丙"}, out)
        out2 = ra.parse_translations_tsv("0\t甲\t乙\n1\t丙", _bundle())
        self.assertEqual({0: "甲\t乙", 1: "丙"}, out2)

    def test_mixed_v2_like_line_in_legacy_file_errors(self):
        # 看着像 v2 的行(第二列==源文前缀)混进二列文件 → 报错,拒绝静默降级保护
        bundle = _bundle()
        first = bundle["segments"][0]["source_text"][:8]
        with self.assertRaises(ValueError):
            ra.parse_translations_tsv(f"0\t{first}\t你好\n1\t纯旧行", bundle)

    def test_v2_empty_translation_kept(self):
        bundle = _bundle()
        e0 = bundle["segments"][0]["source_text"][:8]
        e1 = bundle["segments"][1]["source_text"][:8]
        out = ra.parse_translations_tsv(f"0\t{e0}\t\n1\t{e1}\t译", bundle)
        self.assertEqual({0: "", 1: "译"}, out)


class AssembleTest(unittest.TestCase):
    def test_default_completed_at_is_deterministic(self):
        bundle = _bundle()
        translations = {i: f"译文{i}" for i in range(len(bundle["segments"]))}
        first = ra.assemble_result(bundle, translations, producer_name="composer-2.5")
        second = ra.assemble_result(bundle, translations, producer_name="composer-2.5")
        self.assertEqual(first, second)
        self.assertEqual(ra.DETERMINISTIC_COMPLETED_AT, first["completed_at"])

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
