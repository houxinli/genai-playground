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
