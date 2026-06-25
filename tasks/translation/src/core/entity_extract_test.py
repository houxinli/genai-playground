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


class AgentExtractionTest(unittest.TestCase):
    def test_build_job_has_text_and_skips_tags(self):
        rev = _revision([
            _seg("rev_a:000001:dead", "metadata.title", "ユキの話"),
            _seg("rev_a:000002:beef", "body", "ユキは笑った。"),
            _seg("rev_a:000003:f00d", "metadata.tags", "[R-18]"),  # 不进 job
        ])
        job = ee.build_extraction_job(rev)
        self.assertEqual(DOC, job["document_id"])
        self.assertEqual("name-extraction", job["task_type"])
        kinds = {s["kind"] for s in job["segments"]}
        self.assertIn("body", kinds); self.assertIn("metadata.title", kinds)
        self.assertNotIn("metadata.tags", kinds)

    def test_import_result_creates_candidate_with_readings(self):
        with tempfile.TemporaryDirectory() as t:
            estore = EntityStore(Path(t) / "e"); queue = ReviewQueue(Path(t) / "q")
            result = {"proposals": [
                {"mention": "ユキ", "readings": ["ゆき"], "suggested_target": "小雪", "confidence": 0.9,
                 "segment_id": "rev_abcd1234:000002:beef"},
            ]}
            reviews = ee.import_extraction_result(result, CTX, estore, queue)
            self.assertTrue(reviews)
            self.assertEqual("new_candidate", reviews[0]["reason"])
            ent = [e for e in estore.list_scope(CREATOR) if e["source"] == "ユキ"][0]
            self.assertEqual(["ゆき"], ent["readings"])   # LLM 给的读音落进候选
            self.assertEqual("小雪", ent["target"])
            self.assertEqual("candidate", ent["status"])

    def test_import_result_ignores_result_document_id(self):
        # document_id 权威取自 scope_ctx,不信 result 里夹带的
        with tempfile.TemporaryDirectory() as t:
            estore = EntityStore(Path(t) / "e"); queue = ReviewQueue(Path(t) / "q")
            result = {"proposals": [{"mention": "田中", "document_id": "pixiv:999:111",
                                     "suggested_target": "田中", "confidence": 0.8}]}
            reviews = ee.import_extraction_result(result, CTX, estore, queue)
            self.assertEqual(DOC, reviews[0]["document_id"])  # 用 scope 的 DOC,非 result 的


class CliScopeGuardTest(unittest.TestCase):
    """Codex #117:链接作用域取自 document_id;误填/空路径必须挡住。"""

    def _write_rev(self, tmp):
        rev_path = Path(tmp) / "rev.json"
        import json
        rev_path.write_text(json.dumps({"document_id": DOC, "revision_id": "rev_x", "segments": []}),
                            encoding="utf-8")
        return rev_path

    def _run(self, argv):
        import sys
        old = sys.argv
        sys.argv = ["entity_extract.py", *argv]
        try:
            return ee.main()
        finally:
            sys.argv = old

    def test_mismatched_creator_id_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            rev = self._write_rev(t)
            with self.assertRaises(SystemExit):  # 999999 ≠ document_id 的 50235390
                self._run(["--revision", str(rev), "--link", "--entity-store", str(Path(t) / "e"),
                           "--queue", str(Path(t) / "q"), "--creator-id", "999999"])

    def test_link_without_queue_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            rev = self._write_rev(t)
            with self.assertRaises(SystemExit):
                self._run(["--revision", str(rev), "--link", "--entity-store", str(Path(t) / "e")])

    def test_derives_scope_and_links(self):
        with tempfile.TemporaryDirectory() as t:
            rev = self._write_rev(t)  # segments 空 → 0 proposal,但作用域应由 document_id 推得不报错
            rc = self._run(["--revision", str(rev), "--link", "--entity-store", str(Path(t) / "e"),
                            "--queue", str(Path(t) / "q")])
            self.assertEqual(0, rc)


if __name__ == "__main__":
    unittest.main()
