#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""renderer shadow path:从 revision + 逐 segment 译文渲染 bilingual,与 golden 逐字节一致。"""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    from . import source_identity as si
    from .renderer import render_bilingual, render_zh
except ImportError:  # core/ 在 sys.path 上
    import source_identity as si
    from renderer import render_bilingual, render_zh


TESTDATA = Path(__file__).resolve().parent / "testdata"
FIXTURES = TESTDATA / "fixtures"
GOLDEN = TESTDATA / "golden"

TRANSLATIONS = {
    "朝の挨拶": "早晨的问候",
    "テスト用の短い文章です。": "用于测试的简短文章。",
    "[テスト, 日常]": "[テスト / 测试, 日常 / 日常]",
    "[テスト, 散歩]": "[テスト / 测试, 散歩 / 散步]",
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


def _translations(rev):
    return {s["segment_id"]: TRANSLATIONS[s["source_text"]] for s in rev["segments"]}


def _render(name: str) -> str:
    provider, path = CASES[name]
    rev = si.build_document_revision(provider, path)
    return render_bilingual(rev, path.read_text(encoding="utf-8"), _translations(rev))


def _render_zh(name: str) -> str:
    provider, path = CASES[name]
    rev = si.build_document_revision(provider, path)
    return render_zh(rev, path.read_text(encoding="utf-8"), _translations(rev))


class RendererGoldenTest(unittest.TestCase):
    def test_render_matches_golden_byte_for_byte(self):
        for name in CASES:
            golden = (GOLDEN / f"{name}.render.bilingual.txt").read_text(encoding="utf-8")
            self.assertEqual(golden, _render(name), name)

    def test_render_zh_matches_golden_byte_for_byte(self):
        # zh golden 由 extract_chinese 跑 bilingual golden 生成,render_zh 必须逐字节复刻其字段变换
        for name in CASES:
            golden = (GOLDEN / f"{name}.render.zh.txt").read_text(encoding="utf-8")
            self.assertEqual(golden, _render_zh(name), name)

    def test_render_zh_drops_non_whitelisted_keys(self):
        # author/creator/source_url/lang/x_restrict/series.id 等不得出现在 zh 产物
        out = _render_zh("pixiv-700001")
        for noise in ("author:", "source_url:", "lang:", "x_restrict:", "  id:", "  order:"):
            self.assertNotIn(noise, out)
        self.assertTrue(out.startswith("---\nID: 700001\n"))  # 只开 --- 不闭合 + ID 来自 novel_id

    def test_render_zh_fanbox_uses_excerpt_and_published_keys(self):
        out = _render_zh("fanbox-800001")
        self.assertIn("excerpt: fixture 用的样本。", out)
        self.assertIn("published_at: ", out)
        self.assertNotIn("caption:", out)
        self.assertNotIn("creator:", out)

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

    def test_tags_are_paired(self):
        out = _render("pixiv-700001")
        lines = out.splitlines()
        i = lines.index("tags: [テスト, 日常]")
        self.assertEqual("tags: [テスト / 测试, 日常 / 日常]", lines[i + 1])

    def test_source_text_mismatch_raises(self):
        # 传入与 revision 不一致的源文本(正文被改),必须报错而非错配译文
        provider, path = CASES["pixiv-700001"]
        rev = si.build_document_revision(provider, path)
        translations = {s["segment_id"]: TRANSLATIONS[s["source_text"]] for s in rev["segments"]}
        tampered = path.read_text(encoding="utf-8").replace("「おはよう」", "「こんばんは」")
        with self.assertRaises(ValueError):
            render_bilingual(rev, tampered, translations)

    def test_missing_translation_raises(self):
        provider, path = CASES["pixiv-700001"]
        rev = si.build_document_revision(provider, path)
        with self.assertRaises(KeyError):
            render_bilingual(rev, path.read_text(encoding="utf-8"), {})


    def test_furigana_annotates_kanji(self):
        try:
            import pykakasi  # noqa
        except ImportError:
            self.skipTest("pykakasi 未安装")
        try:
            from .renderer import add_furigana
        except ImportError:
            from renderer import add_furigana
        # 只给汉字注音,送假名剥到括号外;纯假名/符号不动
        self.assertEqual("パッケージに映(うつ)るのは", add_furigana("パッケージに映るのは"))
        self.assertEqual("「おはよう」", add_furigana("「おはよう」"))
        self.assertIn("巨乳(きょにゅう)", add_furigana("巨乳の彼女"))


if __name__ == "__main__":
    unittest.main()
