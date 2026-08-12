#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作者合集:跨 per-work workspace 收集已发布 rendered → 按作者名合成整本(+可选 GDrive 复制)。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import author_collection as ac
except ImportError:
    import author_collection as ac


def _make_work(ws_root: Path, sid: str, *, title: str, rendered=True, provider="pixiv", creator="700000",
               variants=("zh", "bilingual"), annotate_version="av1"):
    """造一个已发布 work 的最小 workspace:ref + rendered(+ study 时的 annotate ref)。"""
    refs = ws_root / f"{provider}-{sid}" / "store" / "refs" / provider / creator
    refs.mkdir(parents=True, exist_ok=True)
    (refs / f"{sid}.json").write_text('{"version_id":"v1"}', encoding="utf-8")
    if "study" in variants and annotate_version:
        aref = ws_root / f"{provider}-{sid}" / "store" / "refs-annotate" / provider / creator
        aref.mkdir(parents=True, exist_ok=True)
        (aref / f"{sid}.json").write_text(json.dumps({"version_id": annotate_version}), encoding="utf-8")
        rd = ws_root / f"{provider}-{sid}" / "rendered"
        rd.mkdir(parents=True, exist_ok=True)
        (rd / f"{sid}.study.meta.json").write_text(
            json.dumps({"annotate_version_id": annotate_version, "translate_version_id": "v1"}),
            encoding="utf-8")
    if rendered:
        rd = ws_root / f"{provider}-{sid}" / "rendered"
        rd.mkdir(parents=True, exist_ok=True)
        for var in variants:
            (rd / f"{sid}.{var}.txt").write_text(
                f"---\nID: {sid}\ntitle: {title}\n---\n\n正文 {sid} {var}\n", encoding="utf-8")


