#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenRouter 执行器:prompt 构造(注入约束/邻句)+ result 组装(mock,不调网络)。"""

from __future__ import annotations

import unittest
import unittest.mock
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

    def test_only_canonical_document_target_is_injected(self):
        msgs = ex.build_messages(
            {"segment_id": "x", "source_text": "みのりが笑った。"},
            {},
            {"みのり": "实里"},
        )
        self.assertIn("みのり => 实里", msgs[0]["content"])
        self.assertNotIn("美乃里", msgs[0]["content"])


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
            return f"T\t{TR[src]}"

        result = ex.translate_bundle(bundle, fake_call, completed_at="2026-06-13T00:00:00Z")
        self.assertEqual([], validate_artifact("result", result))
        self.assertEqual("api", result["producer"]["type"])
        self.assertEqual(ex.DEFAULT_MODEL, result["producer"]["model"])
        # task_digest / source_hash 原样回填 → 不触发 stale 防护
        self.assertEqual([], check_result_against_task(bundle["task"], result))
        # 逐段覆盖,译文为中文
        self.assertEqual(len(bundle["segments"]), len(result["candidates"]))
        self.assertIn("早上好", "".join(c["text"] for c in result["candidates"]))

    def test_first_name_translation_is_carried_and_later_variant_is_normalized(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "みのりが来た。"
        bundle["segments"][1]["source_text"] = "みのりが笑った。"
        systems = []

        def fake_call(messages):
            systems.append(messages[0]["content"])
            if len(systems) == 1:
                return "T\t实里来了。\nE\tみのり\t实里"
            return "T\t美乃里笑了。\nE\tみのり\t美乃里"

        result = ex.translate_bundle(bundle, fake_call, completed_at="2026-06-13T00:00:00Z")
        self.assertEqual("实里来了。", result["candidates"][0]["text"])
        self.assertEqual("实里笑了。", result["candidates"][1]["text"])
        self.assertNotIn("みのり =>", systems[0])
        self.assertIn("みのり => 实里", systems[1])
        self.assertNotIn("美乃里", systems[1])
        self.assertEqual(1, len(result["findings"]))
        self.assertEqual("entity_first_use", result["findings"][0]["code"])

    def test_approved_context_target_wins_without_becoming_document_variant(self):
        rev = _rev()
        body_ids = _body_ids(rev)
        bundle = te.export_job(rev, body_ids, entities=[{"source": "みのり", "target": "实里"}])
        bundle["segments"][0]["source_text"] = "みのりが来た。"

        result = ex.translate_bundle(
            bundle,
            lambda _messages: "T\t美乃里来了。\nE\tみのり\t美乃里",
            completed_at="2026-06-13T00:00:00Z",
        )
        self.assertEqual("实里来了。", result["candidates"][0]["text"])
        self.assertEqual([], result["findings"])


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


class SegmentQualityGateTest(unittest.TestCase):
    """内联复检:执行器自己发现「只译了这段吗」，用退档重试就地修，而不是留给 finish/人工。"""

    def test_neighbor_leak_retried_then_fixed_without_prev_context(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        calls = []

        def fake_call(messages):
            user = messages[-1]["content"] if messages[-1]["role"] == "user" else messages[1]["content"]
            calls.append(user)
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            src = line.split("] ", 1)[1]
            # 只要 prompt 里还有 [上文]，就把上文也译进来(deepseek 的实际行为)
            if "[上文" in messages[1]["content"]:
                return f"T\t「早上好」{TR[src]}"
            return f"T\t{TR[src]}"

        result = ex.translate_bundle(bundle, fake_call)
        texts = [c["text"] for c in result["candidates"]]
        self.assertIn("今天天气真好。", texts)
        self.assertNotIn("「早上好」今天天气真好。", texts)   # 窜入的那版没有被发布
        self.assertTrue(any("[上文" not in c for c in calls))  # 退到了不给上文那一档
        self.assertEqual([], [f for f in result["findings"] if f.get("code") == "segment_quality"])

    def test_unfixable_quality_problem_is_published_with_finding(self):
        # 三档都修不好的质量问题不阻断发布,只记 finding——阻断会让整篇没产物。
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))

        def always_overlong(messages):
            return "T\t" + "很长的译文" * 20

        result = ex.translate_bundle(bundle, always_overlong)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("segment_quality", codes)
        self.assertEqual(len(bundle["segments"]), len(result["candidates"]))

    def test_protocol_residue_on_one_line_is_not_published(self):
        # deepseek 把 T 行和 E 行挤在同一物理行:整条协议曾被原样当成译文发布。
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with self.assertRaisesRegex(ValueError, "结构污染"):
            ex.translate_bundle(bundle, lambda _m: "T\t译文\tE\tおにーさん\t哥哥")

    def test_second_t_record_is_not_glued_into_translation(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        seen = []

        def two_t_lines(messages):
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            src = line.split("] ", 1)[1]
            seen.append(src)
            if len(seen) <= 1:
                return f"T\t上一段的译文\nT\t{TR[src]}"   # 两条 T 记录,不是折行
            return f"T\t{TR[src]}"

        result = ex.translate_bundle(bundle, two_t_lines)
        for c in result["candidates"]:
            self.assertNotIn("T\t", c["text"])

    def test_quality_errors_flags(self):
        self.assertEqual([], ex.segment_quality_errors("今日はいい天気だ。", "今天天气真好。", "「早上好」"))
        self.assertIn("overlong_vs_source", ex.segment_quality_errors("はい♡", "非常长的译文" * 10))
        self.assertIn(
            "neighbor_overlap",
            ex.segment_quality_errors("今日はいい天気だ。", "「早上好」今天天气真好，很不错。", "「早上好」"),
        )


class CheckpointResumeTest(unittest.TestCase):
    """长篇一次限流不该丢掉已译段落:断点即产物格式,重跑自动续上。"""

    def test_writes_checkpoint_and_resumes_without_recalling(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))

        def ok_call(messages):
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            return f"T\t{TR[line.split('] ', 1)[1]]}"

        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            first = ex.translate_bundle(bundle, ok_call, checkpoint_path=cp)
            rows = cp.read_text(encoding="utf-8").rstrip("\n").split("\n")
            self.assertEqual(len(bundle["segments"]), len(rows))

            def boom(_messages):
                raise AssertionError("续跑不应重新调用模型")

            second = ex.translate_bundle(bundle, boom, checkpoint_path=cp)
            self.assertEqual([c["text"] for c in first["candidates"]],
                             [c["text"] for c in second["candidates"]])

    def test_partial_checkpoint_only_translates_remaining(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        calls = []

        def counting(messages):
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            src = line.split("] ", 1)[1]
            calls.append(src)
            return f"T\t{TR[src]}"

        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            seg0 = bundle["segments"][0]
            cp.write_text(f"0\t{seg0['source_text'][:12]}\t已译好的第一段\n", encoding="utf-8")
            result = ex.translate_bundle(bundle, counting, checkpoint_path=cp)
            self.assertEqual("已译好的第一段", result["candidates"][0]["text"])
            self.assertEqual(len(bundle["segments"]) - 1, len(calls))

    def test_checkpoint_from_other_source_is_discarded(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))

        def ok_call(messages):
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            return f"T\t{TR[line.split('] ', 1)[1]]}"

        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            cp.write_text("0\t完全不同的源文\t别的篇的译文\n", encoding="utf-8")  # src_echo 对不上
            result = ex.translate_bundle(bundle, ok_call, checkpoint_path=cp)
            self.assertNotIn("别的篇的译文", [c["text"] for c in result["candidates"]])


class ApiErrorBodyTest(unittest.TestCase):
    def test_http_200_with_error_body_is_retried_then_reported(self):
        import urllib.request
        from contextlib import contextmanager
        import io, json as _json

        @contextmanager
        def fake_urlopen(_req, timeout=None):
            yield io.BytesIO(_json.dumps({"error": {"code": 429, "message": "rate limited"}}).encode())

        with unittest.mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(RuntimeError, "rate limited"):
                ex.openrouter_call([{"role": "user", "content": "x"}], "m", "k",
                                   retries=1, sleep_fn=lambda _s: None)
