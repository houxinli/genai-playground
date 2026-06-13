#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source adapter:目录 -> DocumentRevision 列表。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import source_identity as si
    from .source_adapter import adapt_directory, iter_source_files
except ImportError:  # core/ 在 sys.path 上
    import source_identity as si
    from source_adapter import adapt_directory, iter_source_files


FIXTURES = Path(__file__).resolve().parent / "testdata" / "fixtures"


class SourceAdapterTest(unittest.TestCase):
    def test_adapt_directory_builds_revision_per_source(self):
        root = FIXTURES / "pixiv" / "700001"
        revisions = adapt_directory("pixiv", root)
        self.assertEqual(1, len(revisions))
        direct = si.build_document_revision("pixiv", root / "700001.txt")
        self.assertEqual(direct, revisions[0])

    def test_iter_source_files_excludes_meta_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.txt").write_text("x", encoding="utf-8")
            (root / "a.txt").write_text("x", encoding="utf-8")
            (root / "a.meta.json").write_text("{}", encoding="utf-8")
            files = iter_source_files(root)
            self.assertEqual(["a.txt", "b.txt"], [p.name for p in files])

    def test_adapt_fanbox_reads_creator_identity(self):
        revisions = adapt_directory("fanbox", FIXTURES / "fanbox" / "800001")
        self.assertEqual("fanbox:800000:800001", revisions[0]["document_id"])


if __name__ == "__main__":
    unittest.main()
