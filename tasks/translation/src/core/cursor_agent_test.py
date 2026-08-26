#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cursor-agent 传输层:prompt 渲染与 CLI 契约(不真起进程)。"""

from __future__ import annotations

import subprocess
import unittest

try:
    from . import cursor_agent as ca
except ImportError:
    import cursor_agent as ca


class _Proc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class RenderPromptTest(unittest.TestCase):
    def test_system_and_user_are_concatenated(self):
        p = ca.render_prompt([{"role": "system", "content": "系统约束"},
                              {"role": "user", "content": "[翻译这一段] 犬がいた。"}])
        self.assertIn("系统约束", p)
        self.assertIn("[翻译这一段] 犬がいた。", p)

    def test_assistant_turn_is_labelled(self):
        p = ca.render_prompt([{"role": "system", "content": "s"},
                              {"role": "user", "content": "u"},
                              {"role": "assistant", "content": "跑偏的回答"},
                              {"role": "user", "content": "格式错误,请重写"}])
        self.assertIn("[你上一次的回答]", p)
        self.assertLess(p.index("跑偏的回答"), p.index("格式错误,请重写"))


class CallTest(unittest.TestCase):
    def test_passes_trust_and_model_and_returns_stdout(self):
        seen = {}

        def runner(argv, **kw):
            seen["argv"] = argv
            return _Proc(out="T\t译文\n")

        out = ca.cursor_agent_call([{"role": "user", "content": "x"}], "cursor-grok-4.5-high", runner=runner)
        self.assertEqual("T\t译文", out)
        # 无头模式必须 -p 且 --trust,否则会卡在交互提示上
        self.assertIn("-p", seen["argv"])
        self.assertIn("--trust", seen["argv"])
        self.assertIn("cursor-grok-4.5-high", seen["argv"])

    def test_nonzero_exit_raises(self):
        with self.assertRaisesRegex(RuntimeError, "退出码"):
            ca.cursor_agent_call([{"role": "user", "content": "x"}],
                                 runner=lambda *a, **k: _Proc(rc=1, err="boom"),
                                 retries=0, sleep_fn=lambda _s: None)

    def test_empty_output_raises(self):
        with self.assertRaisesRegex(RuntimeError, "无输出"):
            ca.cursor_agent_call([{"role": "user", "content": "x"}],
                                 runner=lambda *a, **k: _Proc(out="  \n"),
                                 retries=0, sleep_fn=lambda _s: None)


class MakeTranslateFnTest(unittest.TestCase):
    def test_executor_name_is_accepted(self):
        try:
            from . import translate_user as tu
        except ImportError:
            import translate_user as tu
        fn = tu.make_translate_fn("cursor-agent")
        self.assertTrue(callable(fn))   # 不需要 API key,与 openrouter 不同


if __name__ == "__main__":
    unittest.main()


class TransportRetryTest(unittest.TestCase):
    """传输故障必须在这一层重试:上层三档阶梯只捕 ValueError,超时/非零退出会穿透中止整篇。"""

    def test_transient_failure_is_retried_then_succeeds(self):
        calls = {"n": 0}

        def flaky(argv, **kw):
            calls["n"] += 1
            if calls["n"] < 3:
                return _Proc(rc=1, err="transient")
            return _Proc(out="T\t译文")

        out = ca.cursor_agent_call([{"role": "user", "content": "x"}],
                                   runner=flaky, sleep_fn=lambda _s: None)
        self.assertEqual("T\t译文", out)
        self.assertEqual(3, calls["n"])

    def test_timeout_is_retried(self):
        calls = {"n": 0}

        def slow(argv, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise subprocess.TimeoutExpired(cmd="cursor-agent", timeout=1)
            return _Proc(out="T\t译文")

        self.assertEqual("T\t译文", ca.cursor_agent_call([{"role": "user", "content": "x"}],
                                                        runner=slow, sleep_fn=lambda _s: None))

    def test_backoff_is_exponential(self):
        waits = []
        ca.cursor_agent_call.__wrapped__ if hasattr(ca.cursor_agent_call, "__wrapped__") else None
        calls = {"n": 0}

        def always_bad(argv, **kw):
            calls["n"] += 1
            return _Proc(rc=1)

        with self.assertRaises(RuntimeError):
            ca.cursor_agent_call([{"role": "user", "content": "x"}], runner=always_bad,
                                 retries=3, backoff=2.0, sleep_fn=waits.append)
        self.assertEqual([2.0, 4.0, 8.0], waits)
        self.assertEqual(4, calls["n"])


class FatalErrorTest(unittest.TestCase):
    """额度耗尽不该重试:它一秒都不会自愈,重试只是把失败推迟几十秒。"""

    def test_quota_exhaustion_fails_immediately(self):
        calls = {"n": 0}

        def out_of_usage(argv, **kw):
            calls["n"] += 1
            return _Proc(rc=1, err="ActionRequiredError: You're out of usage. Switch to Auto...")

        waits = []
        with self.assertRaises(ca.CursorAgentUnavailable):
            ca.cursor_agent_call([{"role": "user", "content": "x"}], runner=out_of_usage,
                                 retries=3, sleep_fn=waits.append)
        self.assertEqual(1, calls["n"])   # 只调一次
        self.assertEqual([], waits)       # 一次都没退避

    def test_transient_error_still_retries(self):
        calls = {"n": 0}

        def flaky(argv, **kw):
            calls["n"] += 1
            return _Proc(out="T\ta") if calls["n"] > 1 else _Proc(rc=1, err="connection reset")

        ca.cursor_agent_call([{"role": "user", "content": "x"}], runner=flaky, sleep_fn=lambda _s: None)
        self.assertEqual(2, calls["n"])
