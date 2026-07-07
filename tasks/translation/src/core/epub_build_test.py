#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简 EPUB3 生成:结构合规(mimetype 第一且不压缩、显式 TOC、逐章 XHTML、转义)。"""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

try:
    from . import epub_build
except ImportError:
    import epub_build


class EpubBuildTest(unittest.TestCase):
    def _build(self, tmp, chapters):
        out = Path(tmp) / "book.epub"
        epub_build.build_epub(out, "书名", "作者X", chapters)
        return out

    def test_structure_is_valid_epub(self):
        with tempfile.TemporaryDirectory() as t:
            out = self._build(t, [("第1章 甲", "正文一\n\n第二段"), ("第2章 乙", "正文二")])
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
                # 规范:mimetype 必须是第一个 entry 且不压缩
                self.assertEqual("mimetype", names[0])
                self.assertEqual(zipfile.ZIP_STORED, z.getinfo("mimetype").compress_type)
                self.assertEqual(b"application/epub+zip", z.read("mimetype"))
                self.assertIn("META-INF/container.xml", names)
                self.assertIn("OEBPS/content.opf", names)
                self.assertIn("OEBPS/nav.xhtml", names)
                self.assertIn("OEBPS/c1.xhtml", names)
                self.assertIn("OEBPS/c2.xhtml", names)
                # 所有 xml/xhtml 可解析
                for n in names[1:]:
                    ElementTree.fromstring(z.read(n))

    def test_nav_lists_chapter_titles_in_order(self):
        with tempfile.TemporaryDirectory() as t:
            out = self._build(t, [("第1章 甲", "一"), ("第2章 乙", "二")])
            with zipfile.ZipFile(out) as z:
                nav = z.read("OEBPS/nav.xhtml").decode("utf-8")
                self.assertIn("第1章 甲", nav)
                self.assertIn("第2章 乙", nav)
                self.assertLess(nav.index("第1章 甲"), nav.index("第2章 乙"))
                opf = z.read("OEBPS/content.opf").decode("utf-8")
                self.assertLess(opf.index('idref="c1"'), opf.index('idref="c2"'))

    def test_body_html_escaped(self):
        with tempfile.TemporaryDirectory() as t:
            out = self._build(t, [("章<注>", "正文含 <tag> & 符号")])
            with zipfile.ZipFile(out) as z:
                c1 = z.read("OEBPS/c1.xhtml").decode("utf-8")
                self.assertIn("&lt;tag&gt; &amp; 符号", c1)
                self.assertNotIn("<tag>", c1)

    def test_empty_chapters_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                epub_build.build_epub(Path(t) / "x.epub", "书", "者", [])


if __name__ == "__main__":
    unittest.main()
