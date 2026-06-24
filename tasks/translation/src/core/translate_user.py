#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translate-user:通用端到端编排——一个作者目录 → 实际翻译 → 发布 + 渲染 + 合并整本。

逐篇串:revision → 导出 bundle(含 Context Pack)→ **翻译(executor 可插拔)** → import-result(新候选)
→ 评估 → 保守择优(已有 legacy 译文作 incumbent、新译作 challenger,自动选更优)→ DocumentVersion
→ publish → render bilingual+zh → 按作者合并整本。executor 由 translate_fn(bundle)->result 注入:
openrouter 全自动;cursor/claude 由 skill 薄壳驱动同一编排(prepare→agent 翻→finish)。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from . import candidate_eval, legacy_import, openrouter_executor as ox, source_identity as si, version_select
    from .artifact_store import ArtifactStore
    from .pipeline_ingest import merge_author
    from .renderer import render_bilingual, render_zh
    from .result_import import import_result
    from .task_export import export_job, ingest_revision
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import candidate_eval, legacy_import, openrouter_executor as ox, source_identity as si, version_select
    from core.artifact_store import ArtifactStore
    from core.pipeline_ingest import merge_author
    from core.renderer import render_bilingual, render_zh
    from core.result_import import import_result
    from core.task_export import export_job, ingest_revision

TranslateFn = Callable[[Dict[str, Any]], Dict[str, Any]]


def _openrouter_fn(model: str = ox.DEFAULT_MODEL) -> TranslateFn:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("executor=openrouter 需要环境变量 OPENROUTER_API_KEY")
    return lambda bundle: ox.translate_bundle(bundle, lambda m: ox.openrouter_call(m, model, key), model=model)


def make_translate_fn(executor: str, model: Optional[str] = None) -> TranslateFn:
    """executor 名 → translate_fn(bundle)->result。自动路线在此实现;agent 路线(cursor/claude)
    不在此(由 skill 薄壳调 prepare/finish 自己翻),CLI 不接受。"""
    if executor == "openrouter":
        return _openrouter_fn(model or ox.DEFAULT_MODEL)
    raise ValueError(f"未知/不可自动执行的 executor: {executor!r}(cursor/claude 走 skill 薄壳)")


