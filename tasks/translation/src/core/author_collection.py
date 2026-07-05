#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作者合集:把一个 creator 在各 per-work workspace 里已发布的 rendered 产物,按 source_id 顺序合并成
一本「作者名」命名的整本(zh + bilingual),可选复制到外部目录(如 Google Drive)。

每篇作品翻译时落在自己的 workspace `workspaces/<provider>-<source_id>/`,rendered 在其 `rendered/` 下。
本工具跨 workspace 收集同一 creator 的所有已发布篇(以 `store/refs/<provider>/<creator>/*.json` 为准),
复制 rendered 到一个临时合集目录,再用 `merge_author` 合成 `<author>.zh.txt` / `<author>.bilingual.txt`。
"""

from __future__ import annotations

import argparse
import glob
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .pipeline_ingest import merge_author
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.pipeline_ingest import merge_author

VARIANTS = ("zh", "bilingual")


def _published_sids(workspaces_root: Path, provider: str, creator_id: str) -> List[str]:
    refs = glob.glob(str(workspaces_root / "*" / "store" / "refs" / provider / creator_id / "*.json"))
    sids = {Path(r).stem for r in refs}
    return sorted(sids, key=lambda s: (int(s) if s.isdigit() else 0, s))


def build_collection(
    author_name: str, creator_id: str, *, workspaces_root: Path, out_dir: Path,
    provider: str = "pixiv", gdrive_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """收集 creator 已发布篇 → 合并成作者名整本。返回 {sids, missing, chapters, files, gdrive}。"""
    if not author_name.strip():
        raise ValueError("author_name 不能为空")
    workspaces_root = Path(workspaces_root)
    out_dir = Path(out_dir)
    sids = _published_sids(workspaces_root, provider, creator_id)
    if not sids:
        raise ValueError(f"{provider}:{creator_id} 没有已发布篇(workspaces 下无 refs)")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    missing: List[str] = []
    for sid in sids:
        found = False
        for var in VARIANTS:
            src = workspaces_root / f"{provider}-{sid}" / "rendered" / f"{sid}.{var}.txt"
            if src.is_file():
                shutil.copy(src, out_dir / f"{sid}.{var}.txt")
                found = True
        if not found:
            missing.append(sid)
    merged = merge_author(out_dir, author_name, sids)
    files: List[str] = []
    gdrive_files: List[str] = []
    for var in VARIANTS:
        fp = out_dir / f"{author_name}.{var}.txt"
        if fp.is_file():
            files.append(str(fp))
            if gdrive_dir is not None:
                gdrive_dir = Path(gdrive_dir)
                gdrive_dir.mkdir(parents=True, exist_ok=True)
                dst = gdrive_dir / f"{author_name}.{var}.txt"
                shutil.copy(fp, dst)
                gdrive_files.append(str(dst))
    return {
        "sids": sids,
        "missing": missing,
        "chapters": {k: v.get("chapters") for k, v in merged.items()},
        "files": files,
        "gdrive": gdrive_files,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--author", required=True, help="作者名(用作合集文件名,如 錆流浪)")
    p.add_argument("--creator", required=True, help="creator id(如 104039620)")
    p.add_argument("--provider", default="pixiv")
    p.add_argument("--workspaces-root", type=Path, default=Path("tasks/translation/data/workspaces"))
    p.add_argument("--out", type=Path, default=None, help="合集输出目录(默认 workspaces/_collection-<creator>)")
    p.add_argument("--gdrive", type=Path, default=None, help="可选:同时复制整本到此目录")
    args = p.parse_args()
    if not args.author.strip() or not args.creator.strip():
        p.error("--author 与 --creator 不能为空")
    out = args.out or (args.workspaces_root / f"_collection-{args.creator}")
    res = build_collection(args.author, args.creator, workspaces_root=args.workspaces_root,
                           out_dir=out, provider=args.provider, gdrive_dir=args.gdrive)
    import json
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["missing"]:
        print(f"⚠️ {len(res['missing'])} 篇缺 rendered: {res['missing'][:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
