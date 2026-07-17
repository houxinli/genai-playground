#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核验陪读产物 + 写 provenance(轻量版本隔离)。

用法:
    python verify_study.py <bilingual.txt> <study.txt> [--source <原文.txt>] [--model NAME]

核验:①行数与 bilingual 完全一致 ②非日文行(中文译文/front-matter/空行)一字未改。
provenance(<study>.meta.json)分开记两个哈希,因为**注解只依赖原文、和译文无关**:
- `source_sha256`(原文 txt 哈希):注解的真实输入。原文变了才需**重新注解**(几乎不发生)。
- `bilingual_sha256`(源+译交织):陪读产物直接嵌了当时的译文。译文更新→bilingual 变→只需
  **重拼**(把新译文和已有注解交织,不调 LLM),不必重注解。
--check-fresh 据此区分 FRESH / RE-RENDER(译文变) / STALE(原文变)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_KANA = re.compile(r"[぀-ゟ゠-ヿ]")


def verify(bilingual: Path, study: Path, source: Path = None, model: str = "unknown") -> int:
    src = bilingual.read_text(encoding="utf-8").split("\n")
    out = study.read_text(encoding="utf-8").split("\n")
    if len(src) != len(out):
        print(f"❌ 行数不一致: bilingual={len(src)} study={len(out)}")
        return 1
    changed_non_ja = [i for i, (a, b) in enumerate(zip(src, out)) if a != b and not _KANA.search(a)]
    if changed_non_ja:
        i = changed_non_ja[0]
        print(f"❌ 非日文行被改动 {len(changed_non_ja)} 处,首个 行{i}: [{src[i][:40]}] -> [{out[i][:40]}]")
        return 1
    annotated = sum(1 for a, b in zip(src, out) if a != b)
    meta = {
        "schema_version": 2,
        "kind": "study",
        "based_on_bilingual": bilingual.name,
        # 注解的真实输入是原文;译文只是产物里嵌的一份快照。分开记两个哈希。
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest() if source and source.is_file() else None,
        "bilingual_sha256": hashlib.sha256(bilingual.read_bytes()).hexdigest(),
        "model": model,
        "annotated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "lines": len(src),
        "annotated_lines": annotated,
        "verified": True,
    }
    meta_path = study.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ OK: {len(src)} 行, {annotated} 行注解, provenance → {meta_path.name}")
    return 0


def check_fresh(bilingual: Path, study: Path, source: Path = None) -> int:
    """新鲜度:原文变→STALE(重注解);仅译文变→RE-RENDER(重拼);都没变→FRESH。"""
    meta_path = study.with_suffix(".meta.json")
    if not meta_path.is_file():
        print(f"❌ 缺 provenance: {meta_path.name}")
        return 1
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if source and source.is_file() and meta.get("source_sha256"):
        if hashlib.sha256(source.read_bytes()).hexdigest() != meta["source_sha256"]:
            print("❌ STALE:原文已变 → 需**重新注解**")
            return 1
    if hashlib.sha256(bilingual.read_bytes()).hexdigest() != meta.get("bilingual_sha256"):
        print("⚠️ RE-RENDER:译文已更新(原文未变)→ 只需**重拼**(注解仍有效,无需调 LLM)")
        return 2
    print(f"✅ FRESH: 陪读版仍对应当前原文与译文(model={meta.get('model')})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bilingual", type=Path)
    p.add_argument("study", type=Path)
    p.add_argument("--source", type=Path, default=None, help="原文 txt(注解真实输入,记 source_sha256)")
    p.add_argument("--model", default="unknown", help="产出模型名(记入 provenance)")
    p.add_argument("--check-fresh", action="store_true", help="只核验新鲜度(不重写 meta)")
    args = p.parse_args()
    if args.check_fresh:
        return check_fresh(args.bilingual, args.study, args.source)
    return verify(args.bilingual, args.study, args.source, args.model)


if __name__ == "__main__":
    raise SystemExit(main())
