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
    from . import annotate_eval, candidate_eval, document_qa, entity_harvest, legacy_import, openrouter_executor as ox, result_assemble, source_identity as si, version_select
    from .artifact_store import ArtifactStore
    from .pipeline_ingest import merge_author
    from .renderer import render_bilingual, render_zh
    from .result_import import import_result
    from .task_export import export_job, ingest_revision, resolve_entities_for_revision
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import annotate_eval, candidate_eval, document_qa, entity_harvest, legacy_import, openrouter_executor as ox, result_assemble, source_identity as si, version_select
    from core.artifact_store import ArtifactStore
    from core.pipeline_ingest import merge_author
    from core.renderer import render_bilingual, render_zh
    from core.result_import import import_result
    from core.task_export import export_job, ingest_revision, resolve_entities_for_revision

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


def _revision_bundle_legacy(provider, source_path, store, bilingual_dir, entity_store=None):
    """确定性重建 revision + bundle + legacy 映射(prepare/finish 共用)。ingest/legacy 入库幂等。

    entity_store:实体库根目录,给定则把本篇适用实体解析进 context_pack(折入 task 身份)。
    **prepare 与 finish 必须传同一个库**:实体约束入 digest,中途改库 → import 按 stale 隔离。"""
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
    entities = resolve_entities_for_revision(rev, entity_store) if entity_store else None
    bundle = export_job(rev, seg_ids, entities=entities)
    return rev, bundle, legacy_by_seg


def prepare_document(provider, source_path, store, bilingual_dir=None, entity_store=None) -> Dict[str, Any]:
    """agent 路线第一步:导出该篇翻译 bundle(并入库 revision/legacy)给执行器(我/Cursor)。"""
    rev, bundle, _ = _revision_bundle_legacy(provider, source_path, store, bilingual_dir, entity_store=entity_store)
    doc = rev["document_id"]
    return {"document_id": doc, "source_id": doc.rsplit(":", 1)[-1], "bundle": bundle}


