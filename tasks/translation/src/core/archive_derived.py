#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史派生目录归档(#62):**先证已迁入 store,再隔离(绝不 hard-delete)**。

`data/<provider>/<creator>_<suffix>/` 下堆积的 `_bilingual`/`_zh`/`_v2`/`_namefix`/`_trial` 等
历史派生目录,在新架构里职责由 Artifact Store + DocumentVersion + 渲染派生物承担。清理须守 #62 硬 gate:

- **可归档判定**:目录每篇 source 的 legacy candidate **已在 store** 且其 **revision 在 store**(integrity);
  且该目录**不是源入口目录**(裸 `<creator>/`,被生产直读)。任一不满足 → 拒绝归档并给出原因。
- **归档=移入隔离区 + 写 manifest**(原路径/来源/post 列表/时间),**永不物理删除**——保留回溯(参考 #10)。

data 现无持久 store 时,真实派生目录一律 gate 不通过 → 本工具拒绝归档,只能 `--report` 盘点。
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import legacy_import
    from .artifact_store import ArtifactStore
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import legacy_import
    from core.artifact_store import ArtifactStore

# 历史派生目录后缀(源入口目录是裸 <creator>,无这些后缀)。
DERIVED_SUFFIXES = ("_bilingual_fixed", "_bilingual_v2", "_bilingual", "_zh", "_v2", "_namefix", "_trial")


def parse_derived_name(dir_name: str) -> Optional[Tuple[str, str]]:
    """`50235390_bilingual_v2` → (creator_id, suffix);裸 `50235390`(源入口)→ None。"""
    for suf in DERIVED_SUFFIXES:
        if dir_name.endswith(suf) and len(dir_name) > len(suf):
            return dir_name[: -len(suf)], suf
    return None


def post_ids(derived_dir: Path) -> List[str]:
    return sorted(p.stem for p in Path(derived_dir).glob("*.txt"))


def is_archivable(
    derived_dir: Path, store: ArtifactStore, provider: str, source_dir: Path,
    *, legacy_label: str = "bilingual",
) -> Tuple[bool, List[str]]:
    """守 #62 gate(内容核验,非「有就算」):**从本目录重建 legacy candidate,逐个核验其内容寻址
    id 已在 store**,才证明这一篇的译文确实完整迁入(全覆盖)。任一篇缺源文件 / 重建失败 / 有
    candidate 未在 store → 拒绝。仅靠「doc 下有任意 candidate」不够(可能是别轮 executor 候选,
    或部分导入)——Codex #115。

    返回 (可归档, 原因列表)。原因非空 ⇒ 不可归档。
    """
    derived_dir, source_dir = Path(derived_dir), Path(source_dir)
    reasons: List[str] = []
    parsed = parse_derived_name(derived_dir.name)
    if parsed is None:
        return False, [f"{derived_dir.name}: 非派生目录(疑似源入口),拒绝归档"]
    creator_id, _suffix = parsed
    posts = post_ids(derived_dir)
    if not posts:
        return False, [f"{derived_dir.name}: 空目录或无 .txt,跳过(不归档)"]
    for post in posts:
        doc = f"{provider}:{creator_id}:{post}"
        src = source_dir / f"{post}.txt"
        if not src.is_file():
            reasons.append(f"{post}: 缺源文件 {src.name},无法核验迁入")
            continue
        if not store.list_shard("document-revision", doc):
            reasons.append(f"{post}: store 无 revision(integrity 未过)")
            continue
        try:
            cands, _atts, _issues = legacy_import.build_legacy_candidates(
                provider, src, derived_dir / f"{post}.txt", legacy_label)
        except Exception as exc:  # 无法重建 → 不可核验 → 不归档
            reasons.append(f"{post}: 无法重建 legacy candidate({type(exc).__name__}),不可核验")
            continue
        if not cands:
            reasons.append(f"{post}: 重建出 0 candidate,不可核验")
            continue
        missing = [c["candidate_id"] for c in cands if not store.exists("candidate", doc, c["candidate_id"])]
        if missing:
            reasons.append(f"{post}: {len(missing)}/{len(cands)} 个 legacy candidate 未在 store(未完整迁入)")
    return (not reasons), reasons


def quarantine_dir(derived_dir: Path, quarantine_root: Path, provider: str, *,
                   reason: str = "archived: 内容已迁入 store(#62)") -> Dict[str, Any]:
    """移入隔离区 + 写 manifest。**只移动不删除**;目标已存在则报错(不覆盖)。"""
    derived_dir, quarantine_root = Path(derived_dir), Path(quarantine_root)
    dest = quarantine_root / derived_dir.name
    if dest.exists():
        raise FileExistsError(f"隔离目标已存在,拒绝覆盖: {dest}")
    parsed = parse_derived_name(derived_dir.name)
    entry = {
        "original_path": str(derived_dir),
        "archived_to": str(dest),
        "provider": provider,
        "creator_id": parsed[0] if parsed else None,
        "suffix": parsed[1] if parsed else None,
        "posts": post_ids(derived_dir),
        "reason": reason,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
    quarantine_root.mkdir(parents=True, exist_ok=True)
    shutil.move(str(derived_dir), str(dest))  # 移动,非删除
    manifest_path = quarantine_root / "archive_manifest.jsonl"
    with manifest_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def report(data_root: Path, collections: List[str]) -> Dict[str, Any]:
    """只读盘点:列出各 collection 下的派生目录(类型/篇数),不触碰任何文件。"""
    data_root = Path(data_root)
    dirs: List[Dict[str, Any]] = []
    for coll in collections:
        base = data_root / coll
        if not base.is_dir():
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            parsed = parse_derived_name(d.name)
            if parsed is None:
                continue
            dirs.append({"path": str(d), "provider": coll, "creator_id": parsed[0],
                         "suffix": parsed[1], "posts": len(post_ids(d))})
    return {"derived_dirs": dirs, "count": len(dirs)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    rep = sub.add_parser("report", help="只读盘点派生目录")
    rep.add_argument("--data-root", required=True, type=Path)
    rep.add_argument("--collections", nargs="+", default=["pixiv", "fanbox"])
    arc = sub.add_parser("archive", help="gated 归档(内容须已迁入 store;只隔离不删)")
    arc.add_argument("--dir", required=True, type=Path)
    arc.add_argument("--store", required=True, type=Path)
    arc.add_argument("--provider", required=True)
    arc.add_argument("--source-dir", required=True, type=Path, help="源 TXT 目录(核验迁入用)")
    arc.add_argument("--quarantine", required=True, type=Path)
    args = parser.parse_args()

    if args.cmd == "report":
        print(json.dumps(report(args.data_root, args.collections), ensure_ascii=False, indent=2))
        return 0
    store = ArtifactStore(args.store)
    ok, reasons = is_archivable(args.dir, store, args.provider, args.source_dir)
    if not ok:
        print(json.dumps({"archived": False, "reasons": reasons}, ensure_ascii=False, indent=2))
        return 1  # gate 未过:拒绝归档
    entry = quarantine_dir(args.dir, args.quarantine, args.provider)
    print(json.dumps({"archived": True, "manifest": entry}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
