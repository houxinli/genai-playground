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
    from . import document_qa, entity_harvest
    from .document_qa import translation_shape_errors
except ImportError:
    import document_qa
    import entity_harvest
    from document_qa import translation_shape_errors

DEFAULT_MODEL = "x-ai/grok-4.3"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_BASE = (
    "你是一名专业的日译中网络小说译者。逐段翻译,不要解释、不要注释、不要 Markdown、"
    "不要输出原文或上下文标记。沿用原文的方引号「」『』。中文用恰当中文标点。"
    "**只翻译 `[翻译这一段]` 标记的那一段**;`[上文]`/`[下文]` 只供你理解指代和语气,"
    "绝对不要翻译、复述或把它们的内容拼进译文。"
    "译文必须只有一个物理行,禁止换行。译文不得残留日文假名。"
    "tags 段译成 `原词 / 中文` 并保留 `[]` 与逗号。"
    "严格使用简单行协议:第一行是 `T` + ASCII 制表符(TAB,U+0009) + 中文译文;"
    "之后把本段实际使用的每个人名、专名**或称谓**各写一行"
    " `E` + TAB + 日文原写法 + TAB + 本段实际中文译名;"
    "分隔符必须是 TAB,禁止用空格代替。没有可报告的就只写 T 行。"
    "**称谓指用来称呼人的词**(先輩/後輩/お兄さん/お姉ちゃん/センセイ/ママ 这类),"
    "它们和人名一样必须全篇唯一,所以要报告;"
    "不指人的普通名词(物件、身体部位、概念)不要报告,"
    "也不要报告本段源文或译文中没有实际出现的词。"
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
    *,
    neighbors_mode: str = "both",
    previous_translation: Optional[str] = None,
) -> List[Dict[str, str]]:
    """单段 → chat messages。注入硬约束 + 邻句上下文(邻句只供参考,不翻译/不输出)。

    neighbors_mode:`both`=前后都给(默认);`next`=只给下文;`none`=不给邻句。
    退档用:小模型顶不住时,上文正是被误译进来的那段,拿掉它比继续加指令有效(见 translate_bundle)。
    """
    system = _SYSTEM_BASE
    constraints = _constraints_block(context_pack)
    if constraints:
        system += "\n\n" + constraints
    document_constraints = _document_targets_block(document_targets or {})
    if document_constraints:
        system += "\n\n" + document_constraints
    neighbors = context_pack.get("neighbors", {}).get(segment["segment_id"], {})
    parts: List[str] = []
    if neighbors.get("prev") and neighbors_mode == "both":
        parts.append(f"[上文,仅供理解,勿翻译] {neighbors['prev']}")
    if previous_translation and neighbors_mode == "both":
        # 跨段传递的此前只有译名映射,模型看不到自己译出的中文 → 文风/口吻/称谓逐段漂移。
        # **必须紧跟 `[上文]` 之后**:与其源文相邻才构成一个「日→中」示范对;
        # 悬在最前面时它是一句无来源的孤立中文,模型只当背景噪声(实测两条臂指标无差别)。
        # 措辞强调"已定稿、禁止复述",否则会重蹈邻段窜入——内联复检仍然兜底。
        parts.append(f"[上文译文,已定稿,只用于衔接语气与称谓,禁止复述或改写] {previous_translation}")
    parts.append(f"[翻译这一段] {segment['source_text']}")
    if neighbors.get("next") and neighbors_mode in ("both", "next"):
        parts.append(f"[下文,仅供理解,勿翻译] {neighbors['next']}")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(parts)}]


# 本段译文相对源文的长度上限:超出即疑似把邻句也译了进来(中译日文一般 0.6–1.1 倍)。
# 常数项容忍极短段(拟声词、"はい♡" 这类)的正常膨胀。
_OVERLONG_SLOPE, _OVERLONG_INTERCEPT = 1.35, 12


