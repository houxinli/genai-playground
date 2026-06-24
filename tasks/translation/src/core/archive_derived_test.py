#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史派生目录归档(#62):gate(已迁入才可归档)+ quarantine(只隔离不删 + manifest)。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import archive_derived as ad, pipeline_ingest
    from .artifact_store import ArtifactStore
except ImportError:  # core/ 在 sys.path 上
    import archive_derived as ad
    import pipeline_ingest
    from artifact_store import ArtifactStore


TESTDATA = Path(__file__).resolve().parent / "testdata"
SRC = TESTDATA / "fixtures" / "pixiv" / "700001" / "700001.txt"
BILINGUAL = TESTDATA / "golden" / "pixiv-700001.render.bilingual.txt"
CREATOR = "700000"  # fixture 的 document_id 是 pixiv:700000:700001


def _store_with_700001(tmp: Path) -> ArtifactStore:
    src_dir = tmp / "src"; bil_dir = tmp / "bil"
    src_dir.mkdir(); bil_dir.mkdir()
    shutil.copy(SRC, src_dir / "700001.txt")
    shutil.copy(BILINGUAL, bil_dir / "700001.txt")
    store_root = tmp / "store"
    pipeline_ingest.ingest_directory("pixiv", src_dir, bil_dir, store_root)
    return ArtifactStore(store_root)


class ParseNameTest(unittest.TestCase):
    def test_derived_vs_source(self):
        self.assertEqual(("700000", "_bilingual"), ad.parse_derived_name("700000_bilingual"))
        self.assertEqual(("700000", "_bilingual_v2"), ad.parse_derived_name("700000_bilingual_v2"))
        self.assertIsNone(ad.parse_derived_name("700000"))  # 裸源入口目录


class IsArchivableTest(unittest.TestCase):
    def test_imported_dir_is_archivable(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            store = _store_with_700001(tmp)
            d = tmp / f"{CREATOR}_bilingual"; d.mkdir()
            (d / "700001.txt").write_text("...", encoding="utf-8")
            ok, reasons = ad.is_archivable(d, store, "pixiv")
            self.assertTrue(ok, reasons)
            self.assertEqual([], reasons)

    def test_unimported_dir_refused(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            store = _store_with_700001(tmp)
            d = tmp / "999999_bilingual"; d.mkdir()
            (d / "12345.txt").write_text("...", encoding="utf-8")  # store 无此 doc
            ok, reasons = ad.is_archivable(d, store, "pixiv")
            self.assertFalse(ok)
            self.assertTrue(any("未迁入" in r for r in reasons))

    def test_source_dir_refused(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            store = _store_with_700001(tmp)
            d = tmp / CREATOR; d.mkdir()  # 裸源入口目录
            (d / "700001.txt").write_text("...", encoding="utf-8")
            ok, reasons = ad.is_archivable(d, store, "pixiv")
            self.assertFalse(ok)
            self.assertTrue(any("源入口" in r for r in reasons))


class QuarantineTest(unittest.TestCase):
    def test_moves_not_deletes_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            d = tmp / f"{CREATOR}_bilingual"; d.mkdir()
            (d / "700001.txt").write_text("内容", encoding="utf-8")
            q = tmp / "quarantine"
            entry = ad.quarantine_dir(d, q, "pixiv")
            self.assertFalse(d.exists())                       # 原目录已移走
            moved = q / f"{CREATOR}_bilingual" / "700001.txt"
            self.assertTrue(moved.is_file())                   # 内容仍在(只移不删)
            self.assertEqual("内容", moved.read_text(encoding="utf-8"))
            self.assertEqual(["700001"], entry["posts"])
            manifest = (q / "archive_manifest.jsonl").read_text(encoding="utf-8")
            self.assertIn(str(d), manifest)                    # manifest 记原路径

    def test_refuses_overwrite_existing_quarantine(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            d = tmp / f"{CREATOR}_zh"; d.mkdir()
            (d / "700001.txt").write_text("x", encoding="utf-8")
            q = tmp / "quarantine"; (q / f"{CREATOR}_zh").mkdir(parents=True)  # 已存在
            with self.assertRaises(FileExistsError):
                ad.quarantine_dir(d, q, "pixiv")
            self.assertTrue(d.exists())  # 失败时原目录保留(不丢数据)


class ReportTest(unittest.TestCase):
    def test_report_lists_derived_only(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / "pixiv" / "700000_bilingual").mkdir(parents=True)
            (tmp / "pixiv" / "700000_bilingual" / "700001.txt").write_text("x", encoding="utf-8")
            (tmp / "pixiv" / "700000").mkdir()  # 源入口,不应入报告
            rep = ad.report(tmp, ["pixiv"])
            self.assertEqual(1, rep["count"])
            self.assertEqual("_bilingual", rep["derived_dirs"][0]["suffix"])


if __name__ == "__main__":
    unittest.main()
