#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cursor-agent CLI 传输层:把 chat messages 交给 Cursor 的无头 agent 执行。

**只是 openrouter_call 的同位替代**——逐段 prompt 构造、T/E 协议、内联复检与退档重试、
断点续跑全部仍由 openrouter_executor.translate_bundle 承担,这里不复制任何编排逻辑。
存在的理由是计费:Cursor 会员额度内免费,OpenRouter 每次调用都计费。
"""

from __future__ import annotations

import subprocess
import time
from typing import Dict, List

DEFAULT_MODEL = "cursor-grok-4.5-high"
# 额度耗尽/需要人工处置的错误**重试毫无意义**,只是把失败推迟几十秒。
# 实测额度用尽时退避重试了 4 次(3+6+12s)才放弃,而它一秒都不会自愈。
# 与 openrouter_call 区分"可重试状态码"和"4xx 立即抛出"是同一类判断。
_FATAL_MARKERS = (
    "out of usage",
    "ActionRequiredError",
    "Increase limits",
    "Unauthorized",
    "not logged in",
    "invalid api key",
)


class CursorAgentUnavailable(RuntimeError):
    """额度/鉴权类不可重试故障:调用方应当停止本轮而不是继续烧时间。"""
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
                      *, timeout: float = 300, runner=subprocess.run,
                      retries: int = 3, backoff: float = 3.0, sleep_fn=time.sleep) -> str:
    """单次调用,带退避重试。

    **传输故障必须在这一层重试**:上层 `_translate_segment` 的三档阶梯只处理"调用成功但输出不合格",
    它的 try/except 只捕 ValueError;超时/非零退出/空输出会直接穿透上去中止整篇(Codex #194 复审)。
    长篇逐段跑几百次 CLI,偶发一次瞬时故障不该让整篇作废。
    """
    argv = [*_BASE_ARGS, "--model", model, render_prompt(messages)]
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            proc = runner(argv, capture_output=True, text=True, timeout=timeout)
            if proc.returncode != 0:
                detail = ((proc.stderr or "") + (proc.stdout or ""))[:400]
                if any(m.lower() in detail.lower() for m in _FATAL_MARKERS):
                    raise CursorAgentUnavailable(
                        f"cursor-agent 不可用(额度/鉴权,重试无意义): {detail[:200]}")
                raise RuntimeError(f"cursor-agent 退出码 {proc.returncode}: {detail[:200]}")
            out = (proc.stdout or "").strip()
            if not out:
                raise RuntimeError("cursor-agent 无输出")
            return out
        except CursorAgentUnavailable:
            raise                     # 不可重试:立刻上抛,断点已保住已完成段
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
            last = exc
            if attempt == retries:
                raise
            sleep_fn(backoff * (2 ** attempt))
    raise last  # 不可达(循环内已抛),保险
