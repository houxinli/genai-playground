#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""存量 QA 基线：对盘点出的全部 bilingual 派生目录跑 qa_gate 硬规则，汇总问题分布。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from tasks.translation.src.core.qa_gate import TranslationQAGate
    from tasks.translation.src.scripts.inventory_content import build_inventory
except ImportError:  # 直接以脚本运行时
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.qa_gate import TranslationQAGate
    from scripts.inventory_content import build_inventory


def _qa_files(
    gate: TranslationQAGate,
    file_pairs: List[tuple],
) -> Dict[str, Any]:
    """对 (output_path, source_path|None) 列表跑 gate 并聚合。"""
    issue_counts: Dict[str, int] = {}
    files_with_errors = 0
    for output_path, source_path in file_pairs:
        report = gate.run(output_path, source_path)
        if report.has_errors:
            files_with_errors += 1
        for issue in report.issues:
            key = f"{issue.code}:{issue.severity}"
            issue_counts[key] = issue_counts.get(key, 0) + 1
    return {
        "files": len(file_pairs),
        "files_with_errors": files_with_errors,
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def _qa_dir(
    gate: TranslationQAGate,
    derived_dir: Path,
    source_dir: Path,
) -> Dict[str, Any]:
    pairs = []
    for output_path in sorted(derived_dir.glob("*.txt")):
        source_path = source_dir / output_path.name
        pairs.append((output_path, source_path if source_path.exists() else None))
    entry = _qa_files(gate, pairs)
    entry["dir"] = derived_dir.name
    return entry


def build_baseline(data_root: Path, collections: List[str]) -> Dict[str, Any]:
    inventory = build_inventory(data_root, collections)
    gate = TranslationQAGate()
    results: List[Dict[str, Any]] = []
    for collection in inventory["collections"]:
        root_dir = data_root / collection["root"]
        for source in collection["sources"]:
            source_dir = root_dir / source["source"]
            for derived in source["derived"]:
                if "bilingual" not in derived["variant"]:
                    continue
                if derived["quarantine_candidate"]:
                    continue
                entry = _qa_dir(gate, root_dir / derived["name"], source_dir)
                entry["collection"] = collection["root"]
                entry["source"] = source["source"]
                results.append(entry)

    # 顶层打包的 bilingual 产物同样纳入基线(review: PR #13);打包文件无逐篇源,gate 走无源路径
    for item in inventory["packaged_top_level"]:
        if item["kind"] != "bilingual":
            continue
        entry = _qa_files(gate, [(data_root / item["file"], None)])
        entry["dir"] = item["file"]
        entry["collection"] = "(packaged)"
        entry["source"] = item["matched_source"] or item["base"]
        results.append(entry)

    total_issues: Dict[str, int] = {}
    for entry in results:
        for key, count in entry["issue_counts"].items():
            total_issues[key] = total_issues.get(key, 0) + count
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_root": str(data_root),
        "dirs": results,
        "totals": {
            "dirs": len(results),
            "files": sum(e["files"] for e in results),
            "files_with_errors": sum(e["files_with_errors"] for e in results),
            "issue_counts": dict(sorted(total_issues.items())),
        },
    }


def summarize(baseline: Dict[str, Any]) -> str:
    totals = baseline["totals"]
    lines = [
        f"QA 基线: {totals['dirs']} 个 bilingual 目录, {totals['files']} 个文件, "
        f"{totals['files_with_errors']} 个文件有 error 级问题"
    ]
    for key, count in totals["issue_counts"].items():
        lines.append(f"  {key}: {count}")
    worst = sorted(baseline["dirs"], key=lambda e: -e["files_with_errors"])[:5]
    lines.append("问题最多的目录:")
    for entry in worst:
        lines.append(
            f"  {entry['collection']}/{entry['dir']}: "
            f"{entry['files_with_errors']}/{entry['files']} 文件有 error"
        )
    return "\n".join(lines)


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=base / "data")
    parser.add_argument("--collections", nargs="+", default=["pixiv", "fanbox"])
    parser.add_argument(
        "--output", type=Path, default=base / "logs" / "inventory" / "qa_baseline.json"
    )
    args = parser.parse_args()

    if not args.data_root.is_dir():
        print(f"data root 不存在: {args.data_root}", file=sys.stderr)
        return 1

    baseline = build_baseline(args.data_root, args.collections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(summarize(baseline))
    print(f"\n报告: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
