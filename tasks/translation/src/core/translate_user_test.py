#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translate-user 通用编排:mock executor 跑 fixture 全链(翻译→发布→渲染→合并),不调网络。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import translate_user as tu
    from .artifact_store import ArtifactStore
except ImportError:  # core/ 在 sys.path 上
    import translate_user as tu
    from artifact_store import ArtifactStore


TESTDATA = Path(__file__).resolve().parent / "testdata"
SRC = TESTDATA / "fixtures" / "pixiv" / "700001" / "700001.txt"
BILINGUAL = TESTDATA / "golden" / "pixiv-700001.render.bilingual.txt"  # 现有译文作 incumbent
TR = {
    "朝の挨拶": "早晨的问候", "テスト用の短い文章です。": "用于测试的简短文章。",
    "[テスト, 日常]": "[テスト / 测试, 日常 / 日常]", "「おはよう」": "「早上好」",
    "今日はいい天気だ。": "今天天气真好。",
}


def _mk(tr):
    """按译表 tr 造 mock executor;走真实 translate_bundle 组装路径(逐段一 call)。"""
    def executor(bundle):
        def call(messages):
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            return tr[line.split("] ", 1)[1]]
        try:
            from .openrouter_executor import translate_bundle
        except ImportError:
            from openrouter_executor import translate_bundle
        return translate_bundle(bundle, call, model="mock", completed_at="2026-06-13T00:00:00Z")
    return executor


_mock_executor = _mk(TR)


