#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import shutil
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from tasks.translation.src.core import translate_user as tu
from tasks.translation.src.core.artifact_store import ArtifactStore
from tasks.translation.src.core.translate_user_test import SRC, _mk
from tasks.translation.src.scripts import paperbridge_novels as pn
from tasks.translation.src.scripts.provenance_report import load_published

TR = {
    "朝の挨拶": "早晨的问候",
    "[テスト, 日常]": "[テスト / 测试, 日常 / 日常]", "「おはよう」": "「おはよう」",
    "テスト用の短い文章です。": "测试作者(テスト)的短文。",
    "今日はいい天気だ。": "今天天气真好。",
}
KEY = "pixiv:700000:700001"


class PaperbridgeNovelsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.wsroot = root / "workspaces"
        self.ws = self.wsroot / "pixiv-700001"
        (self.ws / "src").mkdir(parents=True)
        shutil.copy(SRC, self.ws / "src" / "700001.txt")
        self.data = root / "data"
        report = tu.translate_document(
            "pixiv", self.ws / "src" / "700001.txt", ArtifactStore(self.ws / "store"), _mk(TR),
            render_dir=self.ws / "rendered", results_dir=self.ws / "results", jobs_dir=self.ws / "jobs")
        self.assertTrue(report["published"], report)

    def tearDown(self):
        self.temp.cleanup()

    def _ref(self):
        return next(self.wsroot.glob("*/store/refs/pixiv/700000/700001.json"))

    def _export(self, **kwargs):
        batch, notes = pn.export_batch(self.wsroot, "pixiv", "700000", creator_name="テスト作者", **kwargs)
        return batch, notes

    def _seg(self, work, src):
        return next(s for s in work["segments"] if s["src"] == src)

    def test_export_carries_published_text_and_flags(self):
        batch, notes = self._export()
        self.assertEqual(notes, [])
        [work] = batch["works"]
        self.assertEqual((work["key"], work["title"], work["title_zh"]), (KEY, "朝の挨拶", "早晨的问候"))
        self.assertEqual(self._seg(work, "「おはよう」")["flags"], ["kana_residue"])
        # tags 行「原词 / 中文」带假名是设计如此,不标。
        self.assertEqual(self._seg(work, "[テスト, 日常]")["flags"], [])
        # 括注读音不算残留。
        self.assertEqual(self._seg(work, "テスト用の短い文章です。")["flags"], [])
        self.assertEqual([s["n"] for s in work["segments"]], list(range(len(work["segments"]))))
        self.assertEqual(self._export(ids=["999"])[1], ["999: 没有已发布版本(未翻译或 unresolved),不导出"])

    def test_import_republishes_and_logs_edit(self):
        [work] = self._export()[0]["works"]
        seg = self._seg(work, "「おはよう」")
        edits = [{"work": KEY, "n": seg["n"], "text": "「早上好」", "base_text": seg["zh"], "base_version": work["version_id"]}]
        kwargs = dict(workspaces_root=self.wsroot, data_root=self.data, entity_store=self.data / "entities")

        [dry] = pn.import_edits(edits, dry_run=True, **kwargs)
        self.assertEqual(dry["status"], "ready", dry)
        self.assertEqual(load_published(self._ref())["version_id"], work["version_id"])

        [rep] = pn.import_edits(edits, dry_run=False, **kwargs)
        self.assertEqual(rep["status"], "republished", rep)
        pub = load_published(self._ref())
        self.assertNotEqual(pub["version_id"], work["version_id"])
        self.assertIn("「早上好」", pub["texts"].values())
        self.assertIn("「早上好」", (self.ws / "rendered" / "700001.zh.txt").read_text(encoding="utf-8"))
        [log] = (self.ws / "results" / "700001.edits.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertTrue(json.loads(log)["applied"])
        # 重导出后这段不再带标记,版本号跟上。
        [again] = self._export()[0]["works"]
        self.assertEqual(self._seg(again, "「おはよう」"), {**seg, "zh": "「早上好」", "flags": []})

    def test_stale_base_text_is_refused_without_touching_tsv(self):
        [work] = self._export()[0]["works"]
        seg = self._seg(work, "今日はいい天気だ。")
        tsv = self.ws / "results" / "700001.zh.tsv"
        before = tsv.read_text(encoding="utf-8")
        edits = [{"work": KEY, "n": seg["n"], "text": "今天天气很好。", "base_text": "别的底稿", "base_version": "x"}]
        [rep] = pn.import_edits(edits, workspaces_root=self.wsroot, data_root=self.data,
                                entity_store=self.data / "entities", dry_run=False)
        self.assertEqual(rep["status"], "skipped")
        self.assertIn("底稿", rep["reason"])
        self.assertEqual(tsv.read_text(encoding="utf-8"), before)

    def test_tsv_drift_blocks_import(self):
        [work] = self._export()[0]["works"]
        seg = self._seg(work, "今日はいい天気だ。")
        tsv = self.ws / "results" / "700001.zh.tsv"
        tsv.write_text(tsv.read_text(encoding="utf-8").replace("早晨的问候", "清晨的问候"), encoding="utf-8")
        edits = [{"work": KEY, "n": seg["n"], "text": "今天天气很好。", "base_text": seg["zh"], "base_version": work["version_id"]}]
        [rep] = pn.import_edits(edits, workspaces_root=self.wsroot, data_root=self.data,
                                entity_store=self.data / "entities", dry_run=False)
        self.assertEqual(rep["status"], "skipped")
        self.assertIn("TSV 与发布版本有 1 段不一致", rep["reason"])

    def test_works_marking_minors_are_not_exported(self):
        pub = load_published(self._ref())
        for marker in ("JK", "女子中学生", "ショタ", "ロリ", "◯K"):
            for seg in pub["revision"]["segments"]:
                if seg["kind"] == "metadata.tags":
                    seg["source_text"] = f"[{marker}, 日常]"
            with unittest.mock.patch.object(pn, "load_published", return_value=pub):
                batch, notes = self._export()
            self.assertEqual(batch["works"], [], marker)
            self.assertIn("把角色标成未成年人", notes[-1])

    def test_conflicting_workspaces_are_not_exported(self):
        other = self.wsroot / "pixiv-700000"
        ref_dir = other / "store" / "refs" / "pixiv" / "700000"
        ref_dir.mkdir(parents=True)
        (ref_dir / "700001.json").write_text(json.dumps({"version_id": "version_other"}), encoding="utf-8")
        batch, notes = self._export()
        self.assertEqual(batch["works"], [])
        self.assertIn("多个 workspace 指向不同版本", notes[0])


if __name__ == "__main__":
    unittest.main()
