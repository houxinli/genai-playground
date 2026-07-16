#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""紧凑译文 → result.json 组装(#134):让 agent 只产译文,机械的身份回填交给 harness。

agent 翻大文档时若逐段写完整 result.json(每段抄 segment_id + 64 位 source_hash + candidate_key),
工具调用与输出量都会爆(Cursor 每轮 25/200 上限)。紧凑路径:agent 写一个 `<id>.zh.tsv`——
每行 `段号<TAB>中文译文`(段号 = bundle.segments 的 0 基序号);本模块从 bundle 回填
segment_id/source_hash/task_digest/producer,产出 schema 合法 result.json。可选两列 `<id>.names.tsv`
保存本篇 first-wins 译名，由 harness 组装为 Result info findings。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from . import entity_harvest
except ImportError:
    import entity_harvest


def _source_echoes(bundle: Dict[str, Any]) -> Dict[int, str]:
    return {i: seg["source_text"] for i, seg in enumerate(bundle["segments"])}


def parse_translations_tsv(content: str, bundle: Optional[Dict[str, Any]] = None) -> Dict[int, str]:
    """解析 `段号<TAB>译文` 或 v2 `段号<TAB>src_echo<TAB>译文` 文本。

    格式判定是**文件级**的:所有内容行都有 ≥2 个 TAB 才按 v2 解析(传 bundle 时逐行校验
    src_echo 必须是对应源文前缀);否则整份按旧二列解析——译文取第一个 TAB 之后的**全部**
    内容(含 TAB 原样保留),不会被误当 v2 截断。混合文件(看着像 v2 却掺二列行)会报错,
    避免 v2 保护被静默降级。
    """
    lines = [(n, l) for n, l in enumerate(content.splitlines(), 1) if l.strip()]
    for lineno, line in lines:
        if "\t" not in line:
            raise ValueError(f"第 {lineno} 行缺 TAB 分隔(应为 `段号<TAB>译文` 或 v2 `段号<TAB>src_echo<TAB>译文`): {line!r}")
    is_v2 = bool(lines) and all(l.count("\t") >= 2 for _, l in lines)
    echoes = _source_echoes(bundle) if bundle is not None else None
    out: Dict[int, str] = {}
    for lineno, line in lines:
        if is_v2:
            idx_str, src_echo, text = line.split("\t", 2)
        else:
            idx_str, _, text = line.partition("\t")
            src_echo = None
        try:
            idx = int(idx_str.strip())
        except ValueError:
            raise ValueError(f"第 {lineno} 行段号不是整数: {idx_str!r}")
        if idx in out:
            raise ValueError(f"段号 {idx} 重复(第 {lineno} 行)")
        if echoes is not None:
            expected = echoes.get(idx)
            if expected is None:
                raise ValueError(f"第 {lineno} 行段号 {idx} 不在 job 中")
            if src_echo is not None:
                if not src_echo:
                    raise ValueError(f"第 {lineno} 行 src_echo 为空")
                if expected[:len(src_echo)] != src_echo:
                    raise ValueError(f"第 {lineno} 行 src_echo 与源文不匹配: 段号 {idx}")
            elif "\t" in text and expected.startswith(text.split("\t", 1)[0]) and text.split("\t", 1)[0]:
                # 旧格式行的"译文"以源文前缀开头且后跟 TAB → 疑似 v2 文件掺了二列行,拒绝静默降级
                raise ValueError(f"第 {lineno} 行疑似 v2 行混入二列文件(src_echo 匹配源文): 段号 {idx}")
        out[idx] = text
    return out


def assemble_result(
    bundle: Dict[str, Any], translations: Dict[int, str], *,
    producer_name: str = "agent", model: Optional[str] = None, completed_at: Optional[str] = None,
    findings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """从 bundle + {段号:译文} 组装 schema 合法 result。逐段回填 segment_id/source_hash,agent 不碰这些。"""
    task = bundle["task"]
    segments = bundle["segments"]
    source_hashes = task["source_hashes"]
    missing = [i for i in range(len(segments)) if i not in translations]
    if missing:
        raise ValueError(f"缺 {len(missing)} 段译文(段号示例: {missing[:10]});需覆盖全部 {len(segments)} 段")
    extra = [i for i in translations if i < 0 or i >= len(segments)]
    if extra:
        raise ValueError(f"译文含越界段号 {extra[:10]}(bundle 共 {len(segments)} 段)")
    candidates = []
    for i, seg in enumerate(segments):
        sid = seg["segment_id"]
        candidates.append({
            "result_candidate_key": producer_name,
            "segment_id": sid,
            "source_hash": source_hashes[sid],
            "text": translations[i],
        })
    return {
        "schema_version": 1,
        "task_id": task["task_id"],
        "task_digest": bundle["task_digest"],
        "producer": {"type": "harness", "name": producer_name, "model": model},
        "candidates": candidates,
        "findings": list(findings or []),
        "recommended_candidate_keys": [producer_name],
        "completed_at": completed_at or datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path, help="prepare 产的 <id>.job.json")
    parser.add_argument("--translations", required=True, type=Path, help="<id>.zh.tsv(段号<TAB>译文)")
    parser.add_argument("--out", required=True, type=Path, help="输出 <id>.result.json")
    parser.add_argument("--names", type=Path, default=None, help="可选 <id>.names.tsv(日文名<TAB>篇内首次译名)")
    parser.add_argument("--producer", default="agent", help="执行器标识(claude-code/cursor-grok/...)")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    for name, val in (("--job", args.job), ("--translations", args.translations), ("--out", args.out)):
        if not str(val).strip():
            parser.error(f"{name} 不能为空")
    if args.names is not None and not args.names.is_file():
        parser.error(f"--names 不存在: {args.names}")
    bundle = json.loads(args.job.read_text(encoding="utf-8"))
    translations = parse_translations_tsv(args.translations.read_text(encoding="utf-8"), bundle)
    findings: List[Dict[str, Any]] = []
    if args.names is not None and args.names.is_file():
        local_targets = entity_harvest.parse_locked_names_tsv(args.names.read_text(encoding="utf-8"))
        translations, findings = entity_harvest.apply_locked_names(bundle, translations, local_targets)
    result = assemble_result(
        bundle,
        translations,
        producer_name=args.producer,
        model=args.model,
        findings=findings,
    )
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidates": len(result["candidates"]), "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
