#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""legacy 导入:bilingual → legacy Candidate(确定性幂等、标签区分、截断容错)。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import legacy_import as li
    from . import source_identity as si
    from .artifact_schemas import validate_artifact
except ImportError:  # core/ 在 sys.path 上
    import legacy_import as li
    import source_identity as si
    from artifact_schemas import validate_artifact


TESTDATA = Path(__file__).resolve().parent / "testdata"
SRC = TESTDATA / "fixtures" / "pixiv" / "700001" / "700001.txt"
BILINGUAL = TESTDATA / "golden" / "pixiv-700001.render.bilingual.txt"
NOW = "2026-06-13T00:00:00Z"

EXPECTED_TEXT = {
    "metadata.title": "早晨的问候",
    "metadata.caption": "用于测试的简短文章。",
    "metadata.tags": "[テスト / 测试, 日常 / 日常]",
    "body": ["「早上好」", "今天天气真好。"],
}


class LegacyImportTest(unittest.TestCase):
    def _build(self, label="momizi-style"):
        return li.build_legacy_candidates("pixiv", SRC, BILINGUAL, label, NOW)

    def test_round_trip_recovers_all_segments(self):
        rev = si.build_document_revision("pixiv", SRC)
        candidates, issues = self._build()
        self.assertEqual([], issues)
        self.assertEqual(len(rev["segments"]), len(candidates))
        for c in candidates:
            self.assertEqual([], validate_artifact("candidate", c))
            self.assertEqual("legacy", c["producer"]["type"])
            self.assertEqual("momizi-style", c["producer"]["name"])
            self.assertEqual("legacy", c["purpose"])

    def test_recovered_text_matches_source_translations(self):
        rev = si.build_document_revision("pixiv", SRC)
        by_seg = {c["segment_id"]: c["text"] for c in self._build()[0]}
        body_texts = []
        for seg in rev["segments"]:
            if seg["kind"] == "body":
                body_texts.append(by_seg[seg["segment_id"]])
            else:
                self.assertEqual(EXPECTED_TEXT[seg["kind"]], by_seg[seg["segment_id"]], seg["kind"])
        self.assertEqual(EXPECTED_TEXT["body"], body_texts)

    def test_write_is_idempotent(self):
        candidates, _ = self._build()
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            w1, s1 = li.write_candidates(candidates, store)
            self.assertEqual((len(candidates), 0), (w1, s1))
            w2, s2 = li.write_candidates(candidates, store)
            self.assertEqual((0, len(candidates)), (w2, s2))  # 重复导入零新增
            self.assertEqual(len(candidates), len(list(store.glob("*.json"))))

    def test_distinct_labels_yield_distinct_candidates(self):
        a = {c["candidate_id"] for c in self._build("dir_bilingual")[0]}
        b = {c["candidate_id"] for c in self._build("dir_bilingual_v2")[0]}
        self.assertEqual(set(), a & b)  # 不同目录标签 = 不同 candidate,保留来源

    def test_truncated_bilingual_partial_import_with_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            truncated = Path(tmp) / "trunc.txt"
            # 只保留 front matter + 第一段正文对,丢掉后续
            full = BILINGUAL.read_text(encoding="utf-8")
            head = full.split("「早上好」")[0] + "「早上好」\n"
            truncated.write_text(head, encoding="utf-8")
            candidates, issues = li.build_legacy_candidates("pixiv", SRC, truncated, "trunc", NOW)
            self.assertTrue(any("truncated" in m for m in issues), issues)
            # metadata + 第一句仍被导入
            self.assertTrue(any(c["text"] == "「早上好」" for c in candidates))


    def test_import_directory_pairs_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            srcdir, bildir, store = tmp / "src", tmp / "bil", tmp / "store"
            srcdir.mkdir(); bildir.mkdir()
            (srcdir / "700001.txt").write_text(SRC.read_text(encoding="utf-8"), encoding="utf-8")
            (bildir / "700001.txt").write_text(BILINGUAL.read_text(encoding="utf-8"), encoding="utf-8")
            # bilingual 多一个无源配对的文件 -> 计入 missing_source
            (bildir / "999999.txt").write_text("---\npost_id: 999999\n---\nx\ny\n", encoding="utf-8")
            report = li.import_directory("pixiv", srcdir, bildir, "dir_label", store, NOW)
            self.assertEqual(1, report["posts"])
            self.assertEqual(["999999.txt"], report["missing_source"])
            self.assertEqual(report["candidates"], report["written"])
            self.assertEqual([], report["posts_with_issues"])


if __name__ == "__main__":
    unittest.main()
