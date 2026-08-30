#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import tempfile
import unittest
from pathlib import Path

from tasks.translation.src.scripts.coverage_report import scan


FRONT = "---\npost_id: {sid}\ntitle: t\nlang: ja\n---\n本文\n"


def _source(directory: Path, sid: str, *, meta: bool = True) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{sid}.txt").write_text(FRONT.format(sid=sid), encoding="utf-8")
    if meta:
        (directory / f"{sid}.meta.json").write_text("{}", encoding="utf-8")


def _ref(ws_root: Path, provider: str, creator: str, sid: str) -> None:
    d = ws_root / "ws1" / "store" / "refs" / provider / creator
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.json").write_text(json.dumps({"version_id": "v1"}), encoding="utf-8")


class CoverageReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name) / "data"
        self.ws = self.data / "workspaces"
        self.ws.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def _rows(self):
        return {r["creator"]: r for r in scan(self.data, self.ws)}

    def test_missing_ref_is_reported(self):
        _source(self.data / "fanbox" / "c1", "100")
        _source(self.data / "fanbox" / "c1", "200")
        _ref(self.ws, "fanbox", "c1", "100")
        row = self._rows()["c1"]
        self.assertEqual((row["downloaded"], row["published"]), (2, 1))
        self.assertEqual([m["source_id"] for m in row["missing"]], ["200"])
        self.assertEqual(row["missing"][0]["reason"], "untranslated")

    def test_source_without_meta_still_counted(self):
        """浏览器脚本只落 txt;以 meta.json 为准会让这类篇整体消失在分母里。"""
        _source(self.data / "fanbox" / "c1", "100", meta=False)
        row = self._rows()["c1"]
        self.assertEqual(row["downloaded"], 1)
        self.assertEqual([m["source_id"] for m in row["missing"]], ["100"])

    def test_derived_directories_skipped(self):
        _source(self.data / "pixiv" / "111", "100")
        _ref(self.ws, "pixiv", "111", "100")
        _source(self.data / "pixiv" / "111_bilingual", "100")
        self.assertEqual(set(self._rows()), {"111"})

    def test_alias_dir_not_flagged_when_published_under_real_creator(self):
        """pixiv_mini 之类的取样别名目录:同一 source_id 已在真 creator 下发布。"""
        _source(self.data / "pixiv" / "111", "100")
        _source(self.data / "pixiv" / "pixiv_mini", "100")
        _ref(self.ws, "pixiv", "111", "100")
        self.assertEqual(self._rows()["pixiv_mini"]["missing"], [])

    def test_broken_front_matter_separated_from_untranslated(self):
        d = self.data / "pixiv" / "111"
        d.mkdir(parents=True)
        (d / "100.txt").write_text("没有 front matter\n", encoding="utf-8")
        reason = self._rows()["111"]["missing"][0]["reason"]
        self.assertNotEqual(reason, "untranslated")


if __name__ == "__main__":
    unittest.main()
