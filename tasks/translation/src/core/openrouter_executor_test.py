#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenRouter 执行器:prompt 构造(注入约束/邻句)+ result 组装(mock,不调网络)。"""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    from . import openrouter_executor as ex, source_identity as si, task_export as te
    from .artifact_schemas import check_result_against_task, validate_artifact
except ImportError:  # core/ 在 sys.path 上
    import openrouter_executor as ex
    import source_identity as si
    import task_export as te
    from artifact_schemas import check_result_against_task, validate_artifact


SRC = Path(__file__).resolve().parent / "testdata" / "fixtures" / "pixiv" / "700001" / "700001.txt"
TR = {"「おはよう」": "「早上好」", "今日はいい天気だ。": "今天天气真好。"}


def _rev():
    return si.build_document_revision("pixiv", SRC)


def _body_ids(rev):
    return [s["segment_id"] for s in rev["segments"] if s["kind"] == "body"]


class BuildMessagesTest(unittest.TestCase):
    def test_constraints_and_neighbors_injected(self):
        seg = {"segment_id": "rev_aa:000001:dead", "source_text": "今日はいい天気だ。"}
        pack = {
            "entities": [{"source": "ユキ", "target": "小雪", "forbidden": ["雪"]}],
            "terminology": [{"source": "魔法", "target": "魔法"}],
            "neighbors": {"rev_aa:000001:dead": {"prev": "「おはよう」", "next": "犬がいた。"}},
        }
        msgs = ex.build_messages(seg, pack)
        system, user = msgs[0]["content"], msgs[1]["content"]
        self.assertIn("ユキ => 小雪", system)
        self.assertIn("禁止译为: 雪", system)
        self.assertIn("魔法 => 魔法", system)
        self.assertIn("今日はいい天気だ。", user)            # 要翻译的段
        self.assertIn("「おはよう」", user)                   # 上文
        self.assertIn("勿翻译", user)                          # 邻句标注为勿翻译

    def test_no_constraints_block_when_empty(self):
        msgs = ex.build_messages({"segment_id": "x", "source_text": "犬がいた。"}, {})
        self.assertNotIn("硬约束", msgs[0]["content"])


class TranslateBundleTest(unittest.TestCase):
    def test_result_is_schema_valid_and_matches_task(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))

        def fake_call(messages):
            # 从 user 消息里取要翻译的段,查表返回中文
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            src = line.split("] ", 1)[1]
            return TR[src]

        result = ex.translate_bundle(bundle, fake_call, completed_at="2026-06-13T00:00:00Z")
        self.assertEqual([], validate_artifact("result", result))
        self.assertEqual("api", result["producer"]["type"])
        self.assertEqual(ex.DEFAULT_MODEL, result["producer"]["model"])
        # task_digest / source_hash 原样回填 → 不触发 stale 防护
        self.assertEqual([], check_result_against_task(bundle["task"], result))
        # 逐段覆盖,译文为中文
        self.assertEqual(len(bundle["segments"]), len(result["candidates"]))
        self.assertIn("早上好", "".join(c["text"] for c in result["candidates"]))


if __name__ == "__main__":
    unittest.main()
