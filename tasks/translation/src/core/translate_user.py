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
    from . import candidate_eval, legacy_import, openrouter_executor as ox, result_assemble, source_identity as si, version_select
    from .artifact_store import ArtifactStore
    from .pipeline_ingest import merge_author
    from .renderer import render_bilingual, render_zh
    from .result_import import import_result
    from .task_export import export_job, ingest_revision
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import candidate_eval, legacy_import, openrouter_executor as ox, result_assemble, source_identity as si, version_select
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


def _revision_bundle_legacy(provider, source_path, store, bilingual_dir):
    """确定性重建 revision + bundle + legacy 映射(prepare/finish 共用)。ingest/legacy 入库幂等。"""
    source_path = Path(source_path)
    rev = si.build_document_revision(provider, source_path)
    doc = rev["document_id"]
    ingest_revision(rev, store)
    legacy_by_seg: Dict[str, Dict[str, Any]] = {}
    if bilingual_dir is not None and (Path(bilingual_dir) / source_path.name).is_file():
        legacy, atts, _ = legacy_import.build_legacy_candidates(provider, source_path, Path(bilingual_dir) / source_path.name, "bilingual")
        if legacy:
            store.put_many(doc, [*legacy, *atts])
            legacy_by_seg = {c["segment_id"]: c for c in legacy}
    seg_ids = [s["segment_id"] for s in rev["segments"]]
    bundle = export_job(rev, seg_ids)
    return rev, bundle, legacy_by_seg


def prepare_document(provider, source_path, store, bilingual_dir=None) -> Dict[str, Any]:
    """agent 路线第一步:导出该篇翻译 bundle(并入库 revision/legacy)给执行器(我/Cursor)。"""
    rev, bundle, _ = _revision_bundle_legacy(provider, source_path, store, bilingual_dir)
    doc = rev["document_id"]
    return {"document_id": doc, "source_id": doc.rsplit(":", 1)[-1], "bundle": bundle}


def finish_document(
    provider, source_path, store, result, render_dir=None, bilingual_dir=None,
) -> Dict[str, Any]:
    """agent 路线第二步:吃 executor 产的 result → import→评估→保守择优→version→publish→render。"""
    source_path = Path(source_path)
    rev, bundle, legacy_by_seg = _revision_bundle_legacy(provider, source_path, store, bilingual_dir)
    doc = rev["document_id"]
    report: Dict[str, Any] = {"document_id": doc, "segments": len(rev["segments"]), "status": "ok"}
    seg_ids = [s["segment_id"] for s in rev["segments"]]
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


def translate_document(
    provider, source_path, store, translate_fn, render_dir=None, bilingual_dir=None,
) -> Dict[str, Any]:
    """自动路线单篇:prepare(导出 bundle)→ translate_fn 翻译 → finish(发布渲染)。"""
    prep = prepare_document(provider, source_path, store, bilingual_dir)
    result = translate_fn(prep["bundle"])
    return finish_document(provider, source_path, store, result, render_dir, bilingual_dir)


