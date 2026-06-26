#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""紧凑译文 → result.json 组装(#134):让 agent 只产译文,机械的身份回填交给 harness。

agent 翻大文档时若逐段写完整 result.json(每段抄 segment_id + 64 位 source_hash + candidate_key),
工具调用与输出量都会爆(Cursor 每轮 25/200 上限)。紧凑路径:agent 只写一个 `<id>.zh.tsv`——
每行 `段号<TAB>中文译文`(段号 = bundle.segments 的 0 基序号);本模块从 bundle 回填
segment_id/source_hash/task_digest/producer,产出 schema 合法 result.json。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def parse_translations_tsv(content: str) -> Dict[int, str]:
    """解析 `段号<TAB>译文` 文本 → {index: text}。译文按 TAB 后原样保留(可空=拒译);
    空行跳过;段号非整数 / 重复 → 报错。"""
    out: Dict[int, str] = {}
    for lineno, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        if "\t" not in line:
            raise ValueError(f"第 {lineno} 行缺 TAB 分隔(应为 `段号<TAB>译文`): {line!r}")
        idx_str, _, text = line.partition("\t")
        try:
            idx = int(idx_str.strip())
        except ValueError:
            raise ValueError(f"第 {lineno} 行段号不是整数: {idx_str!r}")
        if idx in out:
            raise ValueError(f"段号 {idx} 重复(第 {lineno} 行)")
        out[idx] = text
    return out


def assemble_result(
    bundle: Dict[str, Any], translations: Dict[int, str], *,
    producer_name: str = "agent", model: Optional[str] = None, completed_at: Optional[str] = None,
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
        "findings": [],
        "recommended_candidate_keys": [producer_name],
        "completed_at": completed_at or datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path, help="prepare 产的 <id>.job.json")
    parser.add_argument("--translations", required=True, type=Path, help="<id>.zh.tsv(段号<TAB>译文)")
    parser.add_argument("--out", required=True, type=Path, help="输出 <id>.result.json")
    parser.add_argument("--producer", default="agent", help="执行器标识(claude-code/cursor-grok/...)")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    for name, val in (("--job", args.job), ("--translations", args.translations), ("--out", args.out)):
        if not str(val).strip():
            parser.error(f"{name} 不能为空")
    bundle = json.loads(args.job.read_text(encoding="utf-8"))
    translations = parse_translations_tsv(args.translations.read_text(encoding="utf-8"))
    result = assemble_result(bundle, translations, producer_name=args.producer, model=args.model)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidates": len(result["candidates"]), "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
