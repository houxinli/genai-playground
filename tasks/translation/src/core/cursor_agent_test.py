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
                                 runner=lambda *a, **k: _Proc(rc=1, err="boom"))

    def test_empty_output_raises(self):
        with self.assertRaisesRegex(RuntimeError, "无输出"):
            ca.cursor_agent_call([{"role": "user", "content": "x"}],
                                 runner=lambda *a, **k: _Proc(out="  \n"))


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