def segment_quality_errors(source_text: str, text: str, previous_text: str = "") -> List[str]:
    """单段译文的内联复检:返回问题码,空表示通过。

    比 `translation_shape_errors` 更严——那是"能不能进 TSV"的结构底线,这里是"这段是不是真的只译了这段"。
    放在执行器内联做,是因为误判成本只有一次重试;放到 finish 才发现就只能整篇返工。
    """
    errors: List[str] = []
    errors.extend(translation_shape_errors(text))
    if "\t" in text:
        errors.append("protocol_residue")
    if len(text) > _OVERLONG_SLOPE * len(source_text) + _OVERLONG_INTERCEPT:
        errors.append("overlong_vs_source")
    if previous_text and document_qa.neighbor_leak_suspect(
        previous_text, text, threshold=document_qa.NEIGHBOR_OVERLAP_EXECUTOR
    ):
        errors.append("neighbor_overlap")
    return errors


# 结构标记段:源文整段就是一个排版标记,没有可译内容。喂给模型只会让它拿邻句填空
# (实测 pixiv 9425701 三篇都把整段邻段正文塞进了 `[newpage]`),原样透传即可。
# 语料里 725 处,顺带省掉同等数量的 API 调用。
PASSTHROUGH_SEGMENTS = frozenset({"[newpage]"})


_FORMAT_REWRITE = (
    "格式错误。请严格重写:第一行必须是 T + ASCII TAB + 中文译文;"
    "随后每行 E + TAB + 日文原名 + TAB + 中文译名(恰好三列,不要多余列)。"
    "没有人名就只写 T 行。"
)
_ONLY_THIS_SEGMENT = (
    "上一次回答把 `[上文]`/`[下文]` 的内容也翻译进来了。请只重新输出 `[翻译这一段]` 那一段的译文,"
    "一个物理行,不要包含上下文的任何内容。"
)


def _translate_segment(
    seg: Dict[str, Any],
    context_pack: Dict[str, Any],
    document_targets: Dict[str, str],
    previous_text: str,
    call_fn: Callable[[List[Dict[str, str]]], str],
    *,
    carry_previous_translation: bool = False,
):
    """一段的三档重试:正常 → 带纠正指令重问 → 拿掉 `[上文]` 重问。返回 (译文, 观察, 剩余问题码)。

    档位是按**实测有效性**排的(pixiv 27417304,deepseek/deepseek-chat):
    system prompt 加"只译本段"后泄漏从约半数降到 16/213;剩下那批加指令重问也不改,
    但拿掉 `[上文]` 后全部干净——上文在 prompt 里,模型就忍不住要译它。
    """
    attempts = [
        ("both", None),
        ("both", _ONLY_THIS_SEGMENT),
        ("next", None),   # 上文是污染源,直接不给
    ]
    best: Optional[tuple] = None
    for neighbors_mode, correction in attempts:
        messages = build_messages(
            seg, context_pack, document_targets, neighbors_mode=neighbors_mode,
            previous_translation=previous_text if carry_previous_translation else None,
        )
        if correction is not None:
            messages = messages + [{"role": "user", "content": correction}]
        response = call_fn(messages)
        try:
            text, observations = entity_harvest.parse_executor_response(response)
        except ValueError:
            # 协议漂移:同一档内先给一次严格格式纠错机会,避免整篇因一次跑偏中断。
            response = call_fn(messages + [
                {"role": "assistant", "content": response},
                {"role": "user", "content": _FORMAT_REWRITE},
            ])
            try:
                text, observations = entity_harvest.parse_executor_response(response)
            except ValueError:
                continue
        errors = segment_quality_errors(seg["source_text"], text, previous_text)
        if not errors:
            return text, observations, []
        if best is None or len(errors) < len(best[2]):
            best = (text, observations, errors)
    if best is None:
        raise ValueError(f"segment {seg['segment_id']} 返回结构污染: 三次重试都无法解析 T/E 协议")
    return best