class TranslateUserTest(unittest.TestCase):
    def test_one_command_translates_publishes_renders_merges(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir()
            shutil.copy(BILINGUAL, bil_dir / "700001.txt")  # 现有译文作 incumbent(元数据段可解析)
            store_root = tmp / "store"; render_dir = tmp / "out"
            m = tu.translate_user("pixiv", src_dir, store_root, render_dir, _mock_executor, bilingual_dir=bil_dir)
            self.assertEqual(1, m["summary"]["published"])
            self.assertEqual(0, m["summary"]["errors"])
            doc = m["documents"][0]["document_id"]
            store = ArtifactStore(store_root)
            # 翻译后:store 有新候选 + 版本 + 发布 ref;渲染产物 + 合并整本
            self.assertTrue(store.list_shard("candidate", doc))
            self.assertIsNotNone(store.current_ref(doc))
            zh = (render_dir / "700001.zh.txt").read_text(encoding="utf-8")
            self.assertIn("早上好", zh)            # 译文进了渲染
            book = (render_dir / f"{src_dir.name}.zh.txt").read_text(encoding="utf-8")
            self.assertIn("第1章", book)            # 合并整本
            self.assertIn("早上好", book)

    def test_limit_bounds_documents(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "auth"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            shutil.copy(SRC, src_dir / "700002.txt")  # 第二篇(同源,document_id 同 → 仅测 limit 计数)
            m = tu.translate_user("pixiv", src_dir, tmp / "s", None, _mock_executor, limit=1)
            self.assertEqual(1, m["summary"]["total"])

    def test_fresh_author_publishes_with_tags_fallback(self):
        # 无 legacy:title/caption/body 译文过 QA;tags「原词/中文」含假名 QA fail → 仅 tags 兜底 → 发布
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "auth"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            m = tu.translate_user("pixiv", src_dir, tmp / "s", tmp / "out", _mock_executor)
            self.assertEqual(1, m["summary"]["published"])

    def test_failing_title_stays_unresolved_not_force_published(self):
        # Codex #107:title 返回未翻日文(same_as_source fail)且无 incumbent → 不得借 tags 兜底强发
        bad = {**TR, "朝の挨拶": "朝の挨拶"}  # 标题原样照抄 = QA fail
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "auth"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            m = tu.translate_user("pixiv", src_dir, tmp / "s", tmp / "out", _mk(bad))
            self.assertEqual(0, m["summary"]["published"])
            self.assertEqual("unresolved", m["documents"][0]["status"])

    def test_uses_this_run_candidate_not_stale_shard(self):
        # Codex #107:store 已有上一轮非 legacy 候选时,本轮发布/渲染必须用本轮 executor 产物
        old = {**TR, "「おはよう」": "旧甲", "今日はいい天気だ。": "旧乙"}
        new = {**TR, "「おはよう」": "新甲", "今日はいい天気だ。": "新乙"}
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "auth"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            store_root = tmp / "s"; render_dir = tmp / "out"
            tu.translate_user("pixiv", src_dir, store_root, render_dir, _mk(old))   # 第一轮:旧译入库
            tu.translate_user("pixiv", src_dir, store_root, render_dir, _mk(new))   # 第二轮:新译
            zh = (render_dir / "700001.zh.txt").read_text(encoding="utf-8")
            self.assertIn("新甲", zh)
            self.assertNotIn("旧甲", zh)   # 不能渲染上一轮的陈旧候选

    def test_prepare_then_agent_translate_then_finish(self):
        # agent 路线:prepare 导出 bundle → (执行器翻译写 result) → finish 发布渲染合并
        import json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir()
            shutil.copy(BILINGUAL, bil_dir / "700001.txt")
            store_root = tmp / "store"; jobs_dir = tmp / "jobs"; results_dir = tmp / "results"
            render_dir = tmp / "out"; results_dir.mkdir()

            prep = tu.prepare_user("pixiv", src_dir, store_root, jobs_dir, bilingual_dir=bil_dir)
            self.assertEqual(1, len(prep["jobs"]))
            # 模拟执行器:读 job(=bundle)→ 翻译 → 写 result
            for j in prep["jobs"]:
                bundle = json.loads(Path(j["job"]).read_text(encoding="utf-8"))
                result = _mock_executor(bundle)
                (results_dir / f"{j['source_id']}.result.json").write_text(
                    json.dumps(result, ensure_ascii=False), encoding="utf-8")

            m = tu.finish_user("pixiv", src_dir, store_root, render_dir, results_dir, bilingual_dir=bil_dir)
            self.assertEqual(1, m["summary"]["published"])
            book = (render_dir / f"{src_dir.name}.zh.txt").read_text(encoding="utf-8")
            self.assertIn("早上好", book)

    def test_verify_true_after_finish_false_on_prepare_only(self):
        # #129:verify 独立核对落盘——finish 后 ok;只 prepare(Cursor 那种)→ ok=False(没 import/发布/渲染)
        import json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir(); shutil.copy(BILINGUAL, bil_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()

            prep = tu.prepare_user("pixiv", src_dir, store, jobs, bilingual_dir=bil_dir)
            # 只 prepare:还没翻、没 finish → verify 必须 False(这正是 Cursor 谎报的状态)
            v0 = tu.verify_user("pixiv", src_dir, store, render, results)
            self.assertFalse(v0["ok"])
            self.assertFalse(v0["documents"][0]["published"])  # 没 finish → 没发布
            self.assertFalse(v0["documents"][0]["rendered"])   # 没渲染产物
            self.assertFalse(v0["documents"][0]["result_json"])  # 没写 result(Cursor 谎报的核心)

            # 真翻 + finish 后 → verify True
            for j in prep["jobs"]:
                bundle = json.loads(Path(j["job"]).read_text(encoding="utf-8"))
                (results / f"{j['source_id']}.result.json").write_text(
                    json.dumps(_mock_executor(bundle), ensure_ascii=False), encoding="utf-8")
            tu.finish_user("pixiv", src_dir, store, render, results, bilingual_dir=bil_dir)
            v1 = tu.verify_user("pixiv", src_dir, store, render, results)
            self.assertTrue(v1["ok"], v1["documents"])
            self.assertTrue(v1["documents"][0]["published"])
            self.assertTrue(v1["documents"][0]["version_matches_source"])
            self.assertTrue(v1["documents"][0]["rendered"])

            # Codex #130:源改了(新 revision)但旧 ref 仍在 → verify 不能算通过
            (src_dir / "700001.txt").write_text(
                (src_dir / "700001.txt").read_text(encoding="utf-8") + "\n新增一段正文。\n", encoding="utf-8")
            v2 = tu.verify_user("pixiv", src_dir, store, render, results)
            self.assertFalse(v2["ok"])
            self.assertFalse(v2["documents"][0]["version_matches_source"])  # 旧版本不对应新源

    def test_finish_auto_assembles_from_tsv(self):
        # 紧凑路径:只写 <id>.zh.tsv(无 result.json)→ finish 自动组装并发布(少一个 assemble 步骤)
        import json as _json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir(); shutil.copy(BILINGUAL, bil_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()
            prep = tu.prepare_user("pixiv", src_dir, store, jobs, bilingual_dir=bil_dir)
            j = prep["jobs"][0]; sid = j["source_id"]
            bundle = _json.loads(Path(j["job"]).read_text(encoding="utf-8"))
            lines = [f"{i}\t{TR[seg['source_text']]}" for i, seg in enumerate(bundle["segments"])]
            (results / f"{sid}.zh.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")  # 只写 tsv

            m = tu.finish_user("pixiv", src_dir, store, render, results, bilingual_dir=bil_dir)
            self.assertEqual(1, m["summary"]["published"])
            self.assertTrue((results / f"{sid}.result.json").is_file())  # finish 自动组装出 result.json

    def test_finish_respects_limit(self):
        # Codex #122:finish 也要按 limit 切片,不扫 limit 之外的文件(否则报无关 no_result)
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "a"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            shutil.copy(SRC, src_dir / "700002.txt")
            m = tu.finish_user("pixiv", src_dir, tmp / "s", tmp / "out", tmp / "empty", limit=1)
            self.assertEqual(1, m["summary"]["total"])  # 只扫前 1 篇

    def test_finish_without_result_is_no_result(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "a"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            m = tu.finish_user("pixiv", src_dir, tmp / "s", tmp / "out", tmp / "empty_results")
            self.assertEqual("no_result", m["documents"][0]["status"])

    def test_unknown_executor_rejected(self):
        with self.assertRaises(ValueError):
            tu.make_translate_fn("nope")


if __name__ == "__main__":
    unittest.main()
