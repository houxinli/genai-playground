#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entity 自动抽取器(#83 P1b-2b):启发式命中/降噪/去重 + 端到端 extract→link→review。"""

from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

try:
    from . import entity_extract as ee
    from .entity_review import ReviewQueue
    from .entity_store import EntityStore, build_entity
except ImportError:  # core/ 在 sys.path 上
    import entity_extract as ee
    from entity_review import ReviewQueue
    from entity_store import EntityStore, build_entity


DOC = "pixiv:50235390:12430834"
CTX = {"provider": "pixiv", "creator_id": "50235390", "document_id": DOC}
CREATOR = {"level": "creator", "key": "pixiv:50235390"}


def _seg(sid, kind, text):
    return {"segment_id": sid, "kind": kind, "source_text": text}


def _revision(segments):
    return {"document_id": DOC, "revision_id": "rev_x", "segments": segments}


class HeuristicTest(unittest.TestCase):
    def test_honorific_anchor_high_confidence(self):
        counts = Counter()
        out = {h["mention"]: h["confidence"] for h in ee.extract_from_text("田中さんとユキちゃんが来た。", counts)}
        self.assertEqual(0.9, out["田中"])
        self.assertEqual(0.9, out["ユキ"])

    def test_common_word_with_honorific_excluded(self):
        # おじさん 的名字部分是平假名 → 不当人名
        self.assertEqual([], ee.extract_from_text("おじさんが居た。", Counter()))

    def test_recurring_katakana_medium_single_dropped(self):
        counts = ee._katakana_counts(["アレクサンドルが来た", "アレクサンドルは笑う", "ドキドキした"])
        rec = {h["mention"]: h["confidence"] for h in ee.extract_from_text("アレクサンドルが来た", counts)}
        self.assertEqual(0.6, rec["アレクサンドル"])           # 复现 ≥2 → 中置信
        self.assertEqual([], ee.extract_from_text("ドキドキした", counts))  # 单次 → 丢弃

    def test_stopword_filtered(self):
        counts = Counter({"セックス": 5})
        self.assertEqual([], ee.extract_from_text("セックスした", counts))


class ExtractMentionsTest(unittest.TestCase):
    def test_dedup_and_skip_tags(self):
        rev = _revision([
            _seg("s1", "metadata.title", "ユキちゃんの一日"),
            _seg("s2", "body", "ユキは笑った。アレクサンドルが来た。アレクサンドルを見た。"),
            _seg("s3", "metadata.tags", "[アレクサンドル, R-18]"),  # tags 不抽
        ])
        props = ee.extract_mentions(rev)
        mentions = {p["mention"]: p for p in props}
        self.assertIn("ユキ", mentions)                       # 称谓命中(标题)
        self.assertEqual(0.9, mentions["ユキ"]["confidence"])
        self.assertIn("アレクサンドル", mentions)             # body 复现
        self.assertEqual("s2", mentions["アレクサンドル"]["segment_id"])  # 首次出现段
        for p in props:                                       # proposal 形态合法
            self.assertEqual(DOC, p["document_id"])
            self.assertTrue(0 <= p["confidence"] <= 1)
            self.assertIn("context", p)


class ExtractAndLinkTest(unittest.TestCase):
    def test_new_mention_enters_review(self):
        with tempfile.TemporaryDirectory() as t:
            estore = EntityStore(Path(t) / "e"); queue = ReviewQueue(Path(t) / "q")
            rev = _revision([_seg("rev_abcd1234:000001:dead", "body", "アレクサンドルとアレクサンドル。")])
            reviews = ee.extract_and_link(rev, CTX, estore, queue)
            self.assertTrue(reviews)
            self.assertEqual("unmatched_needs_target", reviews[0]["reason"])  # 无译名 → 待补

    def test_existing_entity_links_via_reading(self):
        with tempfile.TemporaryDirectory() as t:
            estore = EntityStore(Path(t) / "e"); queue = ReviewQueue(Path(t) / "q")
            estore.put(build_entity(CREATOR, "ユキ", "小雪", readings=["ゆき"], status="approved", authority="manual"))
            rev = _revision([_seg("rev_abcd1234:000001:dead", "body", "ユキちゃんが来た。")])
            reviews = ee.extract_and_link(rev, CTX, estore, queue)
            # 抽出 ユキ(精确命中既有实体)→ 干净高置信 → 不排队(命中即一致)
            self.assertEqual([], reviews)


if __name__ == "__main__":
    unittest.main()
