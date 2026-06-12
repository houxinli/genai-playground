#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import tempfile
import unittest
from pathlib import Path

from tasks.translation.src.scripts.inventory_content import (
    build_inventory,
    inspect_content,
    scan_root,
)


def _write_post(directory: Path, stem: str, text: str = "正文", meta: bool = True) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stem}.txt").write_text(text, encoding="utf-8")
    if meta:
        (directory / f"{stem}.meta.json").write_text("{}", encoding="utf-8")


class InspectContentTest(unittest.TestCase):
    def test_marker_semantics(self):
        self.assertEqual("partial", inspect_content("a\n[翻译未完成]\nb"))
        self.assertEqual("failed", inspect_content("x[翻译失败]y"))
        self.assertEqual("failed", inspect_content("（以下省略）"))
        self.assertEqual("missing", inspect_content("  \n "))
        self.assertEqual("complete", inspect_content("原文\n译文"))


class ScanRootTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "pixiv"
        src = self.root / "111"
        _write_post(src, "a")
        _write_post(src, "b")
        derived = self.root / "111_bilingual"
        derived.mkdir()
        (derived / "a.txt").write_text("原文\n译文", encoding="utf-8")
        (derived / "b.txt").write_text("原文\n[翻译未完成]", encoding="utf-8")
        bak = self.root / "111_bilingual_broken_bak"
        bak.mkdir()
        (bak / "a.txt").write_text("坏", encoding="utf-8")
        orphan = self.root / "999_bilingual"
        orphan.mkdir()
        (orphan / "z.txt").write_text("孤", encoding="utf-8")
        (self.root / "name_maps").mkdir()
        (self.root / "name_maps" / "rules.txt").write_text("规则", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_source_and_derived_classification(self):
        result = scan_root(self.root)
        self.assertEqual(1, len(result["sources"]))
        entry = result["sources"][0]
        self.assertEqual("111", entry["source"])
        self.assertEqual(2, entry["post_count"])
        self.assertEqual(2, entry["with_meta"])
        names = {d["name"]: d for d in entry["derived"]}
        self.assertIn("111_bilingual", names)
        self.assertIn("111_bilingual_broken_bak", names)

    def test_coverage_and_status(self):
        entry = scan_root(self.root)["sources"][0]
        bilingual = next(d for d in entry["derived"] if d["name"] == "111_bilingual")
        self.assertEqual("partial", bilingual["coverage"])
        self.assertEqual({"complete": 1, "partial": 1}, bilingual["status_counts"])

    def test_quarantine_and_orphans(self):
        result = scan_root(self.root)
        entry = result["sources"][0]
        bak = next(d for d in entry["derived"] if d["name"].endswith("_broken_bak"))
        self.assertTrue(bak["quarantine_candidate"])
        self.assertEqual(["999_bilingual"], result["orphan_dirs"])

    def test_excluded_dirs_are_not_sources(self):
        result = scan_root(self.root)
        self.assertNotIn("name_maps", [s["source"] for s in result["sources"]])


class BuildInventoryTest(unittest.TestCase):
    def test_packaged_and_quarantine_aggregation(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            _write_post(data / "pixiv" / "111", "a")
            bak = data / "pixiv" / "111_tmp"
            bak.mkdir()
            (bak / "a.txt").write_text("x", encoding="utf-8")
            (data / "111_bilingual.txt").write_text("打包", encoding="utf-8")
            (data / "111_v2_zh.txt").write_text("打包", encoding="utf-8")
            (data / "config.json").write_text("{}", encoding="utf-8")

            inventory = build_inventory(data, ["pixiv", "fanbox"])
            self.assertEqual(["pixiv/111_tmp"], inventory["quarantine_candidates"])
            packaged = {p["file"]: p for p in inventory["packaged_top_level"]}
            self.assertEqual({"111_bilingual.txt", "111_v2_zh.txt"}, set(packaged))
            self.assertEqual("111", packaged["111_v2_zh.txt"]["matched_source"])
            self.assertTrue(json.dumps(inventory))


if __name__ == "__main__":
    unittest.main()
