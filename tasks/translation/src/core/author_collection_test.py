#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作者合集:跨 per-work workspace 收集已发布 rendered → 按作者名合成整本(+可选 GDrive 复制)。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import author_collection as ac
except ImportError:
    import author_collection as ac


def _make_work(ws_root: Path, sid: str, *, title: str, rendered=True, provider="pixiv", creator="700000"):
    """造一个已发布 work 的最小 workspace:ref + rendered。"""
    refs = ws_root / f"{provider}-{sid}" / "store" / "refs" / provider / creator
    refs.mkdir(parents=True, exist_ok=True)
    (refs / f"{sid}.json").write_text('{"version_id":"v1"}', encoding="utf-8")
    if rendered:
        rd = ws_root / f"{provider}-{sid}" / "rendered"
        rd.mkdir(parents=True, exist_ok=True)
        for var in ("zh", "bilingual"):
            (rd / f"{sid}.{var}.txt").write_text(
                f"---\nID: {sid}\ntitle: {title}\n---\n\n正文 {sid} {var}\n", encoding="utf-8")


class AuthorCollectionTest(unittest.TestCase):
    def test_builds_named_collection_in_order(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700002", title="第二篇")
            _make_work(ws, "700001", title="第一篇")
            res = ac.build_collection("作者X", "700000", workspaces_root=ws, out_dir=Path(t) / "coll")
            self.assertEqual(["700001", "700002"], res["sids"])  # 按 source_id 升序
            self.assertEqual([], res["missing"])
            self.assertEqual(2, res["chapters"]["zh"])
            self.assertEqual(2, res["chapters"]["bilingual"])
            zh = Path(t) / "coll" / "作者X.zh.txt"
            self.assertTrue(zh.is_file())
            body = zh.read_text(encoding="utf-8")
            self.assertIn("第1章", body)
            self.assertIn("正文 700001", body)
            self.assertLess(body.index("正文 700001"), body.index("正文 700002"))  # 顺序

    def test_gdrive_copy(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="只一篇")
            gd = Path(t) / "gdrive"
            res = ac.build_collection("作者Y", "700000", workspaces_root=ws,
                                      out_dir=Path(t) / "coll", gdrive_dir=gd)
            self.assertTrue((gd / "作者Y.zh.txt").is_file())
            self.assertTrue((gd / "作者Y.bilingual.txt").is_file())
            self.assertEqual(2, len(res["gdrive"]))

    def test_missing_rendered_reported(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="有渲染")
            _make_work(ws, "700002", title="无渲染", rendered=False)  # 发布了但没 rendered
            res = ac.build_collection("作者Z", "700000", workspaces_root=ws, out_dir=Path(t) / "coll")
            self.assertEqual(["700002"], res["missing"])
            self.assertEqual(1, res["chapters"]["zh"])

    def test_no_published_raises(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                ac.build_collection("作者", "999999", workspaces_root=Path(t) / "workspaces",
                                    out_dir=Path(t) / "coll")

    def test_empty_author_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="t")
            with self.assertRaises(ValueError):
                ac.build_collection("  ", "700000", workspaces_root=ws, out_dir=Path(t) / "coll")


if __name__ == "__main__":
    unittest.main()
