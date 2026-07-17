#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核验陪读产物 + 写 provenance(轻量版本隔离)。

用法:
    python verify_study.py <bilingual.txt> <study.txt> [--model NAME]

核验:①行数与 bilingual 完全一致 ②非日文行(中文译文/front-matter/空行)一字未改。
provenance:通过则写 <study>.meta.json,记录 based_on_sha256(源 bilingual 内容哈希)、
model、annotated_at、行数/注解行数。based_on_sha256 让新鲜度可核验——bilingual 若重新发布
(哈希变了),陪读版即判定 stale、需重跑。这是 study.txt 没有 ArtifactStore 版本隔离时的替代。
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


def verify(bilingual: Path, study: Path, model: str = "unknown") -> int:
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
    based_on = hashlib.sha256(bilingual.read_bytes()).hexdigest()
    meta = {
        "schema_version": 1,
        "kind": "study",
        "based_on_bilingual": bilingual.name,
        "based_on_sha256": based_on,
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


def check_fresh(bilingual: Path, study: Path) -> int:
    """独立新鲜度核验:比较 study.meta.json 记录的源哈希与当前 bilingual。"""
    meta_path = study.with_suffix(".meta.json")
    if not meta_path.is_file():
        print(f"❌ 缺 provenance: {meta_path.name}(陪读未经核验/未记录来源)")
        return 1
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    now = hashlib.sha256(bilingual.read_bytes()).hexdigest()
    if meta.get("based_on_sha256") != now:
        print(f"❌ STALE: bilingual 已变(哈希不符),陪读版需重跑")
        return 1
    print(f"✅ FRESH: 陪读版仍对应当前 bilingual(model={meta.get('model')}, at={meta.get('annotated_at')})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bilingual", type=Path)
    p.add_argument("study", type=Path)
    p.add_argument("--model", default="unknown", help="产出模型名(记入 provenance)")
    p.add_argument("--check-fresh", action="store_true", help="只核验新鲜度(不重写 meta)")
    args = p.parse_args()
    if args.check_fresh:
        return check_fresh(args.bilingual, args.study)
    return verify(args.bilingual, args.study, args.model)


if __name__ == "__main__":
    raise SystemExit(main())
