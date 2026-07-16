#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenRouter Grok 翻译执行器:消费自包含 job bundle,逐段翻译产 schema 合法的 result.json。

新架构 harness 路径的一个具体 API 执行器(producer=api/openrouter)。system prompt 注入
bundle.context_pack 的人名/术语硬约束(#83 P1a/P1b);逐段一 candidate，并用简单 T/E 响应在
同一次调用里锁定本文首次译名。translate_bundle 是纯函数(注入 call_fn),CI 用 mock 测;
真实 OpenRouter 调用走 CLI(grok-4/grok-4-fast 已弃用,
默认 x-ai/grok-4.3)。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from . import entity_harvest
    from .document_qa import translation_shape_errors
except ImportError:
    import entity_harvest
    from document_qa import translation_shape_errors

DEFAULT_MODEL = "x-ai/grok-4.3"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_BASE = (
    "你是一名专业的日译中网络小说译者。逐段翻译,不要解释、不要注释、不要 Markdown、"
    "不要输出原文或上下文标记。沿用原文的方引号「」『』。中文用恰当中文标点。"
    "译文必须只有一个物理行,禁止换行。译文不得残留日文假名。"
    "tags 段译成 `原词 / 中文` 并保留 `[]` 与逗号。"
    "严格使用简单行协议:第一行是 `T<TAB>中文译文`;之后把本段实际使用的每个人名或专名"
    "各写一行"
    " `E<TAB>日文原写法<TAB>本段实际中文译名`;没有人名就只写 T 行。不要报告普通名词,"
    "也不要报告本段源文或译文中没有实际出现的名字。"
)


def _constraints_block(context_pack: Dict[str, Any]) -> str:
    """把 context_pack 的 entities/terminology 拼成人名/术语硬约束块。"""
    lines: List[str] = []
    for e in context_pack.get("entities", []):
        line = f"- {e['source']} => {e['target']}"
        if e.get("aliases"):
            line += f"(别名: {', '.join(e['aliases'])})"
        if e.get("forbidden"):
            line += f"(禁止译为: {', '.join(e['forbidden'])})"
        lines.append(line)
    for t in context_pack.get("terminology", []):
        lines.append(f"- {t['source']} => {t['target']}")
    return "【人名/术语硬约束,必须遵守】\n" + "\n".join(lines) if lines else ""


def _document_targets_block(document_targets: Dict[str, str]) -> str:
    lines = [f"- {source} => {target}" for source, target in document_targets.items()]
    if not lines:
        return ""
    return "【本篇此前首次译名,只能使用以下唯一译法】\n" + "\n".join(lines)


def build_messages(
    segment: Dict[str, Any],
    context_pack: Dict[str, Any],
    document_targets: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    """单段 → chat messages。注入硬约束 + 邻句上下文(邻句只供参考,不翻译/不输出)。"""
    system = _SYSTEM_BASE
    constraints = _constraints_block(context_pack)
    if constraints:
        system += "\n\n" + constraints
    document_constraints = _document_targets_block(document_targets or {})
    if document_constraints:
        system += "\n\n" + document_constraints
    neighbors = context_pack.get("neighbors", {}).get(segment["segment_id"], {})
    parts: List[str] = []
    if neighbors.get("prev"):
        parts.append(f"[上文,仅供理解,勿翻译] {neighbors['prev']}")
    parts.append(f"[翻译这一段] {segment['source_text']}")
    if neighbors.get("next"):
        parts.append(f"[下文,仅供理解,勿翻译] {neighbors['next']}")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(parts)}]


def translate_bundle(
    bundle: Dict[str, Any],
    call_fn: Callable[[List[Dict[str, str]]], str],
    *,
    model: str = DEFAULT_MODEL,
    candidate_key: str = "grok",
    completed_at: Optional[str] = None,
) -> Dict[str, Any]:
    """逐段调 call_fn 翻译；本篇首次译名锁定并只把 canonical target 传给下一段。"""
    task = bundle["task"]
    context_pack = bundle.get("context_pack", {})
    source_hashes = task["source_hashes"]
    candidates = []
    findings = []
    locked_targets = entity_harvest.context_targets(context_pack)
    document_targets: Dict[str, str] = {}
    for index, seg in enumerate(bundle["segments"]):
        response = call_fn(build_messages(seg, context_pack, document_targets))
        try:
            text, observations = entity_harvest.parse_executor_response(response)
        except ValueError as exc:
            raise ValueError(f"segment {seg['segment_id']} 返回结构污染: {exc}") from exc
        text, first_uses, _ = entity_harvest.apply_observations(
            seg["source_text"], text, observations, locked_targets
        )
        for entity in first_uses:
            document_targets[entity["source"]] = entity["target"]
            findings.append(entity_harvest.entity_finding(
                entity["source"], entity["target"], seg["segment_id"], index + 1
            ))
        shape_errors = translation_shape_errors(text)
        if shape_errors:
            raise ValueError(
                f"segment {seg['segment_id']} 返回结构污染: {shape_errors};"
                "执行器必须只输出当前段的一行译文"
            )
        candidates.append({
            "result_candidate_key": candidate_key,
            "segment_id": seg["segment_id"],
            "source_hash": source_hashes[seg["segment_id"]],
            "text": text,
        })
    return {
        "schema_version": 1,
        "task_id": task["task_id"],
        "task_digest": bundle["task_digest"],
        "producer": {"type": "api", "name": "openrouter", "model": model},
        "candidates": candidates,
        "findings": findings,
        "recommended_candidate_keys": [candidate_key],
        "completed_at": completed_at or datetime.now(timezone.utc).isoformat(),
    }


_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


def openrouter_call(messages: List[Dict[str, str]], model: str, api_key: str,
                    *, temperature: float = 0.3, max_tokens: int = 4096,
                    timeout: float = 180, retries: int = 4, backoff: float = 3.0,
                    sleep_fn=time.sleep) -> str:
    """单次 chat 调用,带退避重试——长篇逐段翻译里单个超时/限流/5xx 不该让整篇失败。
    可重试:超时/连接错误、HTTP 408/409/429/5xx;其余 HTTP 4xx 立即抛出(请求本身有问题)。"""
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    data = json.dumps(payload).encode("utf-8")
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            OPENROUTER_URL, data=data,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.load(resp)
            return body["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in _RETRYABLE_STATUS or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_exc = exc
            if attempt == retries:
                raise
        sleep_fn(backoff * (2 ** attempt))  # 指数退避
    raise last_exc  # 不可达(循环内已抛),保险


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path, help="translate job bundle json")
    parser.add_argument("--out", required=True, type=Path, help="result.json 输出")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        parser.error("需要环境变量 OPENROUTER_API_KEY")
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    result = translate_bundle(bundle, lambda m: openrouter_call(m, args.model, api_key), model=args.model)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"translated {len(result['candidates'])} segments -> {args.out} (model={args.model})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
