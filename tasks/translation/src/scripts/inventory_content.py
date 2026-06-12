#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""存量内容库盘点：扫描 data 下的源/派生/打包产物，输出每作品形态与完成度报告。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from tasks.translation.src.core.run_state import TranslationStateStore
except ImportError:  # 直接以脚本运行时
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.run_state import TranslationStateStore

PLACEHOLDER_MARKER = TranslationStateStore.PLACEHOLDER_MARKER
FAILURE_MARKERS = TranslationStateStore.FAILURE_MARKERS

# 与翻译无关的工具/资产目录，不参与源目录判定
EXCLUDED_DIRS = {"name_maps", "prompt_styles", "samples"}
QUARANTINE_PATTERN = re.compile(r"(_broken_bak|_bak|_tmp)$")
DERIVED_TOKEN_PATTERN = re.compile(r"_(bilingual|zh)(_|$)")


def inspect_content(text: str) -> str:
    """复用 run_state 的标记语义：missing/partial/failed/complete(文件级)。"""
    if PLACEHOLDER_MARKER in text:
        return "partial"
    if any(marker in text for marker in FAILURE_MARKERS):
        return "failed"
    if not text.strip():
        # 与 TranslationStateStore.inspect_output 一致:文件存在但为空是 partial,
        # missing 只表示文件不存在
        return "partial"
    return "complete"


def _post_ids(directory: Path) -> List[str]:
    return sorted(p.stem for p in directory.glob("*.txt") if not p.name.endswith(".meta.json"))


def _is_source_dir(directory: Path, sibling_names: List[str]) -> bool:
    """源目录：派生命名(_bilingual/_zh)优先排除——即使目录残留 .meta.json 边车文件
    ;其余情况 .meta.json 是强信号,否则要求有 txt 且不是兄弟目录的派生。"""
    if directory.name in EXCLUDED_DIRS:
        return False
    if not any(directory.glob("*.txt")):
        return False
    if DERIVED_TOKEN_PATTERN.search(directory.name):
        return False
    if any(directory.glob("*.meta.json")):
        return True
    return not any(
        directory.name.startswith(f"{other}_") for other in sibling_names if other != directory.name
    )


def _inspect_derived_dir(derived: Path, source_posts: List[str]) -> Dict[str, Any]:
    statuses: Dict[str, int] = {}
    files = _post_ids(derived)
    for stem in files:
        try:
            text = (derived / f"{stem}.txt").read_text(encoding="utf-8")
            status = inspect_content(text)
        except OSError:
            status = "failed"
        statuses[status] = statuses.get(status, 0) + 1
    covered = sorted(set(files) & set(source_posts))
    extras = sorted(set(files) - set(source_posts))
    total = len(source_posts)
    if not source_posts:
        coverage = "unknown"
    elif len(covered) == total and statuses.get("complete", 0) == len(files) and not extras:
        coverage = "complete"
    elif covered:
        coverage = "partial"
    else:
        coverage = "disjoint"
    return {
        "name": derived.name,
        "variant": derived.name.split("_", 1)[1] if "_" in derived.name else "",
        "file_count": len(files),
        "covered": len(covered),
        "source_total": total,
        "extra_files": extras,
        "status_counts": statuses,
        "coverage": coverage,
        "quarantine_candidate": bool(QUARANTINE_PATTERN.search(derived.name)),
    }


def scan_root(root: Path) -> Dict[str, Any]:
    """扫描一个 collection 根(如 data/pixiv、data/fanbox)。"""
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    names = [d.name for d in dirs]
    sources = [d for d in dirs if _is_source_dir(d, names)]
    source_names = sorted((s.name for s in sources), key=len, reverse=True)

    entries: List[Dict[str, Any]] = []
    claimed: set[str] = {s.name for s in sources} | EXCLUDED_DIRS
    for source in sorted(sources, key=lambda p: p.name):
        posts = _post_ids(source)
        derived_dirs = []
        for d in dirs:
            if d.name == source.name or d.name in claimed:
                continue
            base = next((n for n in source_names if d.name.startswith(f"{n}_")), None)
            if base == source.name:
                derived_dirs.append(_inspect_derived_dir(d, posts))
                claimed.add(d.name)
        entries.append(
            {
                "source": source.name,
                "post_count": len(posts),
                "with_meta": sum(1 for p in posts if (source / f"{p}.meta.json").exists()),
                "derived": derived_dirs,
            }
        )

    orphan_dirs = [d.name for d in dirs if d.name not in claimed]
    return {"root": root.name, "sources": entries, "orphan_dirs": sorted(orphan_dirs)}


def scan_packaged(data_root: Path, source_names: List[str]) -> List[Dict[str, Any]]:
    """顶层散落的打包产物(<base>[_v2]_bilingual.txt / _zh.txt 等)。"""
    packaged = []
    for path in sorted(data_root.glob("*.txt")):
        match = re.match(r"^(.*?)(?:_v\d+)?_(bilingual|zh)\.txt$", path.name)
        if not match:
            continue
        base = match.group(1)
        packaged.append(
            {
                "file": path.name,
                "kind": match.group(2),
                "base": base,
                "matched_source": base if base in source_names else None,
            }
        )
    return packaged


def build_inventory(data_root: Path, collections: List[str]) -> Dict[str, Any]:
    roots = [scan_root(data_root / name) for name in collections if (data_root / name).is_dir()]
    all_sources = [s["source"] for r in roots for s in r["sources"]]
    quarantine = [
        f"{r['root']}/{d['name']}"
        for r in roots
        for s in r["sources"]
        for d in s["derived"]
        if d["quarantine_candidate"]
    ]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_root": str(data_root),
        "collections": roots,
        "packaged_top_level": scan_packaged(data_root, all_sources),
        "quarantine_candidates": quarantine,
    }


def summarize(inventory: Dict[str, Any]) -> str:
    lines = []
    for root in inventory["collections"]:
        lines.append(f"[{root['root']}] {len(root['sources'])} 个源目录")
        for s in root["sources"]:
            derived_desc = (
                ", ".join(f"{d['name']}({d['coverage']})" for d in s["derived"]) or "无派生"
            )
            lines.append(f"  {s['source']}: {s['post_count']} 篇 -> {derived_desc}")
        if root["orphan_dirs"]:
            lines.append(f"  孤儿目录: {', '.join(root['orphan_dirs'])}")
    lines.append(f"顶层打包产物: {len(inventory['packaged_top_level'])} 个")
    lines.append(
        "隔离候选: " + (", ".join(inventory["quarantine_candidates"]) or "无")
    )
    return "\n".join(lines)


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=base / "data")
    parser.add_argument(
        "--collections", nargs="+", default=["pixiv", "fanbox"], help="data 下要扫描的子目录"
    )
    parser.add_argument(
        "--output", type=Path, default=base / "logs" / "inventory" / "inventory.json"
    )
    args = parser.parse_args()

    if not args.data_root.is_dir():
        print(f"data root 不存在: {args.data_root}", file=sys.stderr)
        return 1

    inventory = build_inventory(args.data_root, args.collections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(summarize(inventory))
    print(f"\n报告: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
