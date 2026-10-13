#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补被内容策略拦截而留空的 `metadata.tags` 行。

cursor-agent 对含 `ロリ爆乳`/`ロリ巨乳` 的标签行会整行拒绝,退档阶梯走完仍为空,
于是整篇停在 unresolved(空候选阻断建版)。26 篇队列里同一模式出现了 5 次。
标签行本质是查表而不是翻译:`原词 / 中文`,译法在全库已发布作品里早已固定。

口径:词典 = 所有已发布 tags 行里 `原词 / 中文` 的最高频译法。**词典外的标签不猜**,
原样报告并拒绝写入;确需发布时用 `--gloss 原词=译法` 显式给出,由人承担含义。
只填空行,绝不覆盖已有译文。

用法:
    make fill-tags SID=27298835 [GLOSS='インピオ=因皮奥(音译,待确认)']
    之后照常 MODE=finish 重新发布。
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def build_glossary(workspaces_root: Path) -> Dict[str, str]:
    freq: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for tsv in workspaces_root.glob("*/results/*.zh.tsv"):
        for line in tsv.open(encoding="utf-8"):
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 2 or not cols[-1].startswith("[") or " / " not in cols[-1]:
                continue
            for part in cols[-1].strip("[]").split(", "):
                if " / " in part:
                    src, zh = part.split(" / ", 1)
                    if zh.strip():
                        freq[src.strip()][zh.strip()] += 1
    return {k: v.most_common(1)[0][0] for k, v in freq.items()}


def render_tags(source_text: str, glossary: Dict[str, str]) -> Tuple[Optional[str], List[str]]:
    tags = [t.strip() for t in source_text.strip().strip("[]").split(",") if t.strip()]
    unknown = [t for t in tags if t not in glossary]
    if unknown:
        return None, unknown
    return "[" + ", ".join(f"{t} / {glossary[t]}" for t in tags) + "]", []


def fill(tsv_path: Path, job_path: Path, glossary: Dict[str, str]) -> Tuple[int, List[str]]:
    """返回 (填了几行, 词典外标签)。有词典外标签时该行不写。"""
    segments = json.loads(job_path.read_text(encoding="utf-8"))["segments"]
    out, filled, unknown_all = [], 0, []
    for line in tsv_path.open(encoding="utf-8"):
        cols = line.rstrip("\n").split("\t")
        if len(cols) >= 2 and cols[-1] == "" and segments[int(cols[0])]["kind"] == "metadata.tags":
            text, unknown = render_tags(segments[int(cols[0])]["source_text"], glossary)
            if text is None:
                unknown_all += unknown
            else:
                cols[-1] = text
                filled += 1
        out.append("\t".join(cols) + "\n")
    if filled:
        tsv_path.write_text("".join(out), encoding="utf-8")
    return filled, unknown_all


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sid", required=True)
    ap.add_argument("--workspaces-root", type=Path, default=Path("tasks/translation/data/workspaces"))
    ap.add_argument("--workspace", type=Path, help="默认 <workspaces-root>/pixiv-<sid>")
    ap.add_argument("--gloss", action="append", default=[], metavar="原词=译法")
    args = ap.parse_args()

    ws = args.workspace or args.workspaces_root / f"pixiv-{args.sid}"
    glossary = build_glossary(args.workspaces_root)
    glossary.update(dict(g.split("=", 1) for g in args.gloss))
    filled, unknown = fill(ws / "results" / f"{args.sid}.zh.tsv",
                           ws / "jobs" / f"{args.sid}.job.json", glossary)
    if unknown:
        print(f"{args.sid}: 词典外标签 {sorted(set(unknown))},未写入;用 --gloss 原词=译法 显式给出", file=sys.stderr)
        return 1
    print(f"{args.sid}: 补了 {filled} 行 tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