def _checkpoint_meta_path(path: Path) -> Path:
    return Path(f"{path}.meta.json")


def _checkpoint_is_ours(path: Path, bundle: Dict[str, Any], model: str) -> bool:
    """断点是否属于**本次**翻译(同一 job、同一模型)。

    断点文件与最终产物同名同格式,所以「上一轮已完成的译文」和「本轮中途的断点」长得一模一样。
    只靠 src_echo 分不出来——源文没变时旧产物照样通过校验,于是整篇被跳过、旧译文原样重新发布,
    而且 published=1 一切正常,从输出上完全看不出没翻(重译 pixiv 9425701 时实测踩到)。
    因此额外要求 sidecar meta 里的 task_digest 与 model 都对得上;没有 meta 一律不复用。
    """
    meta_path = _checkpoint_meta_path(path)
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return meta.get("task_digest") == bundle.get("task_digest") and meta.get("model") == model


def _write_checkpoint_meta(path: Path, bundle: Dict[str, Any], model: str) -> None:
    _checkpoint_meta_path(path).write_text(
        json.dumps({"task_digest": bundle.get("task_digest"), "model": model},
                   ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _load_checkpoint(path: Optional[Path], bundle: Dict[str, Any]) -> Dict[int, str]:
    """读断点 TSV(与产物同格式),返回 段序号→译文;src_echo 对不上就整份作废重译。"""
    if path is None or not Path(path).is_file():
        return {}
    done: Dict[int, str] = {}
    segments = bundle["segments"]
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3 or not parts[0].isdigit():
            return {}
        index = int(parts[0])
        if index >= len(segments) or not segments[index]["source_text"].startswith(parts[1]):
            return {}  # 断点属于别的源/别的切分 → 不要拿来续,宁可重译
        done[index] = parts[2]
    return done


def translate_bundle(
    bundle: Dict[str, Any],
    call_fn: Callable[[List[Dict[str, str]]], str],
    *,
    model: str = DEFAULT_MODEL,
    candidate_key: str = "grok",
    completed_at: Optional[str] = None,
    checkpoint_path: Optional[Path] = None,
    carry_previous_translation: bool = False,
) -> Dict[str, Any]:
    """逐段调 call_fn 翻译；本篇首次译名锁定并只把 canonical target 传给下一段。

    checkpoint_path:每段译完就**追加**进这个 TSV(即最终产物格式),中断后重跑自动续上。
    长篇一次限流就丢掉全部已译段落的代价太高(574 段那篇实测在 200 段处丢光)。
    首次译名同时落 `<checkpoint>.names.tsv` 并在续跑时预载,否则续跑段落会脱离前半篇的译名锁定。
    """
    task = bundle["task"]
    context_pack = bundle.get("context_pack", {})
    source_hashes = task["source_hashes"]
    candidates = []
    findings = []
    locked_targets = entity_harvest.context_targets(context_pack)
    document_targets: Dict[str, str] = {}
    if checkpoint_path is not None and not _checkpoint_is_ours(Path(checkpoint_path), bundle, model):
        # 不是本轮的断点(上一轮完成品/换了模型/换了 job)→ 不复用,从头翻并接管这个文件。
        if Path(checkpoint_path).is_file():
            stale = Path(f"{checkpoint_path}.stale")
            Path(checkpoint_path).replace(stale)
            print(f"openrouter: 断点不属于本轮(已移至 {stale.name}),从头翻译", flush=True)
        _write_checkpoint_meta(Path(checkpoint_path), bundle, model)
    done = _load_checkpoint(checkpoint_path, bundle)
    names_path = Path(f"{checkpoint_path}.names.tsv") if checkpoint_path is not None else None
    if done and names_path is not None and names_path.is_file():
        for line in names_path.read_text(encoding="utf-8").splitlines():
            source, _, target = line.partition("\t")
            if source and target:
                document_targets[source] = target
                locked_targets.setdefault(source, target)
    if done:
        print(f"openrouter resume: 复用断点 {len(done)}/{len(bundle['segments'])} 段", flush=True)
    previous_text = ""
    for index, seg in enumerate(bundle["segments"]):
        marker = seg["source_text"].strip()
        if marker in PASSTHROUGH_SEGMENTS and index not in done:
            candidates.append({
                "result_candidate_key": candidate_key,
                "segment_id": seg["segment_id"],
                "source_hash": source_hashes[seg["segment_id"]],
                "text": marker,
            })
            previous_text = marker
            if checkpoint_path is not None:
                with Path(checkpoint_path).open("a", encoding="utf-8") as fh:
                    fh.write(f"{index}\t{seg['source_text'][:12]}\t{marker}\n")
            continue
        if index in done:
            text = done[index]
            candidates.append({
                "result_candidate_key": candidate_key,
                "segment_id": seg["segment_id"],
                "source_hash": source_hashes[seg["segment_id"]],
                "text": text,
            })
            previous_text = text
            continue
        text, observations, seg_errors = _translate_segment(
            seg, context_pack, document_targets, previous_text, call_fn,
            carry_previous_translation=carry_previous_translation,
        )
        if seg_errors:
            # 退无可退:结构错(进不了 TSV)仍然中断整篇;质量错(邻段窜入/超长)照常发布并记 finding,
            # 与 skill「质量问题不阻断发布」一致——阻断反而让整篇没产物、更难修。
            if any(code in ("multiline_translation", "protocol_residue") for code in seg_errors):
                raise ValueError(
                    f"segment {seg['segment_id']} 返回结构污染: {seg_errors};"
                    "执行器必须只输出当前段的一行译文"
                )
            # Result schema 的 finding 只认 code/severity/message/evidence/line,
            # 段落定位走 evidence(与 entity_finding 同款)——不为此扩 schema。
            findings.append({
                "code": "segment_quality",
                "severity": "warning",
                "message": f"重试后仍未通过内联复检: {seg_errors}",
                "evidence": json.dumps(
                    {"segment_id": seg["segment_id"], "errors": seg_errors},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ),
                "line": index + 1,
            })
        text, first_uses, _ = entity_harvest.apply_observations(
            seg["source_text"], text, observations, locked_targets
        )
        for entity in first_uses:
            document_targets[entity["source"]] = entity["target"]
            findings.append(entity_harvest.entity_finding(
                entity["source"], entity["target"], seg["segment_id"], index + 1
            ))
            if names_path is not None:
                with names_path.open("a", encoding="utf-8") as fh:
                    fh.write(f"{entity['source']}\t{entity['target']}\n")
        previous_text = text
        candidates.append({
            "result_candidate_key": candidate_key,
            "segment_id": seg["segment_id"],
            "source_hash": source_hashes[seg["segment_id"]],
            "text": text,
        })
        if checkpoint_path is not None:
            with Path(checkpoint_path).open("a", encoding="utf-8") as fh:
                fh.write(f"{index}\t{seg['source_text'][:12]}\t{text}\n")
        if (index + 1) % 10 == 0 or index + 1 == len(bundle["segments"]):
            print(f"openrouter translated {index + 1}/{len(bundle['segments'])}", flush=True)
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
            if "choices" in body:
                return body["choices"][0]["message"]["content"]
            # OpenRouter 限流/上游故障时会返回 **HTTP 200 + {"error": {...}}**,不是错误码。
            # 原样解包只会得到 KeyError: 'choices',整篇中断且看不出原因(574 段那篇实测)。
            detail = (body.get("error") or {}).get("message") or json.dumps(body, ensure_ascii=False)[:200]
            last_exc = RuntimeError(f"OpenRouter 返回无 choices: {detail}")
            if attempt == retries:
                raise last_exc
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
