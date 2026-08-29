#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载器写出的 front matter 必须是合法 YAML。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.batch_download_v1 import build_yaml_frontmatter  # noqa: E402


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
