#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端批量编排器:fixture 目录跑通(发布+渲染)+ 逐文档容错。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import pipeline_ingest
    from .artifact_store import ArtifactStore
except ImportError:  # core/ 在 sys.path 上
    import pipeline_ingest
    from artifact_store import ArtifactStore


TESTDATA = Path(__file__).resolve().parent / "testdata"
SRC = TESTDATA / "fixtures" / "pixiv" / "700001" / "700001.txt"
BILINGUAL = TESTDATA / "golden" / "pixiv-700001.render.bilingual.txt"  # 全字段双键
RENDER_GOLDEN = BILINGUAL
DOC_SID = "700001"


def _layout(tmp: Path):
    """造 source/ 与 bilingual/ 目录,同名 700001.txt。"""
    src_dir = tmp / "src"; bil_dir = tmp / "bil"
    src_dir.mkdir(); bil_dir.mkdir()
    shutil.copy(SRC, src_dir / f"{DOC_SID}.txt")
    shutil.copy(BILINGUAL, bil_dir / f"{DOC_SID}.txt")
    return src_dir, bil_dir


class PipelineIngestTest(unittest.TestCase):
    def test_directory_publishes_renders_and_populates_store(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, bil_dir = _layout(tmp)
            store_root = tmp / "store"; render_dir = tmp / "out"
            manifest = pipeline_ingest.ingest_directory("pixiv", src_dir, bil_dir, store_root, render_dir)
            self.assertEqual(1, manifest["summary"]["total"])
            self.assertEqual(1, manifest["summary"]["published"])
            self.assertEqual(0, manifest["summary"]["errors"])
            doc = manifest["documents"][0]["document_id"]
            store = ArtifactStore(store_root)
            # store 被填充:revision / candidate / evaluation / version / current ref
            self.assertEqual(1, len(store.list_shard("document-revision", doc)))
            self.assertTrue(store.list_shard("candidate", doc))
            self.assertTrue(store.list_shard("evaluation", doc))
            self.assertIsNotNone(store.current_ref(doc))
            self.assertEqual(manifest["documents"][0]["version_id"], store.current_ref(doc)["version_id"])
            # 渲染产物逐字节符合 golden(bilingual)+ zh 存在
            got = (render_dir / f"{DOC_SID}.bilingual.txt").read_text(encoding="utf-8")
            self.assertEqual(RENDER_GOLDEN.read_text(encoding="utf-8"), got)
            self.assertTrue((render_dir / f"{DOC_SID}.zh.txt").is_file())
            self.assertTrue((render_dir / "ingest_manifest.json").is_file())

    def test_existing_newer_ref_is_not_rolled_back(self):
        # Codex #97:store 已有别的(更新)current ref 时,批量 ingest 不得回滚到 legacy 版本
        try:
            from artifact_schemas import version_id_for
        except ImportError:
            from .artifact_schemas import version_id_for
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, bil_dir = _layout(tmp)
            store_root = tmp / "store"
            m1 = pipeline_ingest.ingest_directory("pixiv", src_dir, bil_dir, store_root)
            doc = m1["documents"][0]["document_id"]
            store = ArtifactStore(store_root)
            legacy_v = store.current_ref(doc)["version_id"]
            # 模拟他人发布了一个不同的更新版本(改 created_at → 不同 version_id)
            content = {k: v for k, v in store.get("document-version", doc, legacy_v).items() if k != "version_id"}
            content["created_at"] = "2099-01-01T00:00:00Z"
            v2 = {"version_id": version_id_for(content), **content}
            store.put_many(doc, [v2])
            store.publish(doc, v2["version_id"], expected_version_id=legacy_v)
            # 再跑批量 ingest:不得把 ref 回滚到 legacy 版本
            m2 = pipeline_ingest.ingest_directory("pixiv", src_dir, bil_dir, store_root)
            self.assertEqual("ref_exists_kept", m2["documents"][0]["status"])
            self.assertEqual(v2["version_id"], store.current_ref(doc)["version_id"])

    def test_merge_author_builds_book_in_sid_order(self):
        with tempfile.TemporaryDirectory() as t:
            rd = Path(t)
            # 故意乱序写入,合并应按 source_id 升序
            (rd / "200.bilingual.txt").write_text("---\ntitle: 第二篇\ntitle: 乙\n---\n乙正文\n", encoding="utf-8")
            (rd / "100.bilingual.txt").write_text("---\ntitle: 第一篇\ntitle: 甲\n---\n甲正文\n", encoding="utf-8")
            (rd / "100.zh.txt").write_text("---\ntitle: 甲\n\n\n甲译文\n", encoding="utf-8")
            (rd / "200.zh.txt").write_text("---\ntitle: 乙\n\n\n乙译文\n", encoding="utf-8")
            res = pipeline_ingest.merge_author(rd, "53230930", ["200", "100"])
            self.assertEqual(2, res["bilingual"]["chapters"])
            book = (rd / "53230930_bilingual.txt").read_text(encoding="utf-8")
            self.assertTrue(book.startswith("第1章 甲\n"))   # 100 在前(标题取译文行)
            self.assertIn("第2章 乙", book)
            self.assertLess(book.index("第1章 甲"), book.index("第2章 乙"))
            zh = (rd / "53230930_zh.txt").read_text(encoding="utf-8")
            self.assertIn("第1章 甲", zh); self.assertIn("甲译文", zh)

    def test_merge_ignores_stale_files_on_disk(self):
        # Codex #103:只合并本次 source_ids,磁盘上的遗留/他作者文件不卷进书
        with tempfile.TemporaryDirectory() as t:
            rd = Path(t)
            (rd / "100.zh.txt").write_text("---\ntitle: 甲\n\n\n甲译文\n", encoding="utf-8")
            (rd / "999.zh.txt").write_text("---\ntitle: 旧\n\n\n遗留译文\n", encoding="utf-8")  # 上次遗留
            res = pipeline_ingest.merge_author(rd, "53230930", ["100"])  # 本次只渲染了 100
            self.assertEqual(1, res["zh"]["chapters"])
            book = (rd / "53230930_zh.txt").read_text(encoding="utf-8")
            self.assertIn("甲译文", book)
            self.assertNotIn("遗留译文", book)  # 遗留文件不入书

    def test_directory_run_produces_merged_book(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, bil_dir = _layout(tmp)
            render_dir = tmp / "out"
            m = pipeline_ingest.ingest_directory("pixiv", src_dir, bil_dir, tmp / "store", render_dir)
            self.assertIn("bilingual", m["merged"])  # 合并书随批量产出
            self.assertTrue((render_dir / f"{src_dir.name}_bilingual.txt").is_file())

    def test_missing_bilingual_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "src"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / f"{DOC_SID}.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir()  # 空,无匹配 bilingual
            manifest = pipeline_ingest.ingest_directory("pixiv", src_dir, bil_dir, tmp / "store")
            self.assertEqual("skipped_no_bilingual", manifest["documents"][0]["status"])
            self.assertEqual(1, manifest["summary"]["skipped"])

    def test_bad_source_is_isolated_not_fatal(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, bil_dir = _layout(tmp)
            (src_dir / "junk.txt").write_text("不是合法 front matter", encoding="utf-8")
            (bil_dir / "junk.txt").write_text("也不合法", encoding="utf-8")
            manifest = pipeline_ingest.ingest_directory("pixiv", src_dir, bil_dir, tmp / "store")
            self.assertEqual(2, manifest["summary"]["total"])
            self.assertEqual(1, manifest["summary"]["published"])  # 好文档照常发布
            self.assertEqual(1, manifest["summary"]["errors"])      # 坏文档被隔离


if __name__ == "__main__":
    unittest.main()
