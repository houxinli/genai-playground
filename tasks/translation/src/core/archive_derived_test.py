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


def _layout(tmp: Path):
    """造源目录 + bilingual 派生目录(名 700000_bilingual),内容同 fixture。"""
    src_dir = tmp / "src"; src_dir.mkdir()
    shutil.copy(SRC, src_dir / "700001.txt")
    derived = tmp / f"{CREATOR}_bilingual"; derived.mkdir()
    shutil.copy(BILINGUAL, derived / "700001.txt")
    return src_dir, derived


def _ingest(tmp: Path, src_dir: Path, derived: Path) -> ArtifactStore:
    store_root = tmp / "store"
    pipeline_ingest.ingest_directory("pixiv", src_dir, derived, store_root)  # 用 bilingual 灌库
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
            src_dir, derived = _layout(tmp)
            store = _ingest(tmp, src_dir, derived)  # 这一篇的 legacy candidate 已迁入
            ok, reasons = ad.is_archivable(derived, store, "pixiv", src_dir)
            self.assertTrue(ok, reasons)
            self.assertEqual([], reasons)

    def test_not_imported_refused(self):
        # 内容核验:store 为空(未迁入)→ 重建的 legacy candidate 不在 store → 拒绝
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, derived = _layout(tmp)
            empty_store = ArtifactStore(tmp / "empty")
            ok, reasons = ad.is_archivable(derived, empty_store, "pixiv", src_dir)
            self.assertFalse(ok)
            self.assertTrue(any("未完整迁入" in r or "无 revision" in r for r in reasons))

    def test_revision_present_but_legacy_candidates_missing_refused(self):
        # Codex #115:doc 有 revision/别的工件 ≠ 这一篇 legacy 已迁入。删掉 candidate shard(只留 revision)
        # → 重建的 legacy candidate 不在 store → 拒绝(全覆盖核验,不是「有就算」)
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, derived = _layout(tmp)
            store = _ingest(tmp, src_dir, derived)
            doc = f"pixiv:{CREATOR}:700001"
            self.assertTrue(store.exists("document-revision", doc, store.list_shard("document-revision", doc)[0]["revision_id"]))
            store.shard_path("candidate", doc).unlink()  # 抹掉候选,保留 revision
            ok, reasons = ad.is_archivable(derived, store, "pixiv", src_dir)
            self.assertFalse(ok)
            self.assertTrue(any("未完整迁入" in r for r in reasons))

    def test_missing_source_refused(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, derived = _layout(tmp)
            store = _ingest(tmp, src_dir, derived)
            (src_dir / "700001.txt").unlink()  # 源文件没了,无法核验
            ok, reasons = ad.is_archivable(derived, store, "pixiv", src_dir)
            self.assertFalse(ok)
            self.assertTrue(any("缺源文件" in r for r in reasons))

    def test_source_dir_refused(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, derived = _layout(tmp)
            store = _ingest(tmp, src_dir, derived)
            bare = tmp / CREATOR; bare.mkdir()  # 裸源入口目录
            (bare / "700001.txt").write_text("...", encoding="utf-8")
            ok, reasons = ad.is_archivable(bare, store, "pixiv", src_dir)
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
