#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则影响分析(#83 §8.3):已发布版本里找用了旧译名的 segment;只读、不改 version。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import rule_impact, translate_user as tu
except ImportError:  # core/ 在 sys.path 上
    import rule_impact
    import translate_user as tu


TESTDATA = Path(__file__).resolve().parent / "testdata"
SRC = TESTDATA / "fixtures" / "pixiv" / "700001" / "700001.txt"
BILINGUAL = TESTDATA / "golden" / "pixiv-700001.render.bilingual.txt"
TR = {
    "朝の挨拶": "早晨的问候", "テスト用の短い文章です。": "用于测试的简短文章。",
    "[テスト, 日常]": "[テスト / 测试, 日常 / 日常]", "「おはよう」": "「早上好」",
    "今日はいい天気だ。": "今天天气真好。",
}


def _publish_fixture(tmp: Path) -> Path:
    """走紧凑路径把 fixture 发布进 store,返回 store_root。"""
    import json
    src_dir = tmp / "53230930"; src_dir.mkdir()
    shutil.copy(SRC, src_dir / "700001.txt")
    bil_dir = tmp / "bil"; bil_dir.mkdir(); shutil.copy(BILINGUAL, bil_dir / "700001.txt")
    store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
    results.mkdir()
    prep = tu.prepare_user("pixiv", src_dir, store, jobs, bilingual_dir=bil_dir)
    j = prep["jobs"][0]; sid = j["source_id"]
    bundle = json.loads(Path(j["job"]).read_text(encoding="utf-8"))
    lines = [f"{i}\t{TR[seg['source_text']]}" for i, seg in enumerate(bundle["segments"])]
    (results / f"{sid}.zh.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs, bilingual_dir=bil_dir)
    return store


class RuleImpactTest(unittest.TestCase):
    def test_finds_published_segment_with_stale_text(self):
        with tempfile.TemporaryDirectory() as t:
            store = _publish_fixture(Path(t))
            hit = rule_impact.find_affected(store, "早上好")  # 正文「おはよう」→「早上好」
            self.assertEqual(1, len(hit))
            self.assertIn("早上好", hit[0]["snippet"])
            self.assertTrue(hit[0]["document_id"].startswith("pixiv:"))

    def test_absent_text_returns_empty(self):
        with tempfile.TemporaryDirectory() as t:
            store = _publish_fixture(Path(t))
            self.assertEqual([], rule_impact.find_affected(store, "根本不存在的旧译名"))

    def test_scope_filter(self):
        with tempfile.TemporaryDirectory() as t:
            store = _publish_fixture(Path(t))
            self.assertTrue(rule_impact.find_affected(store, "早上好", scope="pixiv:700000"))
            self.assertEqual([], rule_impact.find_affected(store, "早上好", scope="pixiv:999999"))

    def test_empty_stale_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            store = _publish_fixture(Path(t))
            with self.assertRaises(ValueError):
                rule_impact.find_affected(store, "")


if __name__ == "__main__":
    unittest.main()