def finish_document(
    provider, source_path, store, result, render_dir=None, bilingual_dir=None, entity_store=None,
    entity_review_queue=None,
) -> Dict[str, Any]:
    """agent 路线第二步:吃 executor 产的 result → import→评估→保守择优→version→publish→render。"""
    source_path = Path(source_path)
    rev, bundle, legacy_by_seg = _revision_bundle_legacy(provider, source_path, store, bilingual_dir, entity_store=entity_store)
    doc = rev["document_id"]
    report: Dict[str, Any] = {"document_id": doc, "segments": len(rev["segments"]), "status": "ok"}
    seg_ids = [s["segment_id"] for s in rev["segments"]]

    harvested_entities = entity_harvest.entities_from_result(result)
    if harvested_entities:
        report["entity_harvest"] = {entity["source"]: entity["target"] for entity in harvested_entities}

    rep = import_result(bundle["task"], result, store)
    if rep["quarantined"]:
        report["status"] = "translate_quarantined"
        report["reasons"] = rep["reasons"][:3]
        report["next_action"] = (
            "保持 SOURCE 与 ENTITY_STORE 和 prepare 时一致后重跑 finish；"
            "原 job 未带实体上下文时显式传 ENTITY_STORE="
        )
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

    document_findings = document_qa.audit_document_translations(
        rev["segments"], {sid: c["text"] for sid, c in new_by_seg.items()}
    )
    report["document_qa_findings"] = document_findings
    if any(f["severity"] == "error" for f in document_findings):
        report["status"] = "document_qa_failed"
        report["published"] = False
        return report

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
    # tags 译文按设计含「原词/中文」→ kana_residue 假阳性 QA fail,直接转成通过选择。
    # 其它无 incumbent 的单候选 QA fail 仍保留 review_required,但允许先发布/渲染供人工 review。
    kind_by_seg = {s["segment_id"]: s["kind"] for s in rev["segments"]}
    chal_by_seg = {si["segment_id"]: [c["candidate_id"] for c in si["challengers"]] for si in segments_input}
    for r in recs:
        sole_challenger = chal_by_seg.get(r["segment_id"]) or []
        # **空译文候选一律不可选**(先于所有兜底路径,含 tags 分支——Codex #153 review):
        # 选空文本=发布带洞版本,违反"空候选阻断建版"不变量(gh-142 实测:填空 TSV 的空行被
        # 放宽路径放行,212 篇带洞发布)。空候选留 None → 整篇 unresolved 阻断。
        sole_nonempty = (len(sole_challenger) == 1
                         and (cands_in_store.get(sole_challenger[0]) or {}).get("text", "").strip())
        if r["selected_candidate_id"] is not None or not sole_nonempty:
            continue
        if kind_by_seg.get(r["segment_id"]) == "metadata.tags":
            r["selected_candidate_id"] = sole_challenger[0]
            r["outcome"] = "select_challenger"
            r["reason_code"] = "metadata_tags_sole_candidate_accepted"
        else:
            # 执行器路线先产可渲染版本:无 incumbent 时,唯一非空候选即使 QA fail 也进入
            # draft/current,review_required 保留给 FEEDBACK/patch。多候选未决仍阻断建版。
            r["selected_candidate_id"] = sole_challenger[0]
            r["reason_code"] = f"reviewable_{r['reason_code']}"
    report["review_required"] = sum(1 for r in recs if r["outcome"] == "review_required")
    if any(r["selected_candidate_id"] is None for r in recs):
        report["status"] = "unresolved"  # body 段无可选(新译 QA fail 且无 incumbent)
        report["unresolved_segments"] = sum(1 for r in recs if r["selected_candidate_id"] is None)
        return report

    created_at = legacy_import._legacy_created_at(rev)
    # 先按无 parent 构建(确定性 id):与 current 相同 → 幂等重跑;不同(TSV 修复过)→
    # 带 parent 血缘重建并 CAS 推进 ref。此前 "ref_exists_kept" 永不推进,导致修复只
    # 更新 rendered、store ref 长期指向旧坏版本(gh-142 修复潮踩坑:rendered 与 ref 漂移)。
    version = version_select.build_document_version(rev, recs, "workflow", created_at)
    current = store.current_ref(doc)
    if current is None:
        store.put_many(doc, [version])
        store.publish(doc, version["version_id"], expected_version_id=None)
        report["published"] = True
    elif current["version_id"] == version["version_id"]:
        store.put_many(doc, [version])
        report["published"] = True
    else:
        version = version_select.build_document_version(
            rev, recs, "workflow", created_at, parent_version_id=current["version_id"])
        store.put_many(doc, [version])
        store.publish(doc, version["version_id"], expected_version_id=current["version_id"])
        report["status"] = "republished"
        report["previous_version_id"] = current["version_id"]
        report["published"] = True
    report["version_id"] = version["version_id"]

    cands_by_id = {c["candidate_id"]: c for c in store.list_shard("candidate", doc)}
    translations = {sid: cands_by_id[cid]["text"] for sid, cid in version["selections"].items()}
    source_text = source_path.read_text(encoding="utf-8")
    if render_dir is not None:
        render_dir = Path(render_dir)
        render_dir.mkdir(parents=True, exist_ok=True)
        sid = doc.rsplit(":", 1)[-1]
        # 逐篇 bilingual 保持原始日文(不注音),这样 qa_gate 能按源文精确重对齐;
        # furigana 注音只在作者合集/epub 构建时施加(见 author_collection），不污染 QA 可复核的工件。
        (render_dir / f"{sid}.bilingual.txt").write_text(render_bilingual(rev, source_text, translations), encoding="utf-8")
        (render_dir / f"{sid}.zh.txt").write_text(render_zh(rev, source_text, translations), encoding="utf-8")
        report["rendered"] = True

    if harvested_entities and entity_store is not None and entity_review_queue is not None:
        try:
            reviews = entity_harvest.enqueue_entity_reviews(
                rev, harvested_entities, Path(entity_store), Path(entity_review_queue)
            )
            report["entity_reviews_enqueued"] = len(reviews)
        except Exception as exc:
            report["entity_harvest_error"] = f"{type(exc).__name__}: {exc}"
    return report


def translate_document(
    provider, source_path, store, translate_fn, render_dir=None, bilingual_dir=None, entity_store=None,
    entity_review_queue=None,
) -> Dict[str, Any]:
    """自动路线单篇：prepare → translate_fn(边译边锁本文实体) → finish。"""
    prep = prepare_document(provider, source_path, store, bilingual_dir, entity_store=entity_store)
    result = translate_fn(prep["bundle"])
    return finish_document(provider, source_path, store, result, render_dir, bilingual_dir,
                           entity_store=entity_store, entity_review_queue=entity_review_queue)


