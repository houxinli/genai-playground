#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite 可重建投影:填充 store→重建→join 查询;丢弃 db 再重建结果一致(不依赖 SQLite)。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import pipeline_ingest, sqlite_index as sx
except ImportError:  # core/ 在 sys.path 上
    import pipeline_ingest
    import sqlite_index as sx


TESTDATA = Path(__file__).resolve().parent / "testdata"
SRC = TESTDATA / "fixtures" / "pixiv" / "700001" / "700001.txt"
BILINGUAL = TESTDATA / "golden" / "pixiv-700001.render.bilingual.txt"


def _populate_store(tmp: Path):
    """用 ingest_directory 把 fixture 灌进 store(产 revision/candidate/attestation/evaluation/version)。"""
    src_dir = tmp / "53230930"; bil_dir = tmp / "bil"
    src_dir.mkdir(); bil_dir.mkdir()
    shutil.copy(SRC, src_dir / "700001.txt")
    shutil.copy(BILINGUAL, bil_dir / "700001.txt")
    store_root = tmp / "store"
    manifest = pipeline_ingest.ingest_directory("pixiv", src_dir, bil_dir, store_root)
    return store_root, manifest["documents"][0]["document_id"]


class SqliteIndexTest(unittest.TestCase):
    def test_rebuild_and_queries(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            store_root, doc = _populate_store(tmp)
            db = tmp / "index.db"
            counts = sx.rebuild_index(store_root, db)
            self.assertGreater(counts["candidate"], 0)
            self.assertGreater(counts["evaluation"], 0)
            self.assertGreater(counts["segment"], 0)

            conn = sx.connect(db)
            try:
                cands = sx.candidates_for_document(conn, doc)
                self.assertTrue(cands)
                evals = sx.evaluations_for_document(conn, doc)
                self.assertTrue(evals)
                self.assertTrue(all("verdict" in e and "segment_id" in e for e in evals))  # eval 经 candidate join 拿到 segment
                # 某 segment 的证据:candidate + attestation join
                seg = cands[0]["segment_id"]
                ev = sx.segment_evidence(conn, doc, seg)
                self.assertTrue(ev["candidates"])
                self.assertTrue(ev["attestations"])  # legacy 候选有 attestation(producer)
                self.assertIsNotNone(ev["attestations"][0]["producer_name"])
                # 作者级查询
                prov, creator = doc.split(":")[0], doc.split(":")[1]
                self.assertTrue(sx.candidates_for_author(conn, prov, creator))
            finally:
                conn.close()

    def test_drop_and_rebuild_is_consistent(self):
        # SQLite 可丢弃:删库从 JSONL 重建,结果一致(不是真相源)
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            store_root, doc = _populate_store(tmp)
            db = tmp / "index.db"
            c1 = sx.rebuild_index(store_root, db)
            conn = sx.connect(db); rows1 = sx.candidates_for_document(conn, doc); conn.close()
            db.unlink()  # 丢弃
            for suffix in ("-wal", "-shm"):
                p = db.with_name(db.name + suffix)
                if p.exists():
                    p.unlink()
            c2 = sx.rebuild_index(store_root, db)
            conn = sx.connect(db); rows2 = sx.candidates_for_document(conn, doc); conn.close()
            self.assertEqual(c1, c2)
            self.assertEqual(rows1, rows2)

    def test_rebuild_is_idempotent_no_dup(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            store_root, doc = _populate_store(tmp)
            db = tmp / "index.db"
            c1 = sx.rebuild_index(store_root, db)
            c2 = sx.rebuild_index(store_root, db)  # 重跑不翻倍(DROP+CREATE)
            self.assertEqual(c1, c2)


if __name__ == "__main__":
    unittest.main()
