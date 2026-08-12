#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cursor-agent CLI 传输层:把 chat messages 交给 Cursor 的无头 agent 执行。

**只是 openrouter_call 的同位替代**——逐段 prompt 构造、T/E 协议、内联复检与退档重试、
断点续跑全部仍由 openrouter_executor.translate_bundle 承担,这里不复制任何编排逻辑。
存在的理由是计费:Cursor 会员额度内免费,OpenRouter 每次调用都计费。
"""

from __future__ import annotations

import subprocess
from typing import Dict, List

DEFAULT_MODEL = "cursor-grok-4.5-high"
# 无头模式必须显式 --trust:否则 CLI 会停在 workspace trust 交互提示上,脚本里表现为静默卡死。
_BASE_ARGS = ("cursor-agent", "-p", "--trust", "--output-format", "text")


def render_prompt(messages: List[Dict[str, str]]) -> str:
    """chat messages → 单条 prompt。CLI 没有 system/user 分离,用标题拼成一段。"""
    parts = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            parts.append(m["content"])
        elif role == "assistant":
            parts.append(f"[你上一次的回答]\n{m['content']}")
        else:
            parts.append(m["content"])
    return "\n\n".join(parts)


def cursor_agent_call(messages: List[Dict[str, str]], model: str = DEFAULT_MODEL,
                      *, timeout: float = 300, runner=subprocess.run) -> str:
    """单次调用。非零退出或空输出都抛错,交给上层的重试阶梯处理。"""
    proc = runner([*_BASE_ARGS, "--model", model, render_prompt(messages)],
                  capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"cursor-agent 退出码 {proc.returncode}: {(proc.stderr or '')[:200]}")
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError("cursor-agent 无输出")
    return out