def prepare_user(provider, source_dir, store_root, jobs_dir, *, bilingual_dir=None, entity_store=None, limit=None) -> Dict[str, Any]:
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
            prep = prepare_document(provider, src, store, bilingual_dir, entity_store=entity_store)
            out = jobs_dir / f"{prep['source_id']}.job.json"
            out.write_text(json.dumps(prep["bundle"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            jobs.append({"source": src.name, "source_id": prep["source_id"], "job": str(out),
                         "segments": len(prep["bundle"]["segments"])})
        except Exception as exc:
            jobs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    manifest = {"provider": provider, "source_dir": str(source_dir), "jobs_dir": str(jobs_dir), "jobs": jobs}
    (jobs_dir / "prepare_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _stable_result_signature(result: Dict[str, Any]) -> Dict[str, Any]:
    """比较由 job+TSV 机械派生的稳定字段;completed_at 不参与,避免每次 finish 都改写。"""
    return {
        "schema_version": result.get("schema_version"),
        "task_id": result.get("task_id"),
        "task_digest": result.get("task_digest"),
        "producer": result.get("producer"),
        "recommended_candidate_keys": result.get("recommended_candidate_keys"),
        "findings": result.get("findings"),
        "candidates": [
            {
                "result_candidate_key": c.get("result_candidate_key"),
                "segment_id": c.get("segment_id"),
                "source_hash": c.get("source_hash"),
                "text": c.get("text"),
            }
            for c in result.get("candidates", [])
        ],
    }


def _sync_result_from_tsv(
    result_path: Path,
    tsv_path: Path,
    job_path: Path,
    *,
    producer_name: Optional[str] = None,
    model: Optional[str] = None,
    names_path: Optional[Path] = None,
) -> bool:
    """当 TSV 存在时,用 prepare 的原始 job 组装期望 result。缺失/陈旧/partial result 会被覆盖。"""
    if not tsv_path.is_file():
        return False
    if not job_path.is_file():
        raise ValueError(f"缺原始 job {job_path}(先 prepare),无法从 tsv 组装")
    bundle = json.loads(job_path.read_text(encoding="utf-8"))
    translations = result_assemble.parse_translations_tsv(tsv_path.read_text(encoding="utf-8"), bundle)
    findings: List[Dict[str, Any]] = []
    if names_path is not None and names_path.is_file():
        local_targets = entity_harvest.parse_locked_names_tsv(names_path.read_text(encoding="utf-8"))
        translations, findings = entity_harvest.apply_locked_names(bundle, translations, local_targets)
    current = None
    if result_path.is_file():
        current = json.loads(result_path.read_text(encoding="utf-8"))
    current_producer = current.get("producer", {}) if current else {}
    effective_producer = producer_name or current_producer.get("name") or "agent"
    effective_model = model if model is not None else current_producer.get("model")
    expected = result_assemble.assemble_result(
        bundle,
        translations,
        producer_name=effective_producer,
        model=effective_model,
        completed_at=current.get("completed_at") if current else None,
        findings=findings,
    )
    if current is None or _stable_result_signature(current) != _stable_result_signature(expected):
        result_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True
    return False


def finish_user(
    provider,
    source_dir,
    store_root,
    render_dir,
    results_dir,
    *,
    jobs_dir=None,
    bilingual_dir=None,
    entity_store=None,
    entity_review_queue=None,
    limit=None,
    producer_name: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
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
        names_path = results_dir / f"{source_id}.names.tsv"
        try:
            # 紧凑路径:有 <id>.zh.tsv → 自动组装/校准 result(agent 只需写 tsv,不必单独跑 assemble)。
            # **必须用 prepare 当时存的原始 job 组装**(不是按当前源重建):否则 prepare 后源被改/重下时,
            # 旧译文会被盖上新身份、绕过 stale 防护、把译文发到错的 revision(Codex #136)。用原始 job 组装后,
            # 源若变了 → result 的旧 task_digest 与 finish 重建的当前 task 不符 → import_result 隔离掉。
            # 若已有 result.json 但它是旧的 partial/陈旧产物,完整 TSV 必须重新组装覆盖,否则会把缺段误报成 QA 问题。
            if tsv_path.is_file() and jobs_dir is not None:
                # 有 tsv + 原始 job → 以 tsv 为准(重)组装,覆盖旧/不全 result。
                job_path = Path(jobs_dir) / f"{source_id}.job.json"
                _sync_result_from_tsv(
                    result_path,
                    tsv_path,
                    job_path,
                    producer_name=producer_name,
                    model=model,
                    names_path=names_path,
                )
            elif tsv_path.is_file() and jobs_dir is None and not result_path.is_file():
                # 只有 tsv、既无 job 又无现成 result → 没法组装(Codex #138:仅此时才硬报错)。
                raise ValueError("从 tsv 组装需要 jobs_dir(prepare 存的原始 job)")
            # 其余:tsv 在但没 jobs_dir、且已有可用 result.json → 直接用现成 result(不强制重组装、不报错)。
            if not result_path.is_file():
                docs.append({"source": src.name, "status": "no_result"})
                continue
            result = json.loads(result_path.read_text(encoding="utf-8"))
            docs.append(finish_document(
                provider,
                src,
                store,
                result,
                render_dir,
                bilingual_dir,
                entity_store=entity_store,
                entity_review_queue=entity_review_queue,
            ))
        except Exception as exc:
            docs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    rendered_sids = [d["document_id"].rsplit(":", 1)[-1] for d in docs if d.get("rendered")]
    merged = merge_author(render_dir, source_dir.name, rendered_sids)
    summary = {
        "total": len(docs),
        "published": sum(1 for d in docs if d.get("published")),
        "no_result": sum(1 for d in docs if d.get("status") == "no_result"),
        "quarantined": sum(1 for d in docs if d.get("status") == "translate_quarantined"),
        "unresolved": sum(1 for d in docs if d.get("status") == "unresolved"),
        "qa_failed": sum(1 for d in docs if d.get("status") == "document_qa_failed"),
        "errors": sum(1 for d in docs if d.get("status") == "error"),
    }
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
        # ref 漂移检测(gh-142 踩坑):修复重跑 finish 曾只更新 rendered、不推进 ref →
        # 盘上 zh.txt 与 store 发布版本长期不一致。判据:rendered 内容 == 按 current ref
        # 的 selections 重算的渲染(工作流无关——review_required 保留 incumbent 也自然通过)。
        rep["rendered_matches_ref"] = True
        # 仅当发布版本对应当前源 revision 才可比(源改了 → segment_id 换代,由
        # version_matches_source 单独判 fail,这里不重复)。
        if rep["rendered"] and version and rep["version_matches_source"]:
            cands_by_id = {c["candidate_id"]: c for c in store.list_shard("candidate", doc)}
            sel_texts = {seg_id: cands_by_id[cid]["text"]
                         for seg_id, cid in version.get("selections", {}).items()
                         if cid in cands_by_id}
            expected_zh = render_zh(rev, src.read_text(encoding="utf-8"), sel_texts)
            actual_zh = (render_dir / f"{sid}.zh.txt").read_text(encoding="utf-8")
            rep["rendered_matches_ref"] = expected_zh == actual_zh
        # result.json 仅当传了 results_dir 才作硬条件;核心真相是 入库 + 发布到当前 revision + 渲染。
        rep["ok"] = (rep["candidates"] > 0 and rep["version_matches_source"] and rep["rendered"]
                     and rep["rendered_matches_ref"]
                     and (rep["result_json"] or results_dir is None))
        docs.append(rep)
    ok = bool(docs) and all(d.get("ok") for d in docs)
    return {"ok": ok, "verified": sum(1 for d in docs if d.get("ok")), "total": len(docs), "documents": docs}


# ---------------- annotate(陪读注解,#174):与翻译同构的另一条 task_type 线 ----------------
# 复用同一 revision/job/TSV/result/import/version/publish 机制,差别:
# ①job 只含 body 段(front-matter 不是学习材料)②评估用 annotate_eval(骨架不变量,非翻译 QA)
# ③版本发布到独立 channel("annotate",refs-annotate/)不与译文 current 打架
# ④渲染 study = 选中注解 + **当前翻译版本**交织 → 注解绑原文,翻译更新只需重渲染。


def _annotate_bundle(provider, source_path, store, entity_store=None):
    """annotate 版 revision+bundle(无 legacy:注解没有旧译文 incumbent)。"""
    source_path = Path(source_path)
    rev = si.build_document_revision(provider, source_path)
    ingest_revision(rev, store)
    body_ids = [s["segment_id"] for s in rev["segments"] if s["kind"] == "body"]
    entities = resolve_entities_for_revision(rev, entity_store) if entity_store else None
    bundle = export_job(rev, body_ids, entities=entities, task_type="annotate")
    return rev, bundle


def prepare_annotate_user(provider, source_dir, store_root, jobs_dir, *, entity_store=None, limit=None) -> Dict[str, Any]:
    """逐篇导出注解 bundle 到 jobs_dir/<sid>.annotate.job.json(供 agent 执行器写注解 TSV)。"""
    source_dir, store_root, jobs_dir = Path(source_dir), Path(store_root), Path(jobs_dir)
    store = ArtifactStore(store_root)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(source_dir.glob("*.txt"))
    if limit is not None:
        sources = sources[:limit]
    jobs = []
    for src in sources:
        try:
            rev, bundle = _annotate_bundle(provider, src, store, entity_store=entity_store)
            sid = rev["document_id"].rsplit(":", 1)[-1]
            out = jobs_dir / f"{sid}.annotate.job.json"
            out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            jobs.append({"source": src.name, "source_id": sid, "job": str(out),
                         "segments": len(bundle["segments"])})
        except Exception as exc:
            jobs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    return {"jobs": jobs}


def finish_annotate_document(
    provider, source_path, store, results: List[Dict[str, Any]], render_dir=None, entity_store=None,
    producer_priority: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """吃(多模型的)注解 result → import → annotate_eval → 逐段择优 → 注解 Version →
    publish(channel=annotate)→ render study(选中注解 + 当前翻译)。

    择优:每段取 verdict=pass 的候选;多个 pass 时按 producer_priority 先到先选(注解无 incumbent、
    无保守替换语义,优先级列表即用户的模型偏好);任一段无 pass 候选 → unresolved 不建版。"""
    source_path = Path(source_path)
    rev, bundle = _annotate_bundle(provider, source_path, store, entity_store=entity_store)
    doc = rev["document_id"]
    report: Dict[str, Any] = {"document_id": doc, "task_type": "annotate",
                              "segments": len(bundle["segments"]), "status": "ok"}
    segs = {s["segment_id"]: s for s in rev["segments"]}
    seg_ids = [s["segment_id"] for s in bundle["segments"]]

    # import 全部 result(不同 producer 各一份);任何一份 stale 都隔离并整篇失败(与翻译同语义)。
    cand_ids_by_producer: List[tuple] = []
    for result in results:
        rep = import_result(bundle["task"], result, store)
        if rep["quarantined"]:
            report["status"] = "annotate_quarantined"
            report["reasons"] = rep["reasons"][:3]
            return report
        cand_ids_by_producer.append((result.get("producer", {}).get("name", "unknown"), rep["candidate_ids"]))

    cands_in_store = {c["candidate_id"]: c for c in store.list_shard("candidate", doc)}
    # producer → {segment_id: candidate};按 producer_priority 排序(未列出的按出现序排后)。
    priority = producer_priority or [p for p, _ in cand_ids_by_producer]
    ordered = sorted(cand_ids_by_producer,
                     key=lambda pc: priority.index(pc[0]) if pc[0] in priority else len(priority))
    by_producer: List[tuple[str, Dict[str, Dict[str, Any]]]] = []
    for producer, cids in ordered:
        m: Dict[str, Dict[str, Any]] = {}
        for cid in cids:
            c = cands_in_store.get(cid)
            if c is not None:
                m[c["segment_id"]] = c
        by_producer.append((producer, m))

    recs: List[Dict[str, Any]] = []
    unresolved = 0
    unresolved_details: List[Dict[str, Any]] = []
    for segment_index, sid in enumerate(seg_ids):
        selected = None
        eval_ids: List[str] = []
        failed_candidates: List[Dict[str, Any]] = []
        for producer, pm in by_producer:
            c = pm.get(sid)
            if c is None:
                continue
            ev = annotate_eval.evaluate_annotation_candidate(c, segs[sid]["source_text"])
            store.put_many(doc, [ev])
            eval_ids.append(ev["evaluation_id"])
            if ev["verdict"] == "pass" and selected is None:
                selected = c["candidate_id"]
            elif ev["verdict"] != "pass":
                failed_candidates.append({
                    "producer": producer,
                    "candidate_id": c["candidate_id"],
                    "evaluation_id": ev["evaluation_id"],
                    "candidate_text": c["text"],
                    "findings": ev["findings"],
                })
        if selected is None:
            unresolved += 1
            unresolved_details.append({
                "segment_index": segment_index,
                "segment_id": sid,
                "source_text": segs[sid]["source_text"],
                "candidates": failed_candidates,
            })
        recs.append({
            "segment_id": sid, "selected_candidate_id": selected,
            "selected_by": "policy", "outcome": "select_challenger" if selected else "review_required",
            "reason_code": "annotate_priority_pass" if selected else "no_passing_annotation",
            "incumbent_candidate_id": None, "evaluation_ids": eval_ids,
        })
    if unresolved:
        report["status"] = "unresolved"
        report["unresolved_segments"] = unresolved
        report["unresolved_details"] = unresolved_details
        return report

    # 注解 version 只覆盖 body 段——构造一个 body-only 的 revision 视图喂 build_document_version
    # (它要求 recommendations 覆盖 revision 全部段;metadata 段不属于注解任务)。
    body_rev = {**rev, "segments": [s for s in rev["segments"] if s["kind"] == "body"]}
    current = store.current_ref(doc, channel="annotate")
    selections = {rec["segment_id"]: rec["selected_candidate_id"] for rec in recs}
    version = store.get("document-version", doc, current["version_id"]) if current else None
    if version is not None and (
        version["revision_id"] != body_rev["revision_id"] or version["selections"] != selections
    ):
        version = None
    if version is not None:
        report["published"] = True
    elif current is None:
        version = version_select.build_document_version(body_rev, recs, "workflow", datetime_now_iso())
        store.put_many(doc, [version])
        store.publish(doc, version["version_id"], expected_version_id=None, channel="annotate")
        report["published"] = True
    else:
        version = version_select.build_document_version(
            body_rev, recs, "workflow", datetime_now_iso(), parent_version_id=current["version_id"])
        store.put_many(doc, [version])
        store.publish(doc, version["version_id"], expected_version_id=current["version_id"], channel="annotate")
        report["status"] = "republished"
        report["published"] = True
    report["version_id"] = version["version_id"]

    # render study:注解(本版 selections)+ 当前翻译版本(translate channel)。翻译未发布则跳过渲染。
    if render_dir is not None:
        trans_ref = store.current_ref(doc)
        if trans_ref is None:
            report["study_rendered"] = False
            report["study_skip_reason"] = "translation_not_published"
        else:
            trans_version = store.get("document-version", doc, trans_ref["version_id"])
            translations = {s: cands_in_store[c]["text"]
                            for s, c in trans_version["selections"].items() if c in cands_in_store}
            annotations = {s: cands_in_store[c]["text"]
                           for s, c in version["selections"].items() if c in cands_in_store}
            render_dir = Path(render_dir)
            render_dir.mkdir(parents=True, exist_ok=True)
            sid_short = doc.rsplit(":", 1)[-1]
            source_text = source_path.read_text(encoding="utf-8")
            (render_dir / f"{sid_short}.study.txt").write_text(
                render_bilingual(rev, source_text, translations, annotations=annotations), encoding="utf-8")
            report["study_rendered"] = True
    return report


def finish_annotate_user(
    provider, source_dir, store_root, render_dir, results_dir, *,
    jobs_dir, entity_store=None, limit=None, producer_name: Optional[str] = None,
    producer_priority: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """agent 路线:对每篇找 results_dir 里的注解 TSV(单模型 <sid>.annotate.tsv 或
    多模型 <sid>.annotate.<producer>.tsv 若干)→ 组装 result → finish_annotate_document。"""
    source_dir, store_root = Path(source_dir), Path(store_root)
    results_dir, jobs_dir = Path(results_dir), Path(jobs_dir)
    store = ArtifactStore(store_root)
    sources = sorted(source_dir.glob("*.txt"))
    if limit is not None:
        sources = sources[:limit]
    docs = []
    for src in sources:
        try:
            sid = si.build_document_revision(provider, src)["document_id"].rsplit(":", 1)[-1]
        except Exception as exc:
            docs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            continue
        job_path = jobs_dir / f"{sid}.annotate.job.json"
        if not job_path.is_file():
            docs.append({"source": src.name, "status": "no_job"})
            continue
        bundle = json.loads(job_path.read_text(encoding="utf-8"))
        # 收集 TSV:多模型命名 <sid>.annotate.<producer>.tsv 优先,否则单文件 <sid>.annotate.tsv
        tsvs = sorted(results_dir.glob(f"{sid}.annotate.*.tsv"))
        if not tsvs:
            single = results_dir / f"{sid}.annotate.tsv"
            tsvs = [single] if single.is_file() else []
        if not tsvs:
            docs.append({"source": src.name, "status": "no_result"})
            continue
        results = []
        for tsv in tsvs:
            prefix = f"{sid}.annotate."
            parsed_producer = (
                tsv.name[len(prefix):-len(".tsv")]
                if tsv.name.startswith(prefix) and tsv.name.endswith(".tsv")
                else ""
            )
            producer = parsed_producer or producer_name or "agent"
            translations = result_assemble.parse_translations_tsv(tsv.read_text(encoding="utf-8"), bundle)
            results.append(result_assemble.assemble_result(bundle, translations, producer_name=producer))
        try:
            docs.append(finish_annotate_document(provider, src, store, results, render_dir,
                                                 entity_store=entity_store,
                                                 producer_priority=producer_priority))
        except Exception as exc:
            docs.append({"source": src.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    summary = {"total": len(docs),
               "published": sum(1 for d in docs if d.get("published")),
               "unresolved": sum(1 for d in docs if d.get("status") == "unresolved"),
               "errors": sum(1 for d in docs if d.get("status") == "error")}
    return {"summary": summary, "documents": docs}


def status_annotate_user(
    provider: str,
    source_dir: Path,
    store_root: Path,
    render_dir: Optional[Path] = None,
    results_dir: Optional[Path] = None,
    *,
    jobs_dir: Optional[Path] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """只读汇总 annotate job、TSV、current ref 与 study 产物。"""
    source_dir, store_root = Path(source_dir), Path(store_root)
    jobs_dir = Path(jobs_dir) if jobs_dir is not None else None
    results_dir = Path(results_dir) if results_dir is not None else None
    render_dir = Path(render_dir) if render_dir is not None else None
    store = ArtifactStore(store_root)
    sources = sorted(source_dir.glob("*.txt"))
    if limit is not None:
        sources = sources[:limit]
    docs: List[Dict[str, Any]] = []
    for src in sources:
        rev = si.build_document_revision(provider, src)
        doc = rev["document_id"]
        sid = doc.rsplit(":", 1)[-1]
        job = jobs_dir / f"{sid}.annotate.job.json" if jobs_dir else None
        tsvs = sorted(results_dir.glob(f"{sid}.annotate.*.tsv")) if results_dir else []
        single = results_dir / f"{sid}.annotate.tsv" if results_dir else None
        if single is not None and single.is_file() and not tsvs:
            tsvs = [single]
        ref = store.current_ref(doc, channel="annotate")
        study = render_dir / f"{sid}.study.txt" if render_dir else None
        result_newer_than_study = bool(
            tsvs and study is not None and study.is_file()
            and max(path.stat().st_mtime_ns for path in tsvs) > study.stat().st_mtime_ns
        )
        if tsvs and (study is None or not study.is_file() or result_newer_than_study):
            status = "ready_to_finish"
        elif ref and study is not None and study.is_file():
            status = "published"
        elif job is not None and job.is_file():
            status = "awaiting_result"
        else:
            status = "unprepared"
        docs.append({
            "document_id": doc,
            "status": status,
            "job": str(job) if job is not None and job.is_file() else None,
            "results": [str(path) for path in tsvs],
            "result_newer_than_study": result_newer_than_study,
            "version_id": ref["version_id"] if ref else None,
            "study": str(study) if study is not None and study.is_file() else None,
        })
    return {
        "summary": {
            "total": len(docs),
            "published": sum(1 for doc in docs if doc["status"] == "published"),
            "ready_to_finish": sum(1 for doc in docs if doc["status"] == "ready_to_finish"),
            "awaiting_result": sum(1 for doc in docs if doc["status"] == "awaiting_result"),
            "unprepared": sum(1 for doc in docs if doc["status"] == "unprepared"),
        },
        "documents": docs,
    }


def datetime_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def translate_user(
    provider: str,
    source_dir: Path,
    store_root: Path,
    render_dir: Optional[Path],
    translate_fn: TranslateFn,
    *,
    bilingual_dir: Optional[Path] = None,
    entity_store: Optional[Path] = None,
    entity_review_queue: Optional[Path] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """整作者逐篇翻译并合并整本；首次译名可在发布后送入 review。"""
    source_dir, store_root = Path(source_dir), Path(store_root)
    store = ArtifactStore(store_root)
    sources = sorted(source_dir.glob("*.txt"))
    if limit is not None:
        sources = sources[:limit]
    docs: List[Dict[str, Any]] = []
    for src in sources:
        try:
            docs.append(translate_document(
                provider, src, store, translate_fn, render_dir, bilingual_dir,
                entity_store=entity_store, entity_review_queue=entity_review_queue,
            ))
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
    parser.add_argument("--mode", choices=("auto", "prepare", "finish", "verify", "status"), default="auto",
                        help="auto=自动执行器全程;prepare=导出 bundle;finish=吃 result 发布渲染;verify=独立核对落盘产物;status=只读查看 annotate 进度")
    parser.add_argument("--provider", required=True, choices=("pixiv", "fanbox"))
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--render-dir", type=Path, default=None)
    parser.add_argument("--jobs-dir", type=Path, default=None, help="mode=prepare 的 bundle 输出目录")
    parser.add_argument("--entity-store", type=Path, default=None,
                        help="可选实体库根目录;prepare 与 finish 必须传同一个(实体约束入 task 身份)")
    parser.add_argument("--entity-review-queue", type=Path, default=None,
                        help="本篇首次译名提案的 review 队列根目录(auto/finish 共用)")
    parser.add_argument("--results-dir", type=Path, default=None, help="mode=finish 的 agent result 目录")
    parser.add_argument("--bilingual-dir", type=Path, default=None, help="可选:已有 legacy 译文作 incumbent")
    parser.add_argument("--executor", default="openrouter", help="mode=auto 的执行器(openrouter)")
    parser.add_argument("--producer", default=None, help="mode=finish 从 TSV 组装 result 时记录的 producer 名")
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 篇(控成本)")
    parser.add_argument("--task-type", choices=("translate", "annotate"), default="translate",
                        help="annotate=陪读注解线(#174):prepare 出注解 job,finish 吃注解 TSV 建注解版本+渲染 study")
    parser.add_argument("--producer-priority", default=None,
                        help="annotate 多模型择优的 producer 优先级,逗号分隔(如 composer-2.5,luna)")
    args = parser.parse_args()
    for name, val in (("--store", args.store), ("--source-dir", args.source_dir)):
        if not str(val).strip() or str(val) == ".":
            parser.error(f"{name} 不能为空路径")

    if args.mode == "prepare":
        if not (args.jobs_dir and str(args.jobs_dir).strip()):
            parser.error("mode=prepare 需要非空 --jobs-dir")
        if args.task_type == "annotate":
            m = prepare_annotate_user(args.provider, args.source_dir, args.store, args.jobs_dir,
                                      entity_store=args.entity_store, limit=args.limit)
        else:
            m = prepare_user(args.provider, args.source_dir, args.store, args.jobs_dir,
                             bilingual_dir=args.bilingual_dir, entity_store=args.entity_store, limit=args.limit)
        print(json.dumps({"jobs": len([j for j in m["jobs"] if j.get("job")]), "jobs_dir": str(args.jobs_dir)}, ensure_ascii=False))
        return 0
    if args.mode == "status":
        if args.task_type != "annotate":
            parser.error("mode=status 当前只支持 --task-type annotate")
        m = status_annotate_user(args.provider, args.source_dir, args.store, args.render_dir,
                                 args.results_dir, jobs_dir=args.jobs_dir, limit=args.limit)
        print(json.dumps(m, ensure_ascii=False, indent=2))
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
        if args.task_type == "annotate":
            priority = [p.strip() for p in args.producer_priority.split(",")] if args.producer_priority else None
            m = finish_annotate_user(args.provider, args.source_dir, args.store, args.render_dir,
                                     args.results_dir, jobs_dir=args.jobs_dir,
                                     entity_store=args.entity_store, limit=args.limit,
                                     producer_name=args.producer, producer_priority=priority)
            failed = bool(m["summary"]["unresolved"] or m["summary"]["errors"])
            print(json.dumps(m if failed else m["summary"], ensure_ascii=False, indent=2 if failed else None))
            return 1 if failed else 0
        producer_name = args.producer or (args.executor if args.executor != "openrouter" else None)
        m = finish_user(args.provider, args.source_dir, args.store, args.render_dir, args.results_dir,
                        jobs_dir=args.jobs_dir, bilingual_dir=args.bilingual_dir,
                        entity_store=args.entity_store, entity_review_queue=args.entity_review_queue,
                        limit=args.limit,
                        producer_name=producer_name, model=args.model)
        failed = any(m["summary"][key] for key in ("quarantined", "unresolved", "qa_failed", "errors"))
        print(json.dumps(m if failed else m["summary"], ensure_ascii=False, indent=2 if failed else None))
        return 1 if failed else 0

    translate_fn = make_translate_fn(args.executor, args.model)
    manifest = translate_user(
        args.provider, args.source_dir, args.store, args.render_dir, translate_fn,
        bilingual_dir=args.bilingual_dir, entity_store=args.entity_store,
        entity_review_queue=args.entity_review_queue, limit=args.limit,
    )
    print(json.dumps(manifest["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
