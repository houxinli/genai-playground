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
            zh = Path(t) / "coll" / "作者X_zh.txt"
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
            self.assertTrue((gd / "作者Y_zh.txt").is_file())
            self.assertTrue((gd / "作者Y_bilingual.txt").is_file())
            self.assertEqual(4, len(res["gdrive"]))  # txt + epub × 2 variant

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

    def test_per_creator_workspace_layout(self):
        # 迁移布局:一个 creator 一个 workspace,rendered 集中在 <provider>-<creator>/rendered/
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            cws = ws / "pixiv-700000"
            refs = cws / "store" / "refs" / "pixiv" / "700000"
            refs.mkdir(parents=True)
            rd = cws / "rendered"; rd.mkdir()
            for sid, title in [("700001", "甲"), ("700002", "乙")]:
                (refs / f"{sid}.json").write_text('{"version_id":"v1"}', encoding="utf-8")
                for var in ("zh", "bilingual"):
                    (rd / f"{sid}.{var}.txt").write_text(
                        f"---\nID: {sid}\ntitle: {title}\n---\n\n正文 {sid} {var}\n", encoding="utf-8")
            res = ac.build_collection("作者P", "700000", workspaces_root=ws, out_dir=Path(t) / "coll")
            self.assertEqual(["700001", "700002"], res["sids"])
            self.assertEqual([], res["missing"])
            self.assertEqual(2, res["chapters"]["zh"])
            self.assertTrue((Path(t) / "coll" / "作者P_zh.epub").is_file())

    def test_out_dir_guard_rejects_workspaces_root_and_dirty_dirs(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="t")
            # out_dir == workspaces_root → 拒绝(会清掉全部 per-work 产物)
            with self.assertRaises(ValueError):
                ac.build_collection("作者", "700000", workspaces_root=ws, out_dir=ws)
            # out_dir 指向含子目录的已有目录(如 per-work workspace)→ 拒绝
            with self.assertRaises(ValueError):
                ac.build_collection("作者", "700000", workspaces_root=ws,
                                    out_dir=ws / "pixiv-700001")
            # 重建合法的旧合集目录(只含 txt/epub)→ 允许
            res = ac.build_collection("作者", "700000", workspaces_root=ws,
                                      out_dir=Path(t) / "coll")
            res2 = ac.build_collection("作者", "700000", workspaces_root=ws,
                                       out_dir=Path(t) / "coll")
            self.assertEqual(res["sids"], res2["sids"])

    def test_epub_built_with_explicit_toc(self):
        import zipfile
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="第一篇")
            _make_work(ws, "700002", title="第二篇")
            gd = Path(t) / "gdrive"
            res = ac.build_collection("作者E", "700000", workspaces_root=ws,
                                      out_dir=Path(t) / "coll", gdrive_dir=gd)
            self.assertEqual({"zh": 2, "bilingual": 2}, res["epub_chapters"])
            epub = Path(t) / "coll" / "作者E_zh.epub"
            self.assertTrue(epub.is_file())
            with zipfile.ZipFile(epub) as z:
                nav = z.read("OEBPS/nav.xhtml").decode("utf-8")
                self.assertIn("第1章 第一篇", nav)
                self.assertIn("第2章 第二篇", nav)
            self.assertTrue((gd / "作者E_zh.epub").is_file())
            self.assertTrue((gd / "作者E_bilingual.epub").is_file())

    def _make_ja_work(self, ws_root: Path, sid: str, provider="pixiv", creator="700000"):
        refs = ws_root / f"{provider}-{sid}" / "store" / "refs" / provider / creator
        refs.mkdir(parents=True, exist_ok=True)
        (refs / f"{sid}.json").write_text('{"version_id":"v1"}', encoding="utf-8")
        rd = ws_root / f"{provider}-{sid}" / "rendered"
        rd.mkdir(parents=True, exist_ok=True)
        # bilingual:front-matter 里有中日混排 tags 行(`源词 / 中文` 同行);body 为 源文/译文 交替对。
        (rd / f"{sid}.bilingual.txt").write_text(
            "---\nID: {0}\ntitle: 今日は\n"
            "tags: [パイズリ / 乳交, 巨乳 / 巨乳]\n"
            "---\n\n今日は晴れです\n今天是晴天\n\n巨乳が好きです\n喜欢巨乳\n".format(sid), encoding="utf-8")
        (rd / f"{sid}.zh.txt").write_text(
            "---\nID: {0}\ntitle: 晴天\n---\n\n今天是晴天\n".format(sid), encoding="utf-8")

    def test_furigana_annotates_source_lines_only(self):
        try:
            import pykakasi  # noqa: F401
        except Exception:
            self.skipTest("pykakasi 未安装")
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            self._make_ja_work(ws, "700001")
            ac.build_collection("作者F", "700000", workspaces_root=ws,
                                out_dir=Path(t) / "coll", furigana=True)
            bil = (Path(t) / "coll" / "作者F_bilingual.txt").read_text(encoding="utf-8")
            self.assertIn("(", bil)              # body 源文汉字被注音
            self.assertIn("今天是晴天", bil)      # 中文译文行原样
            self.assertIn("喜欢巨乳", bil)        # 中文译文行原样(不被注音)
            self.assertNotIn("今天(", bil)        # 中文译文行没被误注音
            self.assertNotIn("喜欢(", bil)

    def test_furigana_does_not_corrupt_mixed_frontmatter_tags(self):
        """回归:中日混排 tags 行(`パイズリ / 乳交`)不得把中文 乳交 注成 乳(ちち)交(こう)。
        根因是曾按"整行含假名"判源文,把 front-matter 混排行整行注音。现跳过 front-matter。"""
        try:
            import pykakasi  # noqa: F401
        except Exception:
            self.skipTest("pykakasi 未安装")
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            self._make_ja_work(ws, "700001")
            ac.build_collection("作者H", "700000", workspaces_root=ws,
                                out_dir=Path(t) / "coll", furigana=True)
            bil = (Path(t) / "coll" / "作者H_bilingual.txt").read_text(encoding="utf-8")
            self.assertIn("パイズリ / 乳交", bil)   # tags 行原样,中文侧未被日文读音污染
            self.assertNotIn("乳(ちち)交", bil)
            self.assertNotIn("巨乳(きょにゅう) / 巨乳(きょにゅう)", bil)

    def test_no_furigana_keeps_source_raw(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            self._make_ja_work(ws, "700001")
            ac.build_collection("作者G", "700000", workspaces_root=ws,
                                out_dir=Path(t) / "coll", furigana=False)
            bil = (Path(t) / "coll" / "作者G_bilingual.txt").read_text(encoding="utf-8")
            self.assertIn("今日は晴れです", bil)  # 源文保持原始日文,无注音


if __name__ == "__main__":
    unittest.main()