class AuthorCollectionTest(unittest.TestCase):
    def test_builds_named_collection_in_order(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700002", title="第二篇")
            _make_work(ws, "700001", title="第一篇")
            res = ac.build_collection("作者X", "700000", formats=("txt", "epub"), workspaces_root=ws, out_dir=Path(t) / "coll")
            self.assertEqual(["700001", "700002"], res["sids"])  # 按 source_id 升序
            self.assertEqual([], res["missing"])
            self.assertTrue(res["verification"]["ok"])
            self.assertTrue((Path(t) / "coll" / "collection_manifest.json").is_file())
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
            res = ac.build_collection("作者Y", "700000", formats=("txt", "epub"), workspaces_root=ws,
                                      out_dir=Path(t) / "coll", gdrive_dir=gd)
            self.assertTrue((gd / "作者Y·中文.txt").is_file())
            self.assertTrue((gd / "作者Y·日中对照.txt").is_file())
            self.assertEqual(4, len(res["gdrive"]))  # txt + epub × 2 variant

    def test_default_formats_epub_only(self):
        # 默认 formats=('epub',):只发/同步 epub,整本 txt 不产出。
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="只一篇")
            gd = Path(t) / "gdrive"
            res = ac.build_collection("作者D", "700000", workspaces_root=ws,
                                      out_dir=Path(t) / "coll", gdrive_dir=gd)
            self.assertEqual(2, len(res["gdrive"]))              # 只 zh.epub + bilingual.epub
            self.assertTrue((gd / "作者D·中文.epub").is_file())
            self.assertTrue((gd / "作者D·日中对照.epub").is_file())
            self.assertFalse((gd / "作者D·中文.txt").exists())     # 无整本 txt
            self.assertFalse((Path(t) / "coll" / "作者D_zh.txt").exists())
            self.assertTrue(res["verification"]["ok"])           # epub-only 自校验通过

    def test_formats_txt_only(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="只一篇")
            gd = Path(t) / "gdrive"
            res = ac.build_collection("作者T", "700000", formats=("txt",), workspaces_root=ws,
                                      out_dir=Path(t) / "coll", gdrive_dir=gd)
            self.assertEqual(2, len(res["gdrive"]))
            self.assertTrue((gd / "作者T·中文.txt").is_file())
            self.assertFalse((gd / "作者T·中文.epub").exists())

    def test_missing_rendered_refuses_partial_collection_and_keeps_previous(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="有渲染")
            _make_work(ws, "700002", title="无渲染", rendered=False)  # 发布了但没 rendered
            out = Path(t) / "coll"
            out.mkdir()
            previous = out / "作者Z_zh.txt"
            previous.write_text("旧合集", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "拒绝生成部分合集"):
                ac.build_collection("作者Z", "700000", formats=("txt", "epub"), workspaces_root=ws, out_dir=out)
            self.assertEqual("旧合集", previous.read_text(encoding="utf-8"))

    def test_verify_detects_new_ref_after_build(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            out = Path(t) / "coll"
            _make_work(ws, "700001", title="第一篇")
            ac.build_collection("作者V", "700000", formats=("txt", "epub"), workspaces_root=ws, out_dir=out)
            self.assertTrue(ac.verify_collection(
                "700000", workspaces_root=ws, out_dir=out
            )["ok"])
            _make_work(ws, "700002", title="后来发布")
            verification = ac.verify_collection("700000", workspaces_root=ws, out_dir=out)
            self.assertFalse(verification["ok"])
            self.assertIn("published refs 已变化", "\n".join(verification["errors"]))

    def test_verify_detects_changed_rendered_without_ref_change(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            out = Path(t) / "coll"
            _make_work(ws, "700001", title="第一篇")
            ac.build_collection("作者W", "700000", formats=("txt", "epub"), workspaces_root=ws, out_dir=out)
            rendered = ws / "pixiv-700001" / "rendered" / "700001.zh.txt"
            rendered.write_text(rendered.read_text(encoding="utf-8") + "已重渲染\n", encoding="utf-8")
            verification = ac.verify_collection("700000", workspaces_root=ws, out_dir=out)
            self.assertFalse(verification["ok"])
            self.assertIn("合集需要重建", "\n".join(verification["errors"]))

    def test_verify_detects_modified_collection_output(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            out = Path(t) / "coll"
            _make_work(ws, "700001", title="第一篇")
            ac.build_collection("作者Q", "700000", formats=("txt", "epub"), workspaces_root=ws, out_dir=out)
            merged = out / "作者Q_zh.txt"
            merged.write_text(merged.read_text(encoding="utf-8") + "意外修改\n", encoding="utf-8")
            verification = ac.verify_collection("700000", workspaces_root=ws, out_dir=out)
            self.assertFalse(verification["ok"])
            self.assertIn("合集输出被修改", "\n".join(verification["errors"]))

    def test_no_published_raises(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                ac.build_collection("作者", "999999", formats=("txt", "epub"), workspaces_root=Path(t) / "workspaces",
                                    out_dir=Path(t) / "coll")

    def test_empty_author_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="t")
            with self.assertRaises(ValueError):
                ac.build_collection("  ", "700000", formats=("txt", "epub"), workspaces_root=ws, out_dir=Path(t) / "coll")

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
            res = ac.build_collection("作者P", "700000", formats=("txt", "epub"), workspaces_root=ws, out_dir=Path(t) / "coll")
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
                ac.build_collection("作者", "700000", formats=("txt", "epub"), workspaces_root=ws, out_dir=ws)
            # out_dir 指向含子目录的已有目录(如 per-work workspace)→ 拒绝
            with self.assertRaises(ValueError):
                ac.build_collection("作者", "700000", formats=("txt", "epub"), workspaces_root=ws,
                                    out_dir=ws / "pixiv-700001")
            # 重建合法的旧合集目录(只含 txt/epub)→ 允许
            res = ac.build_collection("作者", "700000", formats=("txt", "epub"), workspaces_root=ws,
                                      out_dir=Path(t) / "coll")
            res2 = ac.build_collection("作者", "700000", formats=("txt", "epub"), workspaces_root=ws,
                                       out_dir=Path(t) / "coll")
            self.assertEqual(res["sids"], res2["sids"])

    def test_epub_built_with_explicit_toc(self):
        import zipfile
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="第一篇")
            _make_work(ws, "700002", title="第二篇")
            gd = Path(t) / "gdrive"
            res = ac.build_collection("作者E", "700000", formats=("txt", "epub"), workspaces_root=ws,
                                      out_dir=Path(t) / "coll", gdrive_dir=gd)
            self.assertEqual({"zh": 2, "bilingual": 2}, res["epub_chapters"])
            epub = Path(t) / "coll" / "作者E_zh.epub"
            self.assertTrue(epub.is_file())
            with zipfile.ZipFile(epub) as z:
                nav = z.read("OEBPS/nav.xhtml").decode("utf-8")
                self.assertIn("第1章 第一篇", nav)
                self.assertIn("第2章 第二篇", nav)
            self.assertTrue((gd / "作者E·中文.epub").is_file())
            self.assertTrue((gd / "作者E·日中对照.epub").is_file())

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
            ac.build_collection("作者F", "700000", formats=("txt", "epub"), workspaces_root=ws,
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
            ac.build_collection("作者H", "700000", formats=("txt", "epub"), workspaces_root=ws,
                                out_dir=Path(t) / "coll", furigana=True)
            bil = (Path(t) / "coll" / "作者H_bilingual.txt").read_text(encoding="utf-8")
            self.assertIn("パイズリ / 乳交", bil)   # tags 行原样,中文侧未被日文读音污染
            self.assertNotIn("乳(ちち)交", bil)
            self.assertNotIn("巨乳(きょにゅう) / 巨乳(きょにゅう)", bil)

    def test_no_furigana_keeps_source_raw(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            self._make_ja_work(ws, "700001")
            ac.build_collection("作者G", "700000", formats=("txt", "epub"), workspaces_root=ws,
                                out_dir=Path(t) / "coll", furigana=False)
            bil = (Path(t) / "coll" / "作者G_bilingual.txt").read_text(encoding="utf-8")
            self.assertIn("今日は晴れです", bil)  # 源文保持原始日文,无注音


class StudyVariantTest(unittest.TestCase):
    """陪读(study)整本:注解线渲染的 `<sid>.study.txt` 与 zh/bilingual 同构,可作为一个 variant 发布。"""

    def test_builds_zh_and_study_collection(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            out = Path(t) / "coll"
            gd = Path(t) / "gdrive"
            for sid in ("700001", "700002"):
                _make_work(ws, sid, title=f"第{sid}篇", variants=("zh", "bilingual", "study"))
            res = ac.build_collection("作者S", "700000", formats=("txt", "epub"), variants=("zh", "study"),
                                      workspaces_root=ws, out_dir=out, gdrive_dir=gd)
            self.assertTrue(res["verification"]["ok"])
            self.assertEqual(2, res["chapters"]["study"])
            self.assertEqual(2, res["epub_chapters"]["study"])
            self.assertTrue((out / "作者S_study.epub").is_file())
            self.assertTrue((gd / "作者S·陪读.epub").is_file())     # GDrive 上是人类可读名
            self.assertFalse((out / "作者S_bilingual.epub").is_file())  # 没选的 variant 不产出
            manifest = json.loads((out / "collection_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(["zh", "study"], manifest["variants"])

    def test_verify_uses_manifest_variants(self):
        # 合集发的是 zh+study,verify 就只核对这两个;不能因为缺 bilingual 而误报。
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            out = Path(t) / "coll"
            _make_work(ws, "700001", title="只一篇", variants=("zh", "study"))
            ac.build_collection("作者T", "700000", variants=("zh", "study"),
                                workspaces_root=ws, out_dir=out)
            self.assertTrue(ac.verify_collection("700000", workspaces_root=ws, out_dir=out)["ok"])
            study = ws / "pixiv-700001" / "rendered" / "700001.study.txt"
            study.write_text(study.read_text(encoding="utf-8") + "已重渲染\n", encoding="utf-8")
            verification = ac.verify_collection("700000", workspaces_root=ws, out_dir=out)
            self.assertFalse(verification["ok"])
            self.assertIn("700001.study.txt 已变化", "\n".join(verification["errors"]))

    def test_missing_study_refuses_partial_collection(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="有陪读", variants=("zh", "study"))
            _make_work(ws, "700002", title="没陪读", variants=("zh",))
            with self.assertRaises(ValueError) as ctx:
                ac.build_collection("作者U", "700000", variants=("zh", "study"),
                                    workspaces_root=ws, out_dir=Path(t) / "coll")
            self.assertIn("700002.study", str(ctx.exception))

    def test_unknown_variant_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="只一篇")
            with self.assertRaises(ValueError):
                ac.build_collection("作者Z", "700000", variants=("zh", "annotated"),
                                    workspaces_root=ws, out_dir=Path(t) / "coll")

    def test_legacy_manifest_without_variants_still_verifies(self):
        # 旧 manifest 没有 variants 字段 → 按默认 zh+bilingual 核对,不报错。
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            out = Path(t) / "coll"
            _make_work(ws, "700001", title="只一篇")
            ac.build_collection("作者L", "700000", workspaces_root=ws, out_dir=out)
            manifest_path = out / "collection_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.pop("variants")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(ac.verify_collection("700000", workspaces_root=ws, out_dir=out)["ok"])


if __name__ == "__main__":
    unittest.main()


class StudyAnnotateFreshnessTest(unittest.TestCase):
    """study 由「注解版本 + 当前翻译版本」渲染 → 只记翻译版本判不出新鲜度(Codex #194 P2)。"""

    def test_manifest_records_annotate_version(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"; out = Path(t) / "coll"
            _make_work(ws, "700001", title="一篇", variants=("zh", "study"))
            ac.build_collection("作者N", "700000", variants=("zh", "study"), workspaces_root=ws, out_dir=out)
            m = json.loads((out / "collection_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("av1", m["documents"][0]["annotate_version_id"])

    def test_annotate_version_change_requires_rebuild(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"; out = Path(t) / "coll"
            _make_work(ws, "700001", title="一篇", variants=("zh", "study"))
            ac.build_collection("作者O", "700000", variants=("zh", "study"), workspaces_root=ws, out_dir=out)
            self.assertTrue(ac.verify_collection("700000", workspaces_root=ws, out_dir=out)["ok"])
            # 注解推进了但 study.txt 没重渲染:旧判据全绿,新判据必须报
            aref = ws / "pixiv-700001" / "store" / "refs-annotate" / "pixiv" / "700000" / "700001.json"
            aref.write_text(json.dumps({"version_id": "av2"}), encoding="utf-8")
            v = ac.verify_collection("700000", workspaces_root=ws, out_dir=out)
            self.assertFalse(v["ok"])
            self.assertIn("annotate 版本已变化", "\n".join(v["errors"]))

    def test_missing_annotate_ref_refuses_partial_collection(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="有注解", variants=("zh", "study"))
            _make_work(ws, "700002", title="没注解", variants=("zh", "study"), annotate_version=None)
            with self.assertRaises(ValueError) as ctx:
                ac.build_collection("作者P", "700000", variants=("zh", "study"),
                                    workspaces_root=ws, out_dir=Path(t) / "coll")
            self.assertIn("700002.annotate-ref", str(ctx.exception))


class StudyWorkspaceSelectionTest(unittest.TestCase):
    """同一篇存在于两个 workspace、rendered 打平时,应选有 annotate ref 的那个。"""

    def test_workspace_with_annotate_ref_wins_tie(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            # 两个 workspace 都有 zh+study rendered,只有后者有 annotate ref
            _make_work(ws, "700001", title="无注解", variants=("zh", "study"), annotate_version=None)
            second = ws / "pixiv-alt"
            (second / "store" / "refs" / "pixiv" / "700000").mkdir(parents=True)
            (second / "store" / "refs" / "pixiv" / "700000" / "700001.json").write_text(
                '{"version_id":"v1"}', encoding="utf-8")
            aref = second / "store" / "refs-annotate" / "pixiv" / "700000"
            aref.mkdir(parents=True)
            (aref / "700001.json").write_text(json.dumps({"version_id": "av9"}), encoding="utf-8")
            rd = second / "rendered"; rd.mkdir()
            for var in ("zh", "study"):
                (rd / f"700001.{var}.txt").write_text(
                    f"---\nID: 700001\ntitle: 有注解\n---\n\n正文 {var}\n", encoding="utf-8")
            (rd / "700001.study.meta.json").write_text(
                json.dumps({"annotate_version_id": "av9", "translate_version_id": "v1"}), encoding="utf-8")
            out = Path(t) / "coll"
            res = ac.build_collection("作者W", "700000", variants=("zh", "study"),
                                      workspaces_root=ws, out_dir=out)
            self.assertTrue(res["verification"]["ok"])
            m = json.loads((out / "collection_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("av9", m["documents"][0]["annotate_version_id"])


class ConflictingAnnotateVersionTest(unittest.TestCase):
    def test_different_annotate_versions_are_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="旧注解", variants=("zh", "study"), annotate_version="av1")
            second = ws / "pixiv-dup"
            for sub, body in (("store/refs/pixiv/700000", '{"version_id":"v1"}'),
                              ("store/refs-annotate/pixiv/700000", '{"version_id":"av2"}')):
                d = second / sub; d.mkdir(parents=True)
                (d / "700001.json").write_text(body, encoding="utf-8")
            rd = second / "rendered"; rd.mkdir()
            for var in ("zh", "study"):
                (rd / f"700001.{var}.txt").write_text(
                    f"---\nID: 700001\ntitle: 新注解\n---\n\n正文 {var}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "不同注解版本"):
                ac.build_collection("作者X2", "700000", variants=("zh", "study"),
                                    workspaces_root=ws, out_dir=Path(t) / "coll")


class StudyProvenanceTest(unittest.TestCase):
    """只记 ref 版本号证明不了 study.txt 由该版本渲染:渲染产物自带 provenance,合集据此核对。"""

    def test_stale_study_render_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="一篇", variants=("zh", "study"), annotate_version="av1")
            # 注解推进到 av2,但 study.txt 渲染失败 → 旧文件与旧 provenance 还在
            aref = ws / "pixiv-700001" / "store" / "refs-annotate" / "pixiv" / "700000" / "700001.json"
            aref.write_text(json.dumps({"version_id": "av2"}), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                ac.build_collection("作者Y2", "700000", variants=("zh", "study"),
                                    workspaces_root=ws, out_dir=Path(t) / "coll")
            self.assertIn("study-stale", str(ctx.exception))

    def test_missing_provenance_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "workspaces"
            _make_work(ws, "700001", title="一篇", variants=("zh", "study"), annotate_version="av1")
            (ws / "pixiv-700001" / "rendered" / "700001.study.meta.json").unlink()
            with self.assertRaises(ValueError) as ctx:
                ac.build_collection("作者Z2", "700000", variants=("zh", "study"),
                                    workspaces_root=ws, out_dir=Path(t) / "coll")
            self.assertIn("study-provenance", str(ctx.exception))
