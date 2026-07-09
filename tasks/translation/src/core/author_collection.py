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
    from .epub_build import build_epub
    from .pipeline_ingest import _chapter_title, _sid_sort_key, merge_author
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.epub_build import build_epub
    from core.pipeline_ingest import _chapter_title, _sid_sort_key, merge_author

VARIANTS = ("zh", "bilingual")


_COLLECTION_SUFFIXES = (".txt", ".epub")


def _guard_out_dir(out_dir: Path, workspaces_root: Path) -> None:
    """rmtree 前置守卫(Codex #143 P1):out_dir 只允许是"专用合集目录"。
    拒绝:与 workspaces_root 相同或为其祖先(会清掉全部 per-work 产物),或已存在但含
    子目录/非合集文件(说明指向了别的东西,如 rendered、per-work workspace、外部同步目录)。
    注:合集目录默认就在 workspaces_root 下(`_collection-<creator>`),位于其内是合法的。"""
    out_r = out_dir.resolve()
    ws_r = workspaces_root.resolve()
    if out_r == ws_r or out_r in ws_r.parents:
        raise ValueError(f"out_dir 不能等于或包含 workspaces_root: {out_dir}")
    if out_dir.exists():
        if not out_dir.is_dir():
            raise ValueError(f"out_dir 已存在且不是目录: {out_dir}")
        for entry in out_dir.iterdir():
            if entry.is_dir() or entry.suffix not in _COLLECTION_SUFFIXES:
                raise ValueError(
                    f"out_dir 已存在且含非合集内容({entry.name}),拒绝清空: {out_dir}")


def _published_sids(workspaces_root: Path, provider: str, creator_id: str) -> Dict[str, Path]:
    """已发布 sid → 所属 workspace 根(从 ref 文件位置反推:<ws>/store/refs/<provider>/<creator>/<sid>.json)。
    同时兼容 per-work(`pixiv-<sid>/`)与 per-creator(`pixiv-<creator>/`)两种布局——
    rendered 都在各自 workspace 的 `rendered/` 下。"""
    refs = glob.glob(str(workspaces_root / "*" / "store" / "refs" / provider / creator_id / "*.json"))
    sid2ws = {Path(r).stem: Path(r).parents[4] for r in refs}
    return dict(sorted(sid2ws.items(), key=lambda kv: (int(kv[0]) if kv[0].isdigit() else 0, kv[0])))


def build_collection(
    author_name: str, creator_id: str, *, workspaces_root: Path, out_dir: Path,
    provider: str = "pixiv", gdrive_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """收集 creator 已发布篇 → 合并成作者名整本。返回 {sids, missing, chapters, files, gdrive}。"""
    if not author_name.strip():
        raise ValueError("author_name 不能为空")
    workspaces_root = Path(workspaces_root)
    out_dir = Path(out_dir)
    sid2ws = _published_sids(workspaces_root, provider, creator_id)
    sids = list(sid2ws)
    if not sids:
        raise ValueError(f"{provider}:{creator_id} 没有已发布篇(workspaces 下无 refs)")
    _guard_out_dir(out_dir, workspaces_root)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    missing: List[str] = []
    for sid, ws in sid2ws.items():
        found = False
        for var in VARIANTS:
            src = ws / "rendered" / f"{sid}.{var}.txt"
            if src.is_file():
                shutil.copy(src, out_dir / f"{sid}.{var}.txt")
                found = True
        if not found:
            missing.append(sid)
    merged = merge_author(out_dir, author_name, sids)
    epubs = _build_epubs(out_dir, author_name, sids)
    files: List[str] = []
    gdrive_files: List[str] = []
    for var in VARIANTS:
        for name in (f"{author_name}.{var}.txt", f"{author_name}.{var}.epub"):
            fp = out_dir / name
            if fp.is_file():
                files.append(str(fp))
                if gdrive_dir is not None:
                    gdrive_dir = Path(gdrive_dir)
                    gdrive_dir.mkdir(parents=True, exist_ok=True)
                    dst = gdrive_dir / name
                    shutil.copy(fp, dst)
                    gdrive_files.append(str(dst))
    return {
        "sids": sids,
        "missing": missing,
        "chapters": {k: v.get("chapters") for k, v in merged.items()},
        "epub_chapters": epubs,
        "files": files,
        "gdrive": gdrive_files,
    }


def _build_epubs(out_dir: Path, author_name: str, sids: List[str]) -> Dict[str, int]:
    """每个 variant 产 `<author>.<var>.epub`(显式 TOC,阅读器不再从 txt 猜章节)。
    章节与 merge_author 同源:按 source_id 升序,标题取渲染文件的中文 title。"""
    out: Dict[str, int] = {}
    for var in VARIANTS:
        chapters = []
        for sid in sorted(set(sids), key=_sid_sort_key):
            f = out_dir / f"{sid}.{var}.txt"
            if not f.is_file():
                continue
            content = f.read_text(encoding="utf-8").rstrip("\n")
            title = _chapter_title(content) or sid
            chapters.append((f"第{len(chapters) + 1}章 {title}", content))
        if chapters:
            build_epub(out_dir / f"{author_name}.{var}.epub", author_name, author_name, chapters)
            out[var] = len(chapters)
    return out


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
