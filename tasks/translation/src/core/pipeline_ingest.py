#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端批量编排:把一个用户的现有 source+bilingual 跑进新架构并发布、渲染。

逐文档串:revision → legacy candidates(既有译文=incumbent)→ deterministic QA → 保守择优 →
DocumentVersion → publish(current ref)→ render bilingual+zh。逐文档容错,产 manifest 报告。
不在此重新翻译(那是 translate-bundle→执行器→import-result 叠加新候选的后续)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from . import candidate_eval, legacy_import, source_identity as si, version_select
    from .artifact_store import ArtifactStore
    from .renderer import render_bilingual, render_zh
    from .task_export import ingest_revision
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import candidate_eval, legacy_import, source_identity as si, version_select
    from core.artifact_store import ArtifactStore
    from core.renderer import render_bilingual, render_zh
    from core.task_export import ingest_revision


def ingest_document(
    provider: str,
    source_path: Path,
    bilingual_path: Path,
    store: ArtifactStore,
    render_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """单文档全链。返回报告(不抛常规缺译异常;真实坏数据由 issues/status 反映)。"""
    source_path, bilingual_path = Path(source_path), Path(bilingual_path)
    rev = si.build_document_revision(provider, source_path)
    doc = rev["document_id"]
    report: Dict[str, Any] = {"document_id": doc, "segments": len(rev["segments"]), "status": "ok"}

    cands, atts, issues = legacy_import.build_legacy_candidates(provider, source_path, bilingual_path, "bilingual")
    report["candidates"] = len(cands)
    report["issues"] = issues

    ingest_revision(rev, store)
    if cands:
        store.put_many(doc, [*cands, *atts])

    segs = {s["segment_id"]: s for s in rev["segments"]}
    covered = {c["segment_id"] for c in cands}
    missing = [sid for sid in segs if sid not in covered]
    if missing:
        # 译文未覆盖全部 segment(截断/空译) → 不建可渲染版本,留报告(可后续重译补)
        report["status"] = "incomplete_coverage"
        report["missing_segments"] = len(missing)
        return report

    evals = [candidate_eval.evaluate_candidate(c, segs[c["segment_id"]]["source_text"]) for c in cands]
    store.put_many(doc, evals)
    evals_by_cand: Dict[str, List[Dict[str, Any]]] = {}
    for ev in evals:
        evals_by_cand.setdefault(ev["candidate_id"], []).append(ev)

    segments_input = [
        {"segment_id": c["segment_id"],
         "incumbent": {"candidate_id": c["candidate_id"], "evaluations": evals_by_cand[c["candidate_id"]]},
         "challengers": []}
        for c in cands
    ]
    recs = version_select.recommend_selection(segments_input)
    report["review_required"] = sum(1 for r in recs if r["outcome"] == "review_required")

    created_at = legacy_import._legacy_created_at(rev)
    version = version_select.build_document_version(rev, recs, "workflow", created_at)
    store.put_many(doc, [version])
    report["version_id"] = version["version_id"]
    # 批量 ingest 只建立 legacy 基线:已有 current ref(repair/人工选择/他 worker 发的更新版本)绝不回滚。
    current = store.current_ref(doc)
    if current is None:
        store.publish(doc, version["version_id"], expected_version_id=None)  # CAS:仅当无 current
        report["published"] = True
    elif current["version_id"] == version["version_id"]:
        report["published"] = True  # 幂等:已发布同一版本
    else:
        report["status"] = "ref_exists_kept"
        report["published"] = False
        report["current_version_id"] = current["version_id"]  # 保留既有(更新)版本,不回滚

    cands_by_id = {c["candidate_id"]: c for c in cands}
    translations = {sid: cands_by_id[cid]["text"] for sid, cid in version["selections"].items()}
    source_text = source_path.read_text(encoding="utf-8")
    if render_dir is not None:
        render_dir = Path(render_dir)
        render_dir.mkdir(parents=True, exist_ok=True)
        sid = doc.rsplit(":", 1)[-1]
        (render_dir / f"{sid}.bilingual.txt").write_text(render_bilingual(rev, source_text, translations), encoding="utf-8")
        (render_dir / f"{sid}.zh.txt").write_text(render_zh(rev, source_text, translations), encoding="utf-8")
        report["rendered"] = True
    return report


def ingest_directory(
    provider: str,
    source_dir: Path,
    bilingual_dir: Path,
    store_root: Path,
    render_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """遍历 source 目录,匹配同名 bilingual,逐文档跑(独立容错),产 manifest。"""
    source_dir, bilingual_dir, store_root = Path(source_dir), Path(bilingual_dir), Path(store_root)
    store = ArtifactStore(store_root)
    docs: List[Dict[str, Any]] = []
    for src in sorted(source_dir.glob("*.txt")):
        bil = bilingual_dir / src.name
        if not bil.is_file():
            docs.append({"source": src.name, "status": "skipped_no_bilingual"})
            continue
        try:
            docs.append(ingest_document(provider, src, bil, store, render_dir))
        except Exception as exc:  # 逐文档容错:坏数据不中断整批
            docs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    summary = {
        "total": len(docs),
        "published": sum(1 for d in docs if d.get("published")),
        "incomplete": sum(1 for d in docs if d.get("status") == "incomplete_coverage"),
        "skipped": sum(1 for d in docs if d.get("status") == "skipped_no_bilingual"),
        "errors": sum(1 for d in docs if d.get("status") == "error"),
    }
    manifest = {
        "provider": provider, "source_dir": str(source_dir), "bilingual_dir": str(bilingual_dir),
        "store_root": str(store_root), "summary": summary, "documents": docs,
    }
    out_dir = Path(render_dir) if render_dir is not None else store_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ingest_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=("pixiv", "fanbox"))
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--bilingual-dir", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path, help="持久 ArtifactStore 根目录")
    parser.add_argument("--render-dir", type=Path, default=None, help="渲染产物输出目录(可选)")
    args = parser.parse_args()
    # 空路径(如 Make 漏传 STORE=)不能静默落到 cwd 写一个 store。
    for name, val in (("--store", args.store), ("--source-dir", args.source_dir), ("--bilingual-dir", args.bilingual_dir)):
        if not str(val).strip() or str(val) == ".":
            parser.error(f"{name} 不能为空路径")
    manifest = ingest_directory(args.provider, args.source_dir, args.bilingual_dir, args.store, args.render_dir)
    print(json.dumps(manifest["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
