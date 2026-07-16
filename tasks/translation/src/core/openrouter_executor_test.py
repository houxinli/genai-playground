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
    def test_multiline_or_context_marker_response_is_rejected(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        for bad in ("当前段\n混入邻段", "当前段 [tags] 多余内容"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "结构污染"):
                    ex.translate_bundle(bundle, lambda _messages, text=bad: text)

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


class OpenRouterCallRetryTest(unittest.TestCase):
    def _patch_urlopen(self, side_effects):
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            i = calls["n"]; calls["n"] += 1
            eff = side_effects[i]
            if isinstance(eff, Exception):
                raise eff
            import io
            return io.BytesIO(eff.encode("utf-8"))  # 当作可读 body(json.load)

        return fake_urlopen, calls

    def test_retries_on_timeout_then_succeeds(self):
        import urllib.request as ur
        ok = '{"choices":[{"message":{"content":"好"}}]}'
        fake, calls = self._patch_urlopen([TimeoutError("t"), ok])
        orig = ur.urlopen
        ur.urlopen = fake
        try:
            out = ex.openrouter_call([{"role": "user", "content": "x"}], "m", "k",
                                     retries=3, sleep_fn=lambda s: None)
        finally:
            ur.urlopen = orig
        self.assertEqual("好", out)
        self.assertEqual(2, calls["n"])  # 第一次超时、第二次成功

    def test_non_retryable_http_400_raises_immediately(self):
        import urllib.request as ur, urllib.error
        err = urllib.error.HTTPError(ex.OPENROUTER_URL, 400, "bad", {}, None)
        fake, calls = self._patch_urlopen([err, '{"choices":[{"message":{"content":"x"}}]}'])
        orig = ur.urlopen
        ur.urlopen = fake
        try:
            with self.assertRaises(urllib.error.HTTPError):
                ex.openrouter_call([{"role": "user", "content": "x"}], "m", "k",
                                   retries=3, sleep_fn=lambda s: None)
        finally:
            ur.urlopen = orig
        self.assertEqual(1, calls["n"])  # 400 不重试


if __name__ == "__main__":
    unittest.main()
