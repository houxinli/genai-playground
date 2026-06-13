#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""legacy 导入:bilingual → legacy Candidate(确定性幂等、标签区分、空译文与截断容错)。"""

from __future__ import annotations

import json
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

EXPECTED_TEXT = {
    "metadata.title": "早晨的问候",
    "metadata.caption": "用于测试的简短文章。",
    "metadata.tags": "[テスト / 测试, 日常 / 日常]",
    "body": ["「早上好」", "今天天气真好。"],
}


class LegacyImportTest(unittest.TestCase):
    def _build(self, label="momizi-style"):
        return li.build_legacy_candidates("pixiv", SRC, BILINGUAL, label)

    def test_round_trip_recovers_all_segments(self):
        rev = si.build_document_revision("pixiv", SRC)
        candidates, attestations, issues = self._build()
        self.assertEqual([], issues)
        self.assertEqual(len(rev["segments"]), len(candidates))
        self.assertEqual(len(candidates), len(attestations))
        for c in candidates:
            self.assertEqual([], validate_artifact("candidate", c))
            self.assertEqual(3, c["schema_version"])
            self.assertRegex(c["candidate_id"], r"^cand_[0-9a-f]{64}$")
            self.assertNotIn("producer", c)  # 来源在 attestation
        by_cand = {a["candidate_id"]: a for a in attestations}
        for c in candidates:
            a = by_cand[c["candidate_id"]]
            self.assertEqual([], validate_artifact("attestation", a))
            self.assertEqual("legacy", a["producer"]["type"])
            self.assertEqual("momizi-style", a["producer"]["name"])
            self.assertEqual("momizi-style", a["legacy_label"])

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

    def test_created_at_is_stable_published_at(self):
        # attestation.created_at 取源 published_at,稳定可复现(不随导入时刻变)
        attestations = self._build()[1]
        self.assertTrue(all(a["created_at"] == "2026-01-01T09:00:00+09:00" for a in attestations))

    def test_write_is_idempotent(self):
        candidates, attestations, _ = self._build()
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            self.assertEqual((len(candidates), 0), li.write_candidates(candidates, store))
            self.assertEqual((0, len(candidates)), li.write_candidates(candidates, store))
            self.assertEqual((len(attestations), 0), li.write_attestations(attestations, store))
            self.assertEqual((0, len(attestations)), li.write_attestations(attestations, store))
            self.assertEqual(len(candidates), len(list(store.glob("cand_*.json"))))
            self.assertEqual(len(attestations), len(list(store.glob("att_*.json"))))

    def test_conflicting_existing_artifact_raises(self):
        candidates, _, _ = self._build()
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            li.write_candidates(candidates, store)
            # 篡改一个已存在工件 -> 同 id 不同内容必须报错
            victim = next(store.glob("cand_*.json"))
            victim.write_text(json.dumps({"corrupt": True}), encoding="utf-8")
            with self.assertRaises(ValueError):
                li.write_candidates(candidates, store)

    def test_distinct_labels_dedup_candidates_distinct_attestations(self):
        # 内容寻址:两个标签产出相同译文 → 同一 Candidate(去重),但来源各记一条 Attestation
        ca, aa, _ = self._build("dir_bilingual")
        cb, ab, _ = self._build("dir_bilingual_v2")
        cand_a = {c["candidate_id"] for c in ca}
        cand_b = {c["candidate_id"] for c in cb}
        self.assertEqual(cand_a, cand_b)  # 文本相同 → candidate 完全去重
        att_a = {a["attestation_id"] for a in aa}
        att_b = {a["attestation_id"] for a in ab}
        self.assertEqual(set(), att_a & att_b)  # legacy_label 不同 → attestation 不同

    def test_two_labels_same_store_dedup_on_disk(self):
        # 落到同一 store:第二个 label 不新增 Candidate,只追加 Attestation(N Candidate + 2N Attestation)
        ca, aa, _ = self._build("dir_bilingual")
        cb, ab, _ = self._build("dir_bilingual_v2")
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            self.assertEqual((len(ca), 0), li.write_candidates(ca, store))
            self.assertEqual((len(aa), 0), li.write_attestations(aa, store))
            # 第二个 label:candidate 全部命中去重(0 写入),attestation 全部新增
            self.assertEqual((0, len(cb)), li.write_candidates(cb, store))
            self.assertEqual((len(ab), 0), li.write_attestations(ab, store))
            self.assertEqual(len(ca), len(list(store.glob("cand_*.json"))))
            self.assertEqual(len(aa) + len(ab), len(list(store.glob("att_*.json"))))

    def test_empty_translation_does_not_bleed_into_next_segment(self):
        # 合法的空译文(译文行为空)不应让下一段原文被当成上一段译文(基线含 112 个 empty)
        rev = si.build_document_revision("pixiv", SRC)
        body_segs = [s for s in rev["segments"] if s["kind"] == "body"]
        with tempfile.TemporaryDirectory() as tmp:
            bil = Path(tmp) / "empty.txt"
            # 第一句译文留空,第二句正常
            bil.write_text(
                "---\nnovel_id: 700001\n---\n「おはよう」\n\n今日はいい天気だ。\n今天天气真好。\n",
                encoding="utf-8",
            )
            translations, issues = li.parse_bilingual_translations(rev, bil.read_text(encoding="utf-8"))
            self.assertEqual("", translations[body_segs[0]["segment_id"]])
            self.assertEqual("今天天气真好。", translations[body_segs[1]["segment_id"]])
            self.assertEqual([], issues)

    def test_metadata_source_change_is_skipped_with_issue(self):
        rev = si.build_document_revision("pixiv", SRC)
        with tempfile.TemporaryDirectory() as tmp:
            bil = Path(tmp) / "meta_changed.txt"
            # title 源值被改(与 revision 不一致)-> 跳过且记 issue
            bil.write_text(
                "---\nnovel_id: 700001\ntitle: 別のタイトル\ntitle: 另一个标题\n---\n",
                encoding="utf-8",
            )
            translations, issues = li.parse_bilingual_translations(rev, bil.read_text(encoding="utf-8"))
            title_seg = next(s for s in rev["segments"] if s["kind"] == "metadata.title")
            self.assertNotIn(title_seg["segment_id"], translations)
            self.assertTrue(any("source changed" in m for m in issues), issues)

    def test_truncated_bilingual_partial_import_with_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            truncated = Path(tmp) / "trunc.txt"
            full = BILINGUAL.read_text(encoding="utf-8")
            head = full.split("「早上好」")[0] + "「早上好」\n"
            truncated.write_text(head, encoding="utf-8")
            candidates, _attestations, issues = li.build_legacy_candidates("pixiv", SRC, truncated, "trunc")
            self.assertTrue(any("truncated" in m for m in issues), issues)
            self.assertTrue(any(c["text"] == "「早上好」" for c in candidates))

    def test_import_directory_pairs_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            srcdir, bildir, store = tmp / "src", tmp / "bil", tmp / "store"
            srcdir.mkdir(); bildir.mkdir()
            (srcdir / "700001.txt").write_text(SRC.read_text(encoding="utf-8"), encoding="utf-8")
            (bildir / "700001.txt").write_text(BILINGUAL.read_text(encoding="utf-8"), encoding="utf-8")
            (bildir / "999999.txt").write_text("---\npost_id: 999999\n---\nx\ny\n", encoding="utf-8")
            report = li.import_directory("pixiv", srcdir, bildir, "dir_label", store)
            self.assertEqual(1, report["posts"])
            self.assertEqual(["999999.txt"], report["missing_source"])
            self.assertEqual(report["candidates"], report["candidates_written"])
            self.assertEqual(report["candidates"], report["attestations_written"])
            self.assertEqual([], report["posts_with_issues"])
            self.assertEqual(report["candidates"], len(list(store.glob("cand_*.json"))))
            self.assertEqual(report["candidates"], len(list(store.glob("att_*.json"))))


if __name__ == "__main__":
    unittest.main()