def prepare_user(provider, source_dir, store_root, jobs_dir, *, bilingual_dir=None, limit=None) -> Dict[str, Any]:
    """agent 路线:逐篇导出 bundle 到 jobs_dir/<source_id>.job.json,供执行器逐个翻译。"""
    source_dir, store_root, jobs_dir = Path(source_dir), Path(store_root), Path(jobs_dir)
    store = ArtifactStore(store_root)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(source_dir.glob("*.txt"))
    if limit is not None:
        sources = sources[:limit]
    jobs = []
    for src in sources:
        try:
            prep = prepare_document(provider, src, store, bilingual_dir)
            out = jobs_dir / f"{prep['source_id']}.job.json"
            out.write_text(json.dumps(prep["bundle"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            jobs.append({"source": src.name, "source_id": prep["source_id"], "job": str(out),
                         "segments": len(prep["bundle"]["segments"])})
        except Exception as exc:
            jobs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    manifest = {"provider": provider, "source_dir": str(source_dir), "jobs_dir": str(jobs_dir), "jobs": jobs}
    (jobs_dir / "prepare_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def finish_user(provider, source_dir, store_root, render_dir, results_dir, *, jobs_dir=None, bilingual_dir=None, limit=None) -> Dict[str, Any]:
    """agent 路线:对每篇 source 找 results_dir/<source_id>.result.json → finish_document → 合并整本。

    source_id 与 prepare 一致地取自 document_id(**不是 src.stem**:pixiv 系列文件名是
    `{series}_{order}_{novel}.txt`,stem≠novel_id,会错配成 no_result,Codex #122)。limit 与 prepare 对齐。"""
    source_dir, store_root = Path(source_dir), Path(store_root)
    results_dir, render_dir = Path(results_dir), Path(render_dir)
    store = ArtifactStore(store_root)
    sources = sorted(source_dir.glob("*.txt"))
    if limit is not None:
        sources = sources[:limit]
    docs = []
    for src in sources:
        try:
            source_id = si.build_document_revision(provider, src)["document_id"].rsplit(":", 1)[-1]
        except Exception as exc:
            docs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            continue
        result_path = results_dir / f"{source_id}.result.json"
        tsv_path = results_dir / f"{source_id}.zh.tsv"
        try:
            # 紧凑路径:有 <id>.zh.tsv 而无 result.json → 自动组装(agent 只需写 tsv,不必单独跑 assemble)。
            # **必须用 prepare 当时存的原始 job 组装**(不是按当前源重建):否则 prepare 后源被改/重下时,
            # 旧译文会被盖上新身份、绕过 stale 防护、把译文发到错的 revision(Codex #136)。用原始 job 组装后,
            # 源若变了 → result 的旧 task_digest 与 finish 重建的当前 task 不符 → import_result 隔离掉。
            if not result_path.is_file() and tsv_path.is_file():
                if jobs_dir is None:
                    raise ValueError("从 tsv 组装需要 jobs_dir(prepare 存的原始 job)")
                job_path = Path(jobs_dir) / f"{source_id}.job.json"
                if not job_path.is_file():
                    raise ValueError(f"缺原始 job {job_path}(先 prepare),无法从 tsv 组装")
                bundle = json.loads(job_path.read_text(encoding="utf-8"))
                translations = result_assemble.parse_translations_tsv(tsv_path.read_text(encoding="utf-8"))
                result = result_assemble.assemble_result(bundle, translations, producer_name="agent")
                result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if not result_path.is_file():
                docs.append({"source": src.name, "status": "no_result"})
                continue
            result = json.loads(result_path.read_text(encoding="utf-8"))
            docs.append(finish_document(provider, src, store, result, render_dir, bilingual_dir))
        except Exception as exc:
            docs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    rendered_sids = [d["document_id"].rsplit(":", 1)[-1] for d in docs if d.get("rendered")]
    merged = merge_author(render_dir, source_dir.name, rendered_sids)
    summary = {"total": len(docs), "published": sum(1 for d in docs if d.get("published")),
               "no_result": sum(1 for d in docs if d.get("status") == "no_result"),
               "errors": sum(1 for d in docs if d.get("status") == "error")}
    manifest = {"provider": provider, "summary": summary, "merged": merged, "documents": docs}
    render_dir.mkdir(parents=True, exist_ok=True)
    (render_dir / "translate_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_user(provider, source_dir, store_root, render_dir, results_dir=None, *, limit=None) -> Dict[str, Any]:
    """**独立核对落盘产物,不信 agent 自述**(#129):逐篇查 result.json 是否在、是否入库(candidate)、
    是否发布(current ref)、是否渲染(zh+bilingual)。任一篇未完整完成 → ok=False。"""
    source_dir, store_root = Path(source_dir), Path(store_root)
    render_dir = Path(render_dir) if render_dir else None
    results_dir = Path(results_dir) if results_dir else None
    store = ArtifactStore(store_root)
    sources = sorted(source_dir.glob("*.txt"))
    if limit is not None:
        sources = sources[:limit]
    docs: List[Dict[str, Any]] = []
    for src in sources:
        rep: Dict[str, Any] = {"source": src.name}
        try:
            rev = si.build_document_revision(provider, src)
        except Exception as exc:
            rep.update(ok=False, error=f"{type(exc).__name__}: {exc}")
            docs.append(rep)
            continue
        doc = rev["document_id"]
        rev_id = rev["revision_id"]
        sid = doc.rsplit(":", 1)[-1]
        rep["source_id"] = sid
        rep["result_json"] = bool(results_dir and (results_dir / f"{sid}.result.json").is_file())
        rep["candidates"] = len(store.list_shard("candidate", doc))
        # 发布须对应**当前源 revision**:旧 current ref(源已变、新版从未 finish)不能算通过(Codex #130)。
        current = store.current_ref(doc)
        rep["published"] = current is not None
        version = store.get("document-version", doc, current["version_id"]) if current else None
        rep["version_matches_source"] = bool(version and version.get("revision_id") == rev_id)
        rep["rendered"] = bool(render_dir and (render_dir / f"{sid}.zh.txt").is_file()
                               and (render_dir / f"{sid}.bilingual.txt").is_file())
        # result.json 仅当传了 results_dir 才作硬条件;核心真相是 入库 + 发布到当前 revision + 渲染。
        rep["ok"] = (rep["candidates"] > 0 and rep["version_matches_source"] and rep["rendered"]
                     and (rep["result_json"] or results_dir is None))
        docs.append(rep)
    ok = bool(docs) and all(d.get("ok") for d in docs)
    return {"ok": ok, "verified": sum(1 for d in docs if d.get("ok")), "total": len(docs), "documents": docs}


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
    parser.add_argument("--mode", choices=("auto", "prepare", "finish", "verify"), default="auto",
                        help="auto=自动执行器全程;prepare=导出 bundle;finish=吃 result 发布渲染;verify=独立核对落盘产物(防造假)")
    parser.add_argument("--provider", required=True, choices=("pixiv", "fanbox"))
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--render-dir", type=Path, default=None)
    parser.add_argument("--jobs-dir", type=Path, default=None, help="mode=prepare 的 bundle 输出目录")
    parser.add_argument("--results-dir", type=Path, default=None, help="mode=finish 的 agent result 目录")
    parser.add_argument("--bilingual-dir", type=Path, default=None, help="可选:已有 legacy 译文作 incumbent")
    parser.add_argument("--executor", default="openrouter", help="mode=auto 的执行器(openrouter)")
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 篇(控成本)")
    args = parser.parse_args()
    for name, val in (("--store", args.store), ("--source-dir", args.source_dir)):
        if not str(val).strip() or str(val) == ".":
            parser.error(f"{name} 不能为空路径")

    if args.mode == "prepare":
        if not (args.jobs_dir and str(args.jobs_dir).strip()):
            parser.error("mode=prepare 需要非空 --jobs-dir")
        m = prepare_user(args.provider, args.source_dir, args.store, args.jobs_dir,
                         bilingual_dir=args.bilingual_dir, limit=args.limit)
        print(json.dumps({"jobs": len([j for j in m["jobs"] if j.get("job")]), "jobs_dir": str(args.jobs_dir)}, ensure_ascii=False))
        return 0
    if args.mode == "verify":
        if not (args.render_dir and str(args.render_dir).strip()):
            parser.error("mode=verify 需要 --render-dir(核对渲染产物)")
        rep = verify_user(args.provider, args.source_dir, args.store, args.render_dir,
                          args.results_dir, limit=args.limit)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0 if rep["ok"] else 1  # 未完整完成 → 非零退出(可作闸门)

    if args.mode == "finish":
        if not (args.results_dir and str(args.results_dir).strip()) or not (args.render_dir and str(args.render_dir).strip()):
            parser.error("mode=finish 需要非空 --results-dir 与 --render-dir")
        m = finish_user(args.provider, args.source_dir, args.store, args.render_dir, args.results_dir,
                        jobs_dir=args.jobs_dir, bilingual_dir=args.bilingual_dir, limit=args.limit)
        print(json.dumps(m["summary"], ensure_ascii=False))
        return 0

    translate_fn = make_translate_fn(args.executor, args.model)
    manifest = translate_user(
        args.provider, args.source_dir, args.store, args.render_dir, translate_fn,
        bilingual_dir=args.bilingual_dir, limit=args.limit,
    )
    print(json.dumps(manifest["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
