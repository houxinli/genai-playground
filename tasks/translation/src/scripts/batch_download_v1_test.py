#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载器写出的 front matter 必须是合法 YAML。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.batch_download_v1 import build_yaml_frontmatter, existing_source_with_header  # noqa: E402


def _parse(meta):
    fm = build_yaml_frontmatter(meta)
    body = fm.strip()
    assert body.startswith("---")
    return yaml.safe_load(body[3:].split("\n---", 1)[0])


BASE = {"novel_id": 1, "title": "标题", "caption": "说明",
        "user": {"id": 9, "name": "作者", "account": "acc"},
        "series": {}, "tags": ["R-18"], "create_date": "d1", "update_date": "d2", "url": "u"}


class FrontMatterEscapeTest(unittest.TestCase):
    def test_colon_space_in_caption_is_escaped(self):
        # 实测 pixiv 18137868:caption 里的 ` : ` 让 YAML 当成嵌套映射,整块解析返回 None,
        # 下游报"缺少 front matter",该篇从下载起就进不了流水线且一直没人发现。
        m = {**BASE, "caption": "ズリ本～合同本～ サークル名 : Pillow talk"}
        self.assertEqual("ズリ本～合同本～ サークル名 : Pillow talk", _parse(m)["caption"])

    def test_other_yaml_indicators(self):
        for risky in ("- 开头像列表", "#号开头", "结尾冒号:", "  前导空白", '含"引号"和\\反斜杠',
                      "@符号开头", "{花括号}", "[方括号]"):
            with self.subTest(risky=risky):
                self.assertEqual(risky, _parse({**BASE, "title": risky})["title"])

    def test_plain_text_stays_unquoted(self):
        fm = build_yaml_frontmatter({**BASE, "title": "普通的标题"})
        self.assertIn("title: 普通的标题", fm)      # 不必要的引号会污染既有文件的 digest

    def test_newlines_are_flattened(self):
        self.assertEqual("第一行 第二行", _parse({**BASE, "caption": "第一行\n第二行"})["caption"])


class ExistingSourceTest(unittest.TestCase):
    """跳过检查必须在抓取前做:已有作品不该再花 API 请求,否则整作者重跑必然限流。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_and_series_filenames_are_recognised(self):
        (self.dir / "111.txt").write_text("---\nnovel_id: 111\n---\n正文", encoding="utf-8")
        (self.dir / "9_002_222.txt").write_text("---\nnovel_id: 222\n---\n正文", encoding="utf-8")
        self.assertEqual(self.dir / "111.txt", existing_source_with_header(self.dir, 111))
        self.assertEqual(self.dir / "9_002_222.txt", existing_source_with_header(self.dir, 222))

    def test_missing_or_headerless_file_is_not_a_hit(self):
        (self.dir / "333.txt").write_text("没有 front matter", encoding="utf-8")
        self.assertIsNone(existing_source_with_header(self.dir, 333))
        self.assertIsNone(existing_source_with_header(self.dir, 444))

    def test_id_suffix_does_not_match_longer_ids(self):
        (self.dir / "9_001_1111.txt").write_text("---\nx: 1\n---\n", encoding="utf-8")
        self.assertIsNone(existing_source_with_header(self.dir, 111))
