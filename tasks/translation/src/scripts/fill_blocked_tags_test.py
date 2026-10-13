#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.fill_blocked_tags import build_glossary, fill, render_tags  # noqa: E402

TAGS = "[R-18, ロリ爆乳, 乳内射精]"


def _workspace(root: Path, name: str, rows):
    ws = root / name
    (ws / "results").mkdir(parents=True)
    (ws / "jobs").mkdir()
    sid = name.split("-")[1]
    segs = [{"kind": k, "source_text": s} for k, s, _ in rows]
    (ws / "jobs" / f"{sid}.job.json").write_text(json.dumps({"segments": segs}), encoding="utf-8")
    body = "".join(f"{i}\t{s[:6]}\t{t}\n" for i, (_, s, t) in enumerate(rows))
    (ws / "results" / f"{sid}.zh.tsv").write_text(body, encoding="utf-8")
    return ws


class FillBlockedTagsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # 已发布作品提供词典;ロリ爆乳 出现 2 次译「萝莉爆乳」、1 次译「别的」→ 取最高频
        for sid, zh in (("1", "萝莉爆乳"), ("2", "萝莉爆乳"), ("3", "别的")):
            _workspace(self.root, f"pixiv-{sid}", [
                ("metadata.tags", "[ロリ爆乳, 乳内射精]", f"[ロリ爆乳 / {zh}, 乳内射精 / 乳内射精]")])
        self.glossary = build_glossary(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_glossary_takes_most_frequent_translation(self):
        self.assertEqual("萝莉爆乳", self.glossary["ロリ爆乳"])

    def test_fills_only_empty_tag_rows_and_never_overwrites(self):
        ws = _workspace(self.root, "pixiv-9", [
            ("metadata.tags", TAGS, ""),
            ("body", "本文", "已有译文")])
        self.glossary["R-18"] = "R-18"
        filled, unknown = fill(ws / "results" / "9.zh.tsv", ws / "jobs" / "9.job.json", self.glossary)
        self.assertEqual((1, []), (filled, unknown))
        lines = (ws / "results" / "9.zh.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual("[R-18 / R-18, ロリ爆乳 / 萝莉爆乳, 乳内射精 / 乳内射精]", lines[0].split("\t")[-1])
        self.assertEqual("已有译文", lines[1].split("\t")[-1])

    def test_unknown_tag_is_reported_not_guessed(self):
        text, unknown = render_tags("[ロリ爆乳, インピオ]", self.glossary)
        self.assertIsNone(text)
        self.assertEqual(["インピオ"], unknown)

    def test_unknown_tag_leaves_file_untouched(self):
        ws = _workspace(self.root, "pixiv-8", [("metadata.tags", "[インピオ]", "")])
        path = ws / "results" / "8.zh.tsv"
        before = path.read_text(encoding="utf-8")
        filled, unknown = fill(path, ws / "jobs" / "8.job.json", self.glossary)
        self.assertEqual((0, ["インピオ"]), (filled, unknown))
        self.assertEqual(before, path.read_text(encoding="utf-8"))

    def test_non_tag_empty_row_is_not_touched(self):
        ws = _workspace(self.root, "pixiv-7", [("body", "本文", "")])
        filled, _ = fill(ws / "results" / "7.zh.tsv", ws / "jobs" / "7.job.json", self.glossary)
        self.assertEqual(0, filled)


if __name__ == "__main__":
    unittest.main()