def translate_document(
    provider: str,
    source_path: Path,
    store: ArtifactStore,
    translate_fn: TranslateFn,
    render_dir: Optional[Path] = None,
    bilingual_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """单篇:revision→bundle→翻译→import→评估→保守择优→version→publish→render。返回报告。"""
    source_path = Path(source_path)
    rev = si.build_document_revision(provider, source_path)
    doc = rev["document_id"]
    report: Dict[str, Any] = {"document_id": doc, "segments": len(rev["segments"]), "status": "ok"}
    ingest_revision(rev, store)

    # 已有 legacy 译文(可选)作 incumbent 基线;新译作 challenger。
    legacy_by_seg: Dict[str, Dict[str, Any]] = {}
    if bilingual_dir is not None and (Path(bilingual_dir) / source_path.name).is_file():
        legacy, atts, _ = legacy_import.build_legacy_candidates(provider, source_path, Path(bilingual_dir) / source_path.name, "bilingual")
        if legacy:
            store.put_many(doc, [*legacy, *atts])
            legacy_by_seg = {c["segment_id"]: c for c in legacy}

    seg_ids = [s["segment_id"] for s in rev["segments"]]
    bundle = export_job(rev, seg_ids)
    result = translate_fn(bundle)
    rep = import_result(bundle["task"], result, store)
    if rep["quarantined"]:
        report["status"] = "translate_quarantined"
        report["reasons"] = rep["reasons"][:3]
        return report

    segs = {s["segment_id"]: s for s in rev["segments"]}
    # 只取本轮 import_result 写入的候选(rep["candidate_ids"]),不从整个 shard 重建:shard 里可能有
    # 上一轮的非 legacy 候选,按 segment_id 去重会被旧候选覆盖,导致发布的不是本轮 executor 产物(Codex #107)。
    cands_in_store = {c["candidate_id"]: c for c in store.list_shard("candidate", doc)}
    new_by_seg: Dict[str, Dict[str, Any]] = {}
    for cid in rep["candidate_ids"]:
        c = cands_in_store.get(cid)
        if c is not None:
            new_by_seg[c["segment_id"]] = c

    segments_input: List[Dict[str, Any]] = []
    for sid in seg_ids:
        src_text = segs[sid]["source_text"]
        challengers = []
        new = new_by_seg.get(sid)
        if new is not None:
            ev = candidate_eval.evaluate_candidate(new, src_text)
            store.put_many(doc, [ev])
            challengers.append({"candidate_id": new["candidate_id"], "evaluations": [ev]})
        incumbent = None
        leg = legacy_by_seg.get(sid)
        if leg is not None:
            ev = candidate_eval.evaluate_candidate(leg, src_text)
            store.put_many(doc, [ev])
            incumbent = {"candidate_id": leg["candidate_id"], "evaluations": [ev]}
        segments_input.append({"segment_id": sid, "incumbent": incumbent, "challengers": challengers})

    recs = version_select.recommend_selection(segments_input)
    # tags 兜底:tags 译文按设计含「原词/中文」→ kana_residue 假阳性 QA fail;无 incumbent 时没有可保护的
    # 旧值,接受唯一译文。**只放行 metadata.tags**:title/caption/body 的 QA fail(未翻/拒译/假名残留)
    # 仍须阻止发布,不能借兜底扩散到这些段(Codex #107)。
    kind_by_seg = {s["segment_id"]: s["kind"] for s in rev["segments"]}
    chal_by_seg = {si["segment_id"]: (si["challengers"][0]["candidate_id"] if si["challengers"] else None)
                   for si in segments_input}
    for r in recs:
        if (r["selected_candidate_id"] is None
                and kind_by_seg.get(r["segment_id"]) == "metadata.tags"
                and chal_by_seg.get(r["segment_id"])):
            r["selected_candidate_id"] = chal_by_seg[r["segment_id"]]
            r["outcome"] = "select_challenger"
            r["reason_code"] = "metadata_tags_sole_candidate_accepted"
    report["review_required"] = sum(1 for r in recs if r["outcome"] == "review_required")
    if any(r["selected_candidate_id"] is None for r in recs):
        report["status"] = "unresolved"  # body 段无可选(新译 QA fail 且无 incumbent)
        report["unresolved_segments"] = sum(1 for r in recs if r["selected_candidate_id"] is None)
        return report

    created_at = legacy_import._legacy_created_at(rev)
    version = version_select.build_document_version(rev, recs, "workflow", created_at)
    store.put_many(doc, [version])
    current = store.current_ref(doc)
    if current is None:
        store.publish(doc, version["version_id"], expected_version_id=None)
        report["published"] = True
    elif current["version_id"] == version["version_id"]:
        report["published"] = True
    else:
        report["status"] = "ref_exists_kept"
        report["published"] = False
    report["version_id"] = version["version_id"]

    cands_by_id = {c["candidate_id"]: c for c in store.list_shard("candidate", doc)}
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


def translate_user(
    provider: str,
    source_dir: Path,
    store_root: Path,
    render_dir: Optional[Path],
    translate_fn: TranslateFn,
    *,
    bilingual_dir: Optional[Path] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """整作者:逐篇翻译(独立容错)→ 合并整本。limit 限篇控成本。"""
    source_dir, store_root = Path(source_dir), Path(store_root)
    store = ArtifactStore(store_root)
    sources = sorted(source_dir.glob("*.txt"))
    if limit is not None:
        sources = sources[:limit]
    docs: List[Dict[str, Any]] = []
    for src in sources:
        try:
            docs.append(translate_document(provider, src, store, translate_fn, render_dir, bilingual_dir))
        except Exception as exc:  # 逐篇容错
            docs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    rendered_sids = [d["document_id"].rsplit(":", 1)[-1] for d in docs if d.get("rendered")]
    merged = merge_author(render_dir, source_dir.name, rendered_sids) if render_dir is not None else {}
    summary = {
        "total": len(docs),
        "published": sum(1 for d in docs if d.get("published")),
        "errors": sum(1 for d in docs if d.get("status") == "error"),
        "quarantined": sum(1 for d in docs if d.get("status") == "translate_quarantined"),
    }
    manifest = {
        "provider": provider, "source_dir": str(source_dir), "store_root": str(store_root),
        "summary": summary, "merged": merged, "documents": docs,
    }
    out_dir = Path(render_dir) if render_dir is not None else store_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "translate_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=("pixiv", "fanbox"))
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--render-dir", type=Path, default=None)
    parser.add_argument("--bilingual-dir", type=Path, default=None, help="可选:已有 legacy 译文作 incumbent")
    parser.add_argument("--executor", default="openrouter", help="自动执行器(openrouter);cursor/claude 走 skill")
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=None, help="只翻前 N 篇(控成本)")
    args = parser.parse_args()
    for name, val in (("--store", args.store), ("--source-dir", args.source_dir)):
        if not str(val).strip() or str(val) == ".":
            parser.error(f"{name} 不能为空路径")
    translate_fn = make_translate_fn(args.executor, args.model)
    manifest = translate_user(
        args.provider, args.source_dir, args.store, args.render_dir, translate_fn,
        bilingual_dir=args.bilingual_dir, limit=args.limit,
    )
    print(json.dumps(manifest["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
