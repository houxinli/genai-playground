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
        # finding 必须仍是 schema 合法的 result,否则 import 端整份 quarantine(574 段那篇实测)
        self.assertEqual([], validate_artifact("result", result))
        self.assertEqual([], check_result_against_task(bundle["task"], result))

    def test_trailing_entity_record_is_recovered_not_published(self):
        # deepseek 把 T 行和 E 行挤在同一物理行:整条协议曾被原样当成译文发布。
        # 现在解析层把它拆回去——译文干净,实体照收。
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        result = ex.translate_bundle(bundle, lambda _m: "T\t译文\tE\tおにーさん\t哥哥")
        for c in result["candidates"]:
            self.assertEqual("译文", c["text"])

    def test_unrecoverable_protocol_residue_still_aborts(self):
        # 残缺的 E 记录(列数不对)拆不回去,只能中断整篇,不能当正文发布。
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with self.assertRaisesRegex(ValueError, "结构污染"):
            ex.translate_bundle(bundle, lambda _m: "T\t译文\tE\t哥哥")

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
            # 跑完即产物:meta 记 completed,重跑不会把它当断点复用(Codex #194 P1)
            import json as _json
            self.assertTrue(_json.loads((cp.parent / f"{cp.name}.meta.json").read_text(encoding="utf-8"))["completed"])

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
            # 真实的中途断点带 sidecar meta;没有 meta 的会被当成外来产物丢弃(见 CheckpointOwnershipTest)
            ex._write_checkpoint_meta(cp, ex._checkpoint_identity(bundle, ex.DEFAULT_MODEL, 'openrouter', False))
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


