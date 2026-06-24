#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entity 模糊/读音匹配(#83 P1b-2b):kana 归一化、读音/模糊命中、优先级与阈值。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import entity_match as em
    from .entity_review import ReviewQueue, import_proposals
    from .entity_store import EntityStore, build_entity
except ImportError:  # core/ 在 sys.path 上
    import entity_match as em
    from entity_review import ReviewQueue, import_proposals
    from entity_store import EntityStore, build_entity


CREATOR = {"level": "creator", "key": "pixiv:50235390"}
DOC = "pixiv:50235390:12430834"
CTX = {"provider": "pixiv", "creator_id": "50235390", "document_id": DOC}


def _ent(source, target, **kw):
    return build_entity(CREATOR, source, target, status="approved", authority="manual", **kw)


class NormalizeKanaTest(unittest.TestCase):
    def test_katakana_to_hiragana(self):
        self.assertEqual("ゆき", em.normalize_kana("ユキ"))
        self.assertEqual("ゆきちゃん", em.normalize_kana("ゆきチャン"))  # 混写
        self.assertEqual("小雪", em.normalize_kana("小雪"))             # 非假名原样


class BestNonexactMatchTest(unittest.TestCase):
    def test_reading_match_across_kana(self):
        ents = [_ent("ユキ", "小雪", readings=["ゆき"])]
        hit = em.best_nonexact_match("ゆき", ents)  # 平假名 mention vs 片假名 source
        self.assertIsNotNone(hit)
        self.assertEqual("reading", hit[1])
        self.assertEqual(1.0, hit[2])

    def test_fuzzy_match_near_typo(self):
        ents = [_ent("アレクサンドル", "亚历山大")]
        hit = em.best_nonexact_match("アレクサンドル ", ents)  # 末尾多空格
        self.assertIsNotNone(hit)
        self.assertEqual("fuzzy", hit[1])
        self.assertGreaterEqual(hit[2], 0.82)

    def test_reading_preferred_over_fuzzy(self):
        ents = [_ent("アレクサ", "亚", readings=["ゆき"]), _ent("ユキコ", "雪子")]
        # mention 'ゆき' 读音命中第一个;对第二个是模糊 → 应取读音
        hit = em.best_nonexact_match("ゆき", ents)
        self.assertEqual("reading", hit[1])

    def test_no_match_below_threshold(self):
        ents = [_ent("田中", "田中")]
        self.assertIsNone(em.best_nonexact_match("山田太郎", ents))

    def test_exact_is_skipped(self):
        ents = [_ent("ユキ", "小雪")]
        self.assertIsNone(em.best_nonexact_match("ユキ", ents))  # 精确由调用方处理


class ImportProposalsFuzzyTest(unittest.TestCase):
    def _harness(self, tmp):
        return EntityStore(Path(tmp) / "ent"), ReviewQueue(Path(tmp) / "q")

    def test_reading_match_routes_to_review_not_new_candidate(self):
        with tempfile.TemporaryDirectory() as t:
            estore, queue = self._harness(t)
            estore.put(_ent("ユキ", "小雪", readings=["ゆき"]))
            before = len(estore.list_scope(CREATOR))
            out = import_proposals([{"mention": "ゆき", "document_id": DOC, "confidence": 0.95,
                                     "suggested_target": "小雪"}], CTX, estore, queue)
            self.assertEqual(1, len(out))
            self.assertEqual("reading_match", out[0]["reason"])
            self.assertEqual(1.0, out[0]["match_score"])
            self.assertEqual(before, len(estore.list_scope(CREATOR)))  # 不建近重复 candidate

    def test_fuzzy_match_routes_to_review(self):
        with tempfile.TemporaryDirectory() as t:
            estore, queue = self._harness(t)
            estore.put(_ent("アレクサンドル", "亚历山大"))
            out = import_proposals([{"mention": "アレクサンドル ", "document_id": DOC,
                                     "confidence": 0.95, "suggested_target": "亚历山大"}], CTX, estore, queue)
            self.assertEqual("fuzzy_match", out[0]["reason"])
            self.assertIn("match_score", out[0])
            self.assertIsNotNone(out[0]["candidate_entity_id"])

    def test_truly_new_mention_still_creates_candidate(self):
        with tempfile.TemporaryDirectory() as t:
            estore, queue = self._harness(t)
            estore.put(_ent("田中", "田中"))
            out = import_proposals([{"mention": "山田太郎", "document_id": DOC, "confidence": 0.95,
                                     "suggested_target": "山田太郎"}], CTX, estore, queue)
            self.assertEqual("new_candidate", out[0]["reason"])  # 无近似 → 仍建 candidate


if __name__ == "__main__":
    unittest.main()
