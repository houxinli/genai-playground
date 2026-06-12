#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path

from tasks.translation.src.scripts.qa_baseline import build_baseline


def _write_source(directory: Path, stem: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stem}.txt").write_text(text, encoding="utf-8")
    (directory / f"{stem}.meta.json").write_text("{}", encoding="utf-8")


class QABaselineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        src = self.data / "pixiv" / "111"
        _write_source(src, "good", "こんにちは\nさようなら")
        _write_source(src, "bad", "こんにちは\nさようなら")
        derived = self.data / "pixiv" / "111_bilingual"
        derived.mkdir()
        # 双语配对:原文行+译文行
        (derived / "good.txt").write_text(
            "こんにちは\n你好\n\nさようなら\n再见\n", encoding="utf-8"
        )
        # 译文残留假名 + 空译文
        (derived / "bad.txt").write_text(
            "こんにちは\nこんにちは你好\n\nさようなら\n\n", encoding="utf-8"
        )
        # 隔离候选与 zh 目录应被跳过
        tmp = self.data / "pixiv" / "111_bilingual_tmp"
        tmp.mkdir()
        (tmp / "good.txt").write_text("x\n", encoding="utf-8")
        zh = self.data / "pixiv" / "111_zh"
        zh.mkdir()
        (zh / "good.txt").write_text("你好\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_baseline_aggregates_issue_counts(self):
        baseline = build_baseline(self.data, ["pixiv"])
        self.assertEqual(1, baseline["totals"]["dirs"])  # tmp 与 zh 被跳过
        entry = baseline["dirs"][0]
        self.assertEqual("111_bilingual", entry["dir"])
        self.assertEqual(2, entry["files"])
        self.assertGreaterEqual(entry["files_with_errors"], 1)
        self.assertTrue(
            any(key.startswith("kana_residue") for key in entry["issue_counts"]),
            entry["issue_counts"],
        )

    def test_packaged_top_level_bilingual_included(self):
        (self.data / "111_bilingual.txt").write_text(
            "こんにちは\n你好\n", encoding="utf-8"
        )
        (self.data / "111_zh.txt").write_text("你好\n", encoding="utf-8")  # zh 不纳入
        baseline = build_baseline(self.data, ["pixiv"])
        packaged = [e for e in baseline["dirs"] if e["collection"] == "(packaged)"]
        self.assertEqual(["111_bilingual.txt"], [e["dir"] for e in packaged])
        self.assertEqual(3, baseline["totals"]["files"])  # 2 目录内 + 1 打包

    def test_clean_dir_reports_zero_errors(self):
        baseline = build_baseline(self.data, ["pixiv"])
        total = baseline["totals"]
        self.assertEqual(2, total["files"])
        self.assertLess(total["files_with_errors"], total["files"])


if __name__ == "__main__":
    unittest.main()
