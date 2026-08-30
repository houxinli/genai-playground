#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""翻译覆盖率报告:哪些**已下载的源**至今没有发布译文。

`provenance_report.py` 只看已发布的篇——它回答"这篇谁翻的",看不见从没进过流水线的篇。
pixiv:9425701:18137868 就是这样漏了几个月:下载器的 YAML 转义 bug 让它连 prepare 都进不去,
而所有报表都从 store 出发,没有源那一侧的对照,于是"少了一篇"永远没人发现。

口径:以 `data/<provider>/<creator>/<id>.txt` 为分母,以任一 workspace 的
`store/refs/<provider>/<creator>/<id>.json`(current ref)为分子。缺 ref = 未发布译文。
顺带对未发布的篇跑一次 front matter 解析,把"下载就坏了"和"只是还没翻"分开。

用法:
    make coverage                      # 全部 provider/creator
    make coverage PROVIDER=pixiv CREATOR=9425701
    make coverage FORMAT=json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from ..core.source_identity import parse_source
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.source_identity import parse_source


def published_ids(provider: str, workspaces_root: Path) -> set:
    """该 provider 下所有已发布的 source_id(跨 workspace、跨 creator 目录)。

    不按 creator 收窄:同一作品会出现在多个 creator 目录里(`pixiv_mini` 是
    50235390 的取样别名),而 pixiv novel_id / fanbox post_id 在 provider 内本就唯一,
    按 (provider, source_id) 判定已发布才不会把别名目录误报成"从没翻过"。
    """
    return {ref.stem for ref in workspaces_root.glob(f"*/store/refs/{provider}/*/*.json")}


PROVIDERS = ("pixiv", "fanbox")

# data/<provider>/ 下混着一堆历史派生目录:里面同样是带 front matter 的 `<id>.txt`,
# 但那是译文/实验产物不是源,内容上无法与源区分,只能按目录名排除。
# 真实 creator id 里带这些词时用 --creator 指名扫描。
_DERIVED_MARKERS = ("_bilingual", "_trial", "_namefix", "_namegloss", "_zh", "_v2", "name_maps")


def is_source_root(creator_dir: Path) -> bool:
    return not any(m in creator_dir.name for m in _DERIVED_MARKERS)


def creator_sources(creator_dir: Path) -> List[Path]:
    """所有 `<数字 id>.txt`。

    不要求 `<id>.meta.json` 存在——浏览器脚本下载的那批只落了 txt,若以 meta 为准,
    这些篇会整体从分母里消失,恰好瞒掉本报告要抓的那类漏网。
    """
    return sorted(p for p in creator_dir.glob("*.txt") if p.stem.isdigit())


def scan(data_root: Path, workspaces_root: Path,
         provider: str = "", creator: str = "") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    providers = [data_root / provider] if provider else \
        [data_root / name for name in PROVIDERS]
    for prov_dir in providers:
        if not prov_dir.is_dir():
            continue
        creators = [prov_dir / creator] if creator else sorted(
            c for c in prov_dir.iterdir() if c.is_dir() and is_source_root(c))
        done = published_ids(prov_dir.name, workspaces_root)
        for creator_dir in creators:
            sources = creator_sources(creator_dir)
            if not sources:
                continue
            missing = []
            for src in sources:
                if src.stem in done:
                    continue
                try:
                    parse_source(src)
                    reason = "untranslated"
                except Exception as exc:  # noqa: BLE001 — 任何解析失败都算"源坏了"
                    reason = f"unparseable: {type(exc).__name__}: {exc}"
                missing.append({
                    "source_id": src.stem,
                    "chars": len(src.read_text(encoding="utf-8")),
                    "reason": reason,
                })
            rows.append({
                "provider": prov_dir.name,
                "creator": creator_dir.name,
                "downloaded": len(sources),
                "published": len([s for s in sources if s.stem in done]),
                "missing": sorted(missing, key=lambda m: -m["chars"]),
            })
    return rows


def render_table(rows: List[Dict[str, Any]]) -> str:
    out: List[str] = []
    total_missing = 0
    for r in sorted(rows, key=lambda r: -len(r["missing"])):
        gap = len(r["missing"])
        total_missing += gap
        flag = "" if gap == 0 else f"   ← 缺 {gap}"
        out.append(f"{r['provider']}:{r['creator']:<12} 已下载 {r['downloaded']:>4}  "
                   f"已发布 {r['published']:>4}{flag}")
        for m in r["missing"]:
            note = "" if m["reason"] == "untranslated" else f"  [{m['reason'][:60]}]"
            out.append(f"      {m['source_id']:<12} {m['chars']:>7} 字{note}")
    out.append("")
    out.append(f"合计未发布译文: {total_missing} 篇 / 已下载 {sum(r['downloaded'] for r in rows)} 篇")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider", default="")
    ap.add_argument("--creator", default="")
    ap.add_argument("--data-root", type=Path, default=Path("tasks/translation/data"))
    ap.add_argument("--workspaces-root", type=Path,
                    default=Path("tasks/translation/data/workspaces"))
    ap.add_argument("--format", choices=("table", "json"), default="table")
    args = ap.parse_args()
    rows = scan(args.data_root, args.workspaces_root, args.provider, args.creator)
    print(json.dumps(rows, ensure_ascii=False, indent=2) if args.format == "json"
          else render_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
