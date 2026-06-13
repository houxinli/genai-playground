#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""renderer shadow path:从 revision + 逐 segment 译文渲染 bilingual,与 golden 逐字节一致。"""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    from . import source_identity as si
    from .renderer import render_bilingual
except ImportError:  # core/ 在 sys.path 上
    import source_identity as si
    from renderer import render_bilingual


TESTDATA = Path(__file__).resolve().parent / "testdata"
FIXTURES = TESTDATA / "fixtures"
GOLDEN = TESTDATA / "golden"

TRANSLATIONS = {
    "朝の挨拶": "早晨的问候",
    "テスト用の短い文章です。": "用于测试的简短文章。",
    "「おはよう」": "「早上好」",
    "今日はいい天気だ。": "今天天气真好。",
    "散歩": "散步",
    "フィクスチャ用のサンプル。": "fixture 用的样本。",
    "公園を歩いた。": "在公园里散步了。",
    "犬がいた。": "有一只狗。",
}

CASES = {
    "pixiv-700001": ("pixiv", FIXTURES / "pixiv" / "700001" / "700001.txt"),
    "fanbox-800001": ("fanbox", FIXTURES / "fanbox" / "800001" / "800001.txt"),
}


def _render(name: str) -> str:
    provider, path = CASES[name]
    rev = si.build_document_revision(provider, path)
    translations = {s["segment_id"]: TRANSLATIONS[s["source_text"]] for s in rev["segments"]}
    return render_bilingual(rev, path.read_text(encoding="utf-8"), translations)


class RendererGoldenTest(unittest.TestCase):
    def test_render_matches_golden_byte_for_byte(self):
        for name in CASES:
            golden = (GOLDEN / f"{name}.render.bilingual.txt").read_text(encoding="utf-8")
            self.assertEqual(golden, _render(name), name)

    def test_metadata_keys_are_paired_after_source(self):
        # pixiv 配 caption,fanbox 配 excerpt;译文行紧跟在源键行之后
        out = _render("fanbox-800001")
        lines = out.splitlines()
        i = lines.index("excerpt: フィクスチャ用のサンプル。")
        self.assertEqual("excerpt: fixture 用的样本。", lines[i + 1])
        # 非可翻译键(creator/tags)不被插入译文行
        self.assertNotIn("creator: ", out)

    def test_body_blank_lines_preserved(self):
        out = _render("pixiv-700001")
        lines = out.splitlines()
        # 源正文两段之间的空行保留,且每个非空源行后紧跟译文
        self.assertIn("「おはよう」", lines)
        self.assertEqual("「早上好」", lines[lines.index("「おはよう」") + 1])
        self.assertIn("", lines)  # 段间空行

    def test_missing_translation_raises(self):
        provider, path = CASES["pixiv-700001"]
        rev = si.build_document_revision(provider, path)
        with self.assertRaises(KeyError):
            render_bilingual(rev, path.read_text(encoding="utf-8"), {})


if __name__ == "__main__":
    unittest.main()
