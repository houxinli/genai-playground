#!/usr/bin/env python3
"""Tests for the hard-rule translation QA gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from .qa_gate import TranslationQAGate, infer_source_for_output
except ImportError:  # unittest discover may import this test as top-level core.qa_gate_test.
    from qa_gate import TranslationQAGate, infer_source_for_output


class TranslationQAGateTest(unittest.TestCase):
    def test_passes_clean_bilingual_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "series" / "1001.txt"
            output = base / "series_bilingual" / "1001.txt"
            source.parent.mkdir()
            output.parent.mkdir()
            source.write_text("---\ntitle: タイトル\n---\nこんにちは\n", encoding="utf-8")
            output.write_text("---\ntitle: タイトル\ntitle: 标题\n---\nこんにちは\n你好。\n", encoding="utf-8")

            report = TranslationQAGate().run(output, source)

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.summary["errors"], 0)

    def test_detects_missing_pair_in_middle(self) -> None:
        # 源行 A,B,C;输出只有 A、C 的配对 → B 必须报 missing_pair error
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "src.txt"
            output = base / "out.txt"
            source.write_text("---\ntitle: t\n---\n行A\n行B\n行C\n", encoding="utf-8")
            output.write_text("---\ntitle: t\ntitle: 题\n---\n行A\n译A\n\n行C\n译C\n", encoding="utf-8")

            report = TranslationQAGate().run(output, source)

            missing = [i for i in report.issues if i.code == "missing_pair"]
            self.assertEqual(1, len(missing))
            self.assertEqual("error", missing[0].severity)
            self.assertEqual("行B", missing[0].detail["source"])
            self.assertEqual(5, missing[0].line)  # front matter 3 行 + 正文第 2 行
            self.assertTrue(report.has_errors)

    def test_detects_truncated_tail(self) -> None:
        # 输出在中途截断:尾部未消费的源行必须全部报 missing_pair
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "src.txt"
            output = base / "out.txt"
            source.write_text("行A\n行B\n行C\n行D\n", encoding="utf-8")
            output.write_text("行A\n译A\n", encoding="utf-8")

            report = TranslationQAGate().run(output, source)

            missing = [i.detail["source"] for i in report.issues if i.code == "missing_pair"]
            self.assertEqual(["行B", "行C", "行D"], missing)
            self.assertTrue(report.has_errors)

    def test_detects_kana_placeholders_refusal_and_name_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            rules = base / "rules.txt"
            output = base / "1001.txt"
            rules.write_text("タカオ=高尾|高雄\n", encoding="utf-8")
            output.write_text(
                "---\ntitle: sample\n---\n"
                "タカオ\n高雄说まだ。\n"
                "次\n[翻译未完成]\n"
                "依頼\n抱歉，不能协助。\n",
                encoding="utf-8",
            )

            report = TranslationQAGate(rules).run(output)
            codes = [issue.code for issue in report.issues]

            self.assertEqual(report.status, "fail")
            self.assertIn("kana_residue", codes)
            self.assertIn("failure_marker", codes)
            self.assertIn("refusal_marker", codes)
            self.assertIn("name_alias_drift", codes)
            first_pair_issue = next(issue for issue in report.issues if issue.code == "name_alias_drift")
            self.assertEqual(first_pair_issue.detail["source_body_index"], 0)
            self.assertEqual(first_pair_issue.detail["translation_body_index"], 1)

    def test_writes_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output = base / "1001.txt"
            report_path = base / "report.json"
            output.write_text("原文\n译文\n", encoding="utf-8")

            report = TranslationQAGate().run(output)
            TranslationQAGate.write_report(report, report_path)
            data = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(data["schema_version"], 1)
            self.assertIn("summary", data)

    def test_infers_source_from_bilingual_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "series" / "1001.txt"
            output = base / "series_bilingual" / "1001.txt"
            source.parent.mkdir()
            output.parent.mkdir()
            source.write_text("原文\n", encoding="utf-8")
            output.write_text("原文\n译文\n", encoding="utf-8")

            self.assertEqual(infer_source_for_output(output), source)


if __name__ == "__main__":
    unittest.main()