class PassthroughMarkerTest(unittest.TestCase):
    """`[newpage]` 这类排版标记没有可译内容:喂给模型只会被邻句填空,原样透传且不调 API。"""

    def test_newpage_segment_is_passed_through_without_api_call(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "[newpage]"
        calls = []

        def fake_call(messages):
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            src = line.split("] ", 1)[1]
            calls.append(src)
            return f"T\t{TR.get(src, '译文')}"

        result = ex.translate_bundle(bundle, fake_call)
        self.assertEqual("[newpage]", result["candidates"][0]["text"])
        self.assertNotIn("[newpage]", calls)          # 没为它调过模型
        self.assertEqual(len(bundle["segments"]) - 1, len(calls))


class CarryPreviousTranslationTest(unittest.TestCase):
    """A/B 用:把上一段已定稿译文当风格锚点注入,默认关闭。"""

    def test_off_by_default(self):
        msgs = ex.build_messages({"segment_id": "x", "source_text": "犬がいた。"}, {})
        self.assertNotIn("上文译文", msgs[1]["content"])

    def test_previous_translation_is_labelled_and_ordered_before_source(self):
        msgs = ex.build_messages(
            {"segment_id": "x", "source_text": "犬がいた。"},
            {"neighbors": {"x": {"prev": "「おはよう」"}}},
            previous_translation="「早上好」",
        )
        u = msgs[1]["content"]
        self.assertIn("[上文译文,已定稿", u)
        self.assertIn("禁止复述", u)
        # 必须夹在 `[上文]` 源文与本段之间:与其源文相邻才构成「日→中」示范对
        self.assertLess(u.index("[上文,"), u.index("[上文译文,"))
        self.assertLess(u.index("[上文译文,"), u.index("[翻译这一段]"))

    def test_bundle_carries_previous_output_when_enabled(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        seen = []

        def fake_call(messages):
            seen.append(messages[1]["content"])
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            return f"T\t{TR[line.split('] ', 1)[1]]}"

        ex.translate_bundle(bundle, fake_call, carry_previous_translation=True)
        self.assertNotIn("上文译文", seen[0])          # 第一段没有上文
        self.assertIn("上文译文", seen[1])             # 之后带上前一段的译文
        self.assertIn("「早上好」", seen[1])


class HonorificLockTest(unittest.TestCase):
    """称谓(先輩/お兄さん)必须全篇唯一,和人名同等对待——此前被"不要报告普通名词"排除在锁外,
    实测 pixiv 16321738 的「先輩」在同一篇里既译「前辈」又译「学长」。"""

    def test_system_prompt_asks_for_honorifics(self):
        system = ex.build_messages({"segment_id": "x", "source_text": "犬がいた。"}, {})[0]["content"]
        self.assertIn("称谓", system)
        self.assertIn("先輩", system)
        self.assertIn("不指人的普通名词", system)   # 仍然排除物件/概念

    def test_honorific_first_use_is_locked_and_reused(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "先輩が笑った。"
        bundle["segments"][1]["source_text"] = "先輩はもう帰った。"
        seen = []

        def fake_call(messages):
            seen.append(messages[0]["content"])
            src = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            if "笑った" in src:
                return "T\t前辈笑了。\nE\t先輩\t前辈"
            return "T\t学长已经回去了。\nE\t先輩\t学长"      # 第二段想改译法

        result = ex.translate_bundle(bundle, fake_call)
        # 第二段的 system prompt 里必须带着第一段锁定的译法
        self.assertIn("先輩 => 前辈", seen[-1])
        # 冲突译名被纠正回首次译法,不会全篇两种称呼并存
        self.assertIn("前辈", result["candidates"][1]["text"])
        self.assertNotIn("学长", result["candidates"][1]["text"])


class CheckpointOwnershipTest(unittest.TestCase):
    """断点与最终产物同名同格式 → 必须能分辨「本轮中途」和「上一轮完成品」。"""

    @staticmethod
    def _ok_call(messages):
        line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
        return f"T\t{TR[line.split('] ', 1)[1]]}"

    def test_previous_run_output_is_not_reused(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            # 上一轮的完整产物:src_echo 全对得上,只靠内容分辨不出来
            cp.write_text("".join(f"{i}\t{s['source_text'][:12]}\t六月的旧译文\n"
                                  for i, s in enumerate(bundle["segments"])), encoding="utf-8")
            result = ex.translate_bundle(bundle, self._ok_call, checkpoint_path=cp)
            self.assertNotIn("六月的旧译文", [c["text"] for c in result["candidates"]])
            self.assertTrue(_P(f"{cp}.stale").is_file())     # 旧产物被移开保留,不是删掉

    def test_interrupted_checkpoint_is_resumed(self):
        """能续的是**中断**的断点(meta 无 completed),不是上一轮的完成品。"""
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            seg0 = bundle["segments"][0]
            cp.write_text(f"0\t{seg0['source_text'][:12]}\t中断前译好的\n", encoding="utf-8")
            ex._write_checkpoint_meta(cp, ex._checkpoint_identity(bundle, ex.DEFAULT_MODEL, 'openrouter', False))     # completed=False
            calls = []

            def counting(messages):
                calls.append(1)
                return self._ok_call(messages)

            result = ex.translate_bundle(bundle, counting, checkpoint_path=cp)
            self.assertEqual("中断前译好的", result["candidates"][0]["text"])
            self.assertEqual(len(bundle["segments"]) - 1, len(calls))

    def test_model_change_invalidates_checkpoint(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            ex.translate_bundle(bundle, self._ok_call, checkpoint_path=cp, model="model-a")
            calls = []

            def counting(messages):
                calls.append(1)
                return self._ok_call(messages)

            ex.translate_bundle(bundle, counting, checkpoint_path=cp, model="model-b")
            self.assertEqual(len(bundle["segments"]), len(calls))   # 换模型 → 全部重翻


class CodexReviewFixesTest(unittest.TestCase):
    """Codex 对 #194 的复审:两条 P1 + 两条小 P2。"""

    @staticmethod
    def _ok(messages):
        line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
        return f"T\t{TR[line.split('] ', 1)[1]]}"

    def test_second_t_record_selects_correct_segment_after_rewrite(self):
        # 旧测试只断言结果不含 `T\t`,没断言选中的是**本段**译文 → 回归没被覆盖(Codex 指出)
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        tries = {"n": 0}

        def two_then_ok(messages):
            src = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0].split("] ", 1)[1]
            tries["n"] += 1
            if tries["n"] == 1:
                return f"T\t上一段的译文\nT\t{TR[src]}"     # 两条 T,首条是上一段
            return f"T\t{TR[src]}"

        result = ex.translate_bundle(bundle, two_then_ok)
        self.assertNotIn("上一段的译文", [c["text"] for c in result["candidates"]])
        self.assertIn(TR["「おはよう」"], result["candidates"][0]["text"])

    def test_completed_output_is_not_reused_on_same_model_rerun(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            ex.translate_bundle(bundle, self._ok, checkpoint_path=cp, model="m")
            calls = []

            def counting(messages):
                calls.append(1)
                return self._ok(messages)

            # 同源、同 job、同模型重跑(改进 prompt 后重译正是这种)必须真的重翻
            ex.translate_bundle(bundle, counting, checkpoint_path=cp, model="m")
            self.assertEqual(len(bundle["segments"]), len(calls))

    def test_names_sidecar_uses_finish_filename(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "ユキが来た。"
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"

            def with_entity(messages):
                src = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0].split("] ", 1)[1]
                if "ユキ" in src:
                    return "T\t小雪来了。\nE\tユキ\t小雪"
                return f"T\t{TR[src]}"

            ex.translate_bundle(bundle, with_entity, checkpoint_path=cp)
            self.assertTrue((_P(t) / "700001.names.tsv").is_file())      # finish_user 读的名字
            self.assertFalse((_P(t) / "700001.zh.tsv.names.tsv").is_file())

    def test_resumed_segments_rebuild_entity_findings(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "ユキが来た。"
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            # 造一个"中断前已发现实体"的断点:首段译文 + names sidecar,meta 未完成
            cp.write_text(f"0\t{bundle['segments'][0]['source_text'][:12]}\t小雪来了。\n", encoding="utf-8")
            (_P(t) / "700001.names.tsv").write_text("ユキ\t小雪\n", encoding="utf-8")
            # 名字与它所属的段号一起持久化(段 0 已落盘)
            ex._write_checkpoint_meta(cp, ex._checkpoint_identity(bundle, ex.DEFAULT_MODEL, 'openrouter', False),
                                      names={"ユキ": 0})
            result = ex.translate_bundle(bundle, self._ok, checkpoint_path=cp)
            ents = [f for f in result["findings"] if f["code"] == "entity_first_use"]
            self.assertTrue(any("ユキ" in f["message"] for f in ents),
                            "中断前发现的名字必须重建 finding,否则进不了 entity-review")


class CodexSecondRoundFixesTest(unittest.TestCase):
    def test_space_separated_second_t_is_rejected(self):
        # normalize 只转首行时,第二条空格 T 会被折行循环拼进第一条译文(Codex 复审)
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        tries = {"n": 0}

        def space_two_then_ok(messages):
            src = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0].split("] ", 1)[1]
            tries["n"] += 1
            if tries["n"] == 1:
                return f"T 上一段的译文\nT {TR[src]}"
            return f"T\t{TR[src]}"

        result = ex.translate_bundle(bundle, space_two_then_ok)
        self.assertNotIn("上一段的译文", result["candidates"][0]["text"])
        self.assertIn(TR["「おはよう」"], result["candidates"][0]["text"])

    def test_producer_reflects_actual_executor(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))

        def ok(messages):
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            return f"T\t{TR[line.split('] ', 1)[1]]}"

        r = ex.translate_bundle(bundle, ok, model="cursor-grok-4.5-high", producer_name="cursor-agent")
        self.assertEqual("cursor-agent", r["producer"]["name"])
        self.assertEqual("openrouter", ex.translate_bundle(bundle, ok)["producer"]["name"])

    def test_names_sidecar_rotates_with_stale_checkpoint(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            names = _P(t) / "700001.names.tsv"
            cp.write_text("0\t上一轮\t上一轮译文\n", encoding="utf-8")     # 无 meta → 外来断点
            names.write_text("ユキ\t旧译名\n", encoding="utf-8")

            def ok(messages):
                line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
                return f"T\t{TR[line.split('] ', 1)[1]]}"

            ex.translate_bundle(bundle, ok, checkpoint_path=cp)
            self.assertTrue(_P(f"{names}.stale").is_file())   # 旧名字表同批轮换,不会被追加污染
            self.assertNotIn("旧译名", names.read_text(encoding="utf-8") if names.is_file() else "")


class CheckpointIdentityTest(unittest.TestCase):
    """断点身份要含一切影响 prompt 的执行参数,否则 A/B 两臂共用目录会混进同一产物。"""

    @staticmethod
    def _ok(messages):
        line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
        return f"T\t{TR[line.split('] ', 1)[1]]}"

    def test_other_ab_arm_checkpoint_is_not_reused(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            seg0 = bundle["segments"][0]
            cp.write_text(f"0\t{seg0['source_text'][:12]}\tA 臂的译文\n", encoding="utf-8")
            # A 臂(不带上文译文)的未完成断点
            ex._write_checkpoint_meta(cp, ex._checkpoint_identity(bundle, ex.DEFAULT_MODEL, "openrouter", False))
            # B 臂(带上文译文)不该认它
            result = ex.translate_bundle(bundle, self._ok, checkpoint_path=cp,
                                         carry_previous_translation=True)
            self.assertNotIn("A 臂的译文", [c["text"] for c in result["candidates"]])

    def test_producer_change_invalidates_checkpoint(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            cp.write_text(f"0\t{bundle['segments'][0]['source_text'][:12]}\t别的执行器译的\n", encoding="utf-8")
            ex._write_checkpoint_meta(cp, ex._checkpoint_identity(bundle, "m", "openrouter", False))
            result = ex.translate_bundle(bundle, self._ok, checkpoint_path=cp, model="m",
                                         producer_name="cursor-agent")
            self.assertNotIn("别的执行器译的", [c["text"] for c in result["candidates"]])


class NamesCheckpointAtomicityTest(unittest.TestCase):
    """名字表与段断点不是同一次写入 → 中间崩溃时不能把"孤儿名字"当已锁定(Codex #194 复审)。"""

    @staticmethod
    def _with_entity(messages):
        src = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0].split("] ", 1)[1]
        if "ユキ" in src:
            return "T\t小雪来了。\nE\tユキ\t小雪"
        return f"T\t{TR[src]}"

    def test_orphan_name_is_not_preloaded_so_entity_is_rediscovered(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "ユキが来た。"
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            # 崩在"写完名字表"与"写段断点"之间:名字在表里,段 0 却没落盘
            cp.write_text("", encoding="utf-8")
            (_P(t) / "700001.names.tsv").write_text("ユキ\t小雪\n", encoding="utf-8")
            ex._write_checkpoint_meta(cp, ex._checkpoint_identity(bundle, ex.DEFAULT_MODEL, "openrouter", False),
                                      names={"ユキ": 0})
            result = ex.translate_bundle(bundle, self._with_entity, checkpoint_path=cp)
            ents = [f for f in result["findings"] if f["code"] == "entity_first_use"]
            self.assertTrue(any("ユキ" in f["message"] for f in ents),
                            "段未落盘时名字必须重新被发现,否则永久缺席 entity-review")

    def test_orphan_name_is_removed_from_sidecar(self):
        """孤儿记录必须从文件里删掉:留着会与重译产生的新译名并存,finish 按 first-wins 拒绝整篇。"""
        import tempfile
        from pathlib import Path as _P
        try:
            from . import entity_harvest as eh
        except ImportError:
            import entity_harvest as eh
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "ユキが来た。"
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            names = _P(t) / "700001.names.tsv"
            # 段 1 已落盘且其名字有效;段 0 是孤儿(名字在表里,段没落盘)
            cp.write_text(f"1\t{bundle['segments'][1]['source_text'][:12]}\t有效译文\n", encoding="utf-8")
            names.write_text("ユキ\t旧孤儿译名\nマホ\t真秀\n", encoding="utf-8")
            ex._write_checkpoint_meta(cp, ex._checkpoint_identity(bundle, ex.DEFAULT_MODEL, "openrouter", False),
                                      names={"ユキ": 0, "マホ": 1})

            def with_new_target(messages):
                src = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0].split("] ", 1)[1]
                if "ユキ" in src:
                    return "T\t小雪来了。\nE\tユキ\t小雪"      # 与孤儿记录不同的译名
                return f"T\t{TR.get(src, '译文')}"

            ex.translate_bundle(bundle, with_new_target, checkpoint_path=cp)
            body = names.read_text(encoding="utf-8")
            self.assertNotIn("旧孤儿译名", body)
            self.assertIn("マホ\t真秀", body)                 # 有效记录保留
            eh.parse_locked_names_tsv(body)                   # 不再违反 first-wins

    def test_orphan_cleanup_runs_with_zero_completed_segments(self):
        """崩在首段"写名字表"与"写段断点"之间:done 为空,清理不能被跳过(Codex #194 复审)。"""
        import tempfile
        from pathlib import Path as _P
        try:
            from . import entity_harvest as eh
        except ImportError:
            import entity_harvest as eh
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "ユキが来た。"
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            names = _P(t) / "700001.names.tsv"
            cp.write_text("", encoding="utf-8")                    # 一段都没落盘
            names.write_text("ユキ\t旧孤儿译名\n", encoding="utf-8")
            ex._write_checkpoint_meta(cp, ex._checkpoint_identity(bundle, ex.DEFAULT_MODEL, "openrouter", False),
                                      names={"ユキ": 0})

            def with_new_target(messages):
                src = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0].split("] ", 1)[1]
                if "ユキ" in src:
                    return "T\t小雪来了。\nE\tユキ\t小雪"
                return f"T\t{TR.get(src, '译文')}"

            ex.translate_bundle(bundle, with_new_target, checkpoint_path=cp)
            body = names.read_text(encoding="utf-8")
            self.assertNotIn("旧孤儿译名", body)
            eh.parse_locked_names_tsv(body)                        # 不违反 first-wins

    def test_names_cleanup_is_atomic(self):
        """写回期间被杀不能留下截断的名字表:临时文件 + rename,原文件要么旧要么新。"""
        import tempfile
        from pathlib import Path as _P
        with tempfile.TemporaryDirectory() as t:
            names = _P(t) / "700001.names.tsv"
            names.write_text("ユキ\t小雪\nマホ\t真秀\n", encoding="utf-8")
            original = names.read_text(encoding="utf-8")
            with unittest.mock.patch.object(ex.os, "replace", side_effect=RuntimeError("kill")):
                with self.assertRaises(RuntimeError):
                    ex._atomic_write_text(names, "只写了一半")
            self.assertEqual(original, names.read_text(encoding="utf-8"))   # 原文件未被截断
            self.assertEqual([], list(_P(t).glob("*.tmp")))                 # 临时文件已清理


class TenthRoundFixesTest(unittest.TestCase):
    """Codex 第十轮:上文译文只在有上文时给、producer type 随执行器、坏断点要轮换。"""

    @staticmethod
    def _ok(messages):
        line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
        return f"T\t{TR.get(line.split('] ', 1)[1], '译文')}"

    def test_no_previous_translation_without_prev_source(self):
        msgs = ex.build_messages({"segment_id": "x", "source_text": "犬がいた。"}, {},
                                 previous_translation="metadata 的译文")
        self.assertNotIn("上文译文", msgs[1]["content"])   # 没有 [上文] 就不给它的译文

    def test_previous_text_tracks_body_only(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"].insert(0, {"segment_id": "meta:0", "kind": "metadata.tags",
                                      "source_text": "[R-18]"})
        bundle["task"]["source_hashes"]["meta:0"] = "h0"
        seen = []

        def spy(messages):
            seen.append(messages[1]["content"])
            return self._ok(messages)

        ex.translate_bundle(bundle, spy, carry_previous_translation=True)
        self.assertFalse(any("[R-18]" in u or "上文译文] 译文" in u for u in seen[1:2]),
                         "metadata 译文不该成为正文段的上文锚点")

    def test_producer_type_follows_executor(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        r = ex.translate_bundle(bundle, self._ok, producer_name="cursor-agent", producer_type="harness")
        self.assertEqual({"harness", "cursor-agent"}, {r["producer"]["type"], r["producer"]["name"]})
        self.assertEqual("api", ex.translate_bundle(bundle, self._ok)["producer"]["type"])

    def test_corrupt_checkpoint_is_rotated_not_appended(self):
        import tempfile
        from pathlib import Path as _P
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        with tempfile.TemporaryDirectory() as t:
            cp = _P(t) / "700001.zh.tsv"
            cp.write_text("0\t半行没写完", encoding="utf-8")      # 坏行:少一列
            ex._write_checkpoint_meta(cp, ex._checkpoint_identity(bundle, ex.DEFAULT_MODEL, "openrouter", False))
            ex.translate_bundle(bundle, self._ok, checkpoint_path=cp)
            self.assertTrue(_P(f"{cp}.corrupt").is_file())         # 坏文件被轮换
            self.assertNotIn("半行没写完", cp.read_text(encoding="utf-8"))
            # 轮换后的新断点必须能再次解析(否则下次恢复仍在同一处失败)
            self.assertIsNotNone(ex._load_checkpoint(cp, bundle))


class MarkerPatternTest(unittest.TestCase):
    """结构标记用模式判定:固定集合每漏一种就重演一次「标记段被塞进邻段正文」。"""

    def test_known_and_symbolic_markers(self):
        for m in ("[newpage]", "◇", "◇◇◇", "＊＊＊", "＊＊＊＊＊＊", "──────────", "※"):
            self.assertTrue(ex.is_passthrough_segment(m), m)

    def test_real_text_is_not_a_marker(self):
        for t in ("「おはよう」", "犬がいた。", "──ぶびゅッッッ♡♡♡", "……", "♡♡♡"):
            self.assertFalse(ex.is_passthrough_segment(t), t)

    def test_symbolic_marker_passes_through_without_api_call(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "◇"
        calls = []

        def fake(messages):
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            calls.append(line)
            return f"T\t{TR.get(line.split('] ', 1)[1], '译文')}"

        r = ex.translate_bundle(bundle, fake)
        self.assertEqual("◇", r["candidates"][0]["text"])
        self.assertFalse(any("◇" in c for c in calls))


class NarrationPovTest(unittest.TestCase):
    """滚动叙述视角:逐段翻译丢失了"本篇是第一人称"这个信息,无主语旁白句只能靠猜。"""

    def test_pov_only_from_narration_not_dialogue(self):
        self.assertEqual("俺", ex.narration_pov("俺は立ち上がった。"))
        self.assertIsNone(ex.narration_pov("「俺がやるよ」"))   # 台词里的自称与叙述视角无关
        self.assertIsNone(ex.narration_pov("彼は立ち上がった。"))

    def test_pov_block_only_constrains_subjectless(self):
        b = ex._pov_block("俺")
        self.assertIn("第一人称", b)
        self.assertIn("省略主语", b)
        self.assertIn("仍按第三人称译", b)      # 源文明写「彼が」的不动

    def test_pov_is_injected_and_rolls_forward(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        bundle["segments"][0]["source_text"] = "俺は歩いた。"
        bundle["segments"][1]["source_text"] = "立ち上がった。"       # 无主语,应沿用上一段视角
        seen = []

        def spy(messages):
            seen.append(messages[0]["content"])
            return "T\t译文"

        ex.translate_bundle(bundle, spy)
        self.assertIn("「俺」", seen[0])              # 该段自带证据,注入无害
        self.assertIn("「俺」", seen[1])              # **关键**:无主语段沿用了上一段的视角

    def test_scene_marker_resets_pov(self):
        rev = _rev()
        bundle = te.export_job(rev, _body_ids(rev))
        segs = bundle["segments"]
        segs[0]["source_text"] = "俺は歩いた。"
        segs.insert(1, {"segment_id": "mk", "kind": "body", "source_text": "[newpage]"})
        segs.insert(2, {"segment_id": "s2", "kind": "body", "source_text": "立ち上がった。"})
        for sid in ("mk", "s2"):
            bundle["task"]["source_hashes"][sid] = "h"
        seen = []

        def spy(messages):
            seen.append(messages[0]["content"])
            return "T\t译文"

        ex.translate_bundle(bundle, spy)
        # 场景标记后的无主语段不该继承上一场景的视角(实测 5 篇在场景边界切换人称)
        self.assertNotIn("本场景叙述视角", seen[1])

    def test_inline_quotes_are_stripped_before_pov(self):
        # 段内嵌台词里的自称不能当叙述视角(实测让第三人称篇被误判成第一人称)
        self.assertIsNone(ex.narration_pov("彼は「私がやる」と言って立ち上がった。"))
        self.assertIsNone(ex.narration_pov("少年は「わしに任せろ」と笑った。"))
        self.assertEqual("俺", ex.narration_pov("「任せろ」と彼が言うので、俺は頷いた。"))

    def test_pronoun_lookalikes_are_not_pov(self):
        # 「わしわし」是揉搓拟声、「思わしき」是构词,都不是人称代词(实测让视角乱跳)
        self.assertIsNone(ex.narration_pov("そのままわしわしと揉みこみ始める。"))
        self.assertIsNone(ex.narration_pov("女子高生と思わしき彼女は小さな体格をしていた。"))
        self.assertEqual("わたし", ex.narration_pov("わたしは頷いた。"))   # 假名形态后接助词才算
        self.assertIn("我", ex._pov_block("わたし"))                      # 目标译法仍是「我」
        self.assertIsNone(ex.narration_pov("（私だって揉みたい……）"))   # 整段心声不是旁白
        self.assertEqual("私", ex.narration_pov("私は頷いた。"))
