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


def _mock_executor(bundle):
    """从 bundle.segments 查表返回中文,组装合法 result(走真实 translate_bundle 组装路径)。"""
    src_by_seg = {s["segment_id"]: s["source_text"] for s in bundle["segments"]}

    def call(messages):
        # build_messages 把要翻译的段放进 user 消息;这里直接按 segment 顺序对应不可靠,
        # 改用 translate_bundle 的逐段调用:它每段一次 call,user 含 [翻译这一段] <src>
        line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
        return TR[line.split("] ", 1)[1]]

    try:
        from .openrouter_executor import translate_bundle
    except ImportError:
        from openrouter_executor import translate_bundle
    return translate_bundle(bundle, call, model="mock", completed_at="2026-06-13T00:00:00Z")


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

    def test_unknown_executor_rejected(self):
        with self.assertRaises(ValueError):
            tu.make_translate_fn("nope")


if __name__ == "__main__":
    unittest.main()
