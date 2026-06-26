#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则影响分析(#83 P1b-2b §8.3):译名/规则变化后,找出已发布版本里用了旧译名的 segment。

**只读、不改写历史发布版本**——扫描每个文档的 current ref → DocumentVersion → 选中候选的译文,
报告含有旧译名(stale_text)的 segment。产出即"受影响 segment 列表",驱动后续重译(新候选/新版本由
执行器走正常翻译流程产生,本工具不动既有 version)。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .artifact_store import ArtifactStore
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.artifact_store import ArtifactStore


def _iter_published(store: ArtifactStore):
    """遍历 store 里所有有 current ref 的文档 → (document_id, version_id)。"""
    refs_root = store.root / "refs"
    if not refs_root.is_dir():
        return
    for ref_file in sorted(refs_root.rglob("*.json")):
        provider, creator_id, source_id = ref_file.parts[-3], ref_file.parts[-2], ref_file.stem
        doc = f"{provider}:{creator_id}:{source_id}"
        current = store.current_ref(doc)
        if current and current.get("version_id"):
            yield doc, current["version_id"]


def find_affected(store_root: Path, stale_text: str, *, scope: Optional[str] = None) -> List[Dict[str, Any]]:
    """已发布版本里译文含 stale_text 的 segment。scope 可选:document_id 前缀(如 `pixiv:104039620`)过滤。"""
    if not stale_text:
        raise ValueError("stale_text 不能为空")
    store = ArtifactStore(Path(store_root))
    affected: List[Dict[str, Any]] = []
    for doc, version_id in _iter_published(store):
        if scope and not doc.startswith(scope):
            continue
        version = store.get("document-version", doc, version_id)
        if not version:
            continue
        cands = {c["candidate_id"]: c for c in store.list_shard("candidate", doc)}
        for seg_id, cid in version.get("selections", {}).items():
            cand = cands.get(cid)
            if cand and stale_text in cand.get("text", ""):
                affected.append({
                    "document_id": doc,
                    "version_id": version_id,
                    "segment_id": seg_id,
                    "candidate_id": cid,
                    "snippet": cand["text"][:80],
                })
    return affected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--stale", required=True, help="旧译名/要排查的串(如某个被废弃的人名译法)")
    parser.add_argument("--scope", default=None, help="可选 document_id 前缀,如 pixiv:104039620")
    args = parser.parse_args()
    if not str(args.store).strip() or not args.stale.strip():
        parser.error("--store 与 --stale 不能为空")
    affected = find_affected(args.store, args.stale, scope=args.scope)
    print(json.dumps({"stale": args.stale, "affected": len(affected), "segments": affected},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
