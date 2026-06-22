#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export-job:从 DocumentRevision + 选定 segment 生成 Task 与自包含 job bundle。

执行器(编码 agent / API)消费 job bundle:bundle 含 Task(身份/约束/segment 列表)与每个
segment 的源文本,执行器据此产出 Result,再经 result_import 落 candidate。
task_id 由内容确定性派生 → 同一 job 重复导出得到同一 task_id 与 task_digest(与 import 端一致)。
此处只生成 Task,不调度、不写 candidate。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .artifact_schemas import canonical_digest, canonical_dumps, validate_artifact
    from .source_identity import _source_hash
except ImportError:  # 作为脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.artifact_schemas import canonical_digest, canonical_dumps, validate_artifact
    from core.source_identity import _source_hash

DEFAULT_CONSTRAINTS = {"output_language": "zh-CN", "preserve_line_count": True}


def _verify_segment_integrity(seg: Dict[str, Any]) -> None:
    """导出前核对 segment 自洽:source_hash 与 source_text 一致、segment_id 内嵌 hash 前缀匹配。
    防止被篡改/损坏的 revision(改了 source_text 却没更新 hash)绕过 stale-result 防护。"""
    expected = _source_hash(seg["source_text"])
    if seg["source_hash"] != expected:
        raise ValueError(
            f"segment {seg['segment_id']}: source_hash {seg['source_hash']} != sha256(source_text) {expected}"
        )
    prefix = seg["segment_id"].rsplit(":", 1)[1]
    if not seg["source_hash"].startswith(prefix):
        raise ValueError(f"segment {seg['segment_id']}: id hash prefix does not match source_hash")


def _segments_by_id(revision: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {s["segment_id"]: s for s in revision["segments"]}


def export_task(
    revision: Dict[str, Any],
    segment_ids: List[str],
    task_type: str = "translate",
    constraints: Optional[Dict[str, Any]] = None,
    knowledge_snapshot_id: Optional[str] = None,
    existing_candidate_ids: Optional[List[str]] = None,
    annotation_ids: Optional[List[str]] = None,
    context_pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建一个 schema 合法的 Task。segment_ids 必须属于该 revision。"""
    segs = _segments_by_id(revision)
    if not segment_ids:
        raise ValueError("segment_ids must not be empty")
    unknown = [sid for sid in segment_ids if sid not in segs]
    if unknown:
        raise ValueError(f"segment_ids not in revision: {unknown}")
    ordered = sorted(segment_ids)
    for sid in ordered:
        _verify_segment_integrity(segs[sid])
    source_hashes = {sid: segs[sid]["source_hash"] for sid in ordered}
    constraints = dict(constraints or DEFAULT_CONSTRAINTS)
    existing = sorted(existing_candidate_ids or [])
    annotations = sorted(annotation_ids or [])

    # context_digest:覆盖参与本 task 的源内容、约束与 Context Pack,内容变即新 task。
    # context_pack(术语/实体/邻句)影响译文,必须进身份(#77 纪律:语义输入不进身份会同 id 异义)。
    context_digest = canonical_digest({
        "revision_id": revision["revision_id"],
        "segments": [{"segment_id": sid, "source_text": segs[sid]["source_text"]} for sid in ordered],
        "task_type": task_type,
        "constraints": constraints,
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "context_pack": context_pack,
    })
    # task_id:由身份内容确定性派生 → 同一 job 重复导出稳定;覆盖所有影响执行语义的引用字段。
    task_id = "task_" + hashlib.sha256(
        canonical_dumps({
            "document_id": revision["document_id"],
            "revision_id": revision["revision_id"],
            "segment_ids": ordered,
            "task_type": task_type,
            "context_digest": context_digest,
            "knowledge_snapshot_id": knowledge_snapshot_id,
            "existing_candidate_ids": existing,
            "annotation_ids": annotations,
        }).encode("utf-8")
    ).hexdigest()[:24]

    task = {
        "schema_version": 1,
        "task_id": task_id,
        "task_type": task_type,
        "document_id": revision["document_id"],
        "revision_id": revision["revision_id"],
        "segment_ids": ordered,
        "source_hashes": source_hashes,
        "context_digest": context_digest,
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "constraints": constraints,
        "existing_candidate_ids": existing,
        "annotation_ids": annotations,
        "expected_result_schema": 1,
    }
    errors = validate_artifact("task", task)
    if errors:
        raise ValueError(f"exported task invalid: {errors}")
    return task


def _validate_constraints(items: Any, kind: str) -> None:
    """约束必须是「对象数组」且每项含非空 source+target —— 否则 fail fast。

    防止误传(单个对象当数组、拼错键导致 None)被静默吞掉:那会让长 harness 跑出**无约束**译文
    却仍产出可导入 bundle(Codex #86 review)。"""
    if items is None:
        return
    if not isinstance(items, list):
        raise ValueError(f"context_pack.{kind} 必须是对象数组,得到 {type(items).__name__}")
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise ValueError(f"context_pack.{kind}[{i}] 必须是对象,得到 {type(it).__name__}")
        missing = [k for k in ("source", "target") if not it.get(k)]
        if missing:
            raise ValueError(f"context_pack.{kind}[{i}] 缺必填字段 {missing}: {it}")


def build_context_pack(
    revision: Dict[str, Any],
    segment_ids: List[str],
    terminology: Optional[List[Dict[str, Any]]] = None,
    entities: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """构建最小 Context Pack(#83 P1a):隔离执行器据此施加术语/实体硬约束并参考邻句。

    - terminology / entities 由调用方提供(P1a 不建 Entity Store):各为约束列表,按 canonical 形排序
      以保证 task 身份确定性。entity 形如 {source, target, aliases?, forbidden?, scope?}。
    - neighbors 由 revision 的 body 顺序派生:每个被选 body segment 的前/后一条 body 源句(给跨句上下文,
      即便只翻子集)。metadata segment 不取邻句。
    """
    _validate_constraints(terminology, "terminology")
    _validate_constraints(entities, "entities")
    segs = _segments_by_id(revision)
    body_order = [s["segment_id"] for s in revision["segments"] if s["kind"] == "body"]
    body_index = {sid: i for i, sid in enumerate(body_order)}
    neighbors: Dict[str, Dict[str, str]] = {}
    for sid in sorted(segment_ids):
        if sid not in body_index:
            continue
        i = body_index[sid]
        entry: Dict[str, str] = {}
        if i > 0:
            entry["prev"] = segs[body_order[i - 1]]["source_text"]
        if i + 1 < len(body_order):
            entry["next"] = segs[body_order[i + 1]]["source_text"]
        if entry:
            neighbors[sid] = entry
    return {
        "terminology": sorted(list(terminology or []), key=canonical_dumps),
        "entities": sorted(list(entities or []), key=canonical_dumps),
        "neighbors": neighbors,
    }


def export_job(
    revision: Dict[str, Any],
    segment_ids: List[str],
    terminology: Optional[List[Dict[str, Any]]] = None,
    entities: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """自包含 job bundle:Task + 每个 segment 的源文本 + Context Pack(执行器据此翻译)。

    task_digest 在 bundle 内给出,供执行器原样回填到 Result.task_digest,避免重算口径不一致。
    Context Pack(术语/实体/邻句,#83 P1a)内联进 bundle,折入 task 身份(见 export_task)。
    仍只支持无外部引用的 translate task:knowledge_snapshot / existing_candidate / annotation 是对
    外部工件的引用,需把被引内容打进 bundle 才自包含,留待 #83 P1b——否则隔离执行器拿不到内容。
    """
    if kwargs.get("task_type", "translate") != "translate":
        raise ValueError("export_job 目前只支持 translate task(其它类型需 #83 P1b context builder)")
    for ref in ("knowledge_snapshot_id", "existing_candidate_ids", "annotation_ids"):
        if kwargs.get(ref):
            raise ValueError(f"export_job 暂不支持带 {ref} 的 job(对外部工件的引用需 #83 P1b 打包)")
    context_pack = build_context_pack(revision, segment_ids, terminology, entities)
    task = export_task(revision, segment_ids, context_pack=context_pack, **kwargs)
    segs = _segments_by_id(revision)
    return {
        "task": task,
        "task_digest": canonical_digest(task),
        "segments": [
            {"segment_id": sid, "kind": segs[sid]["kind"], "source_text": segs[sid]["source_text"]}
            for sid in task["segment_ids"]
        ],
        "context_pack": context_pack,
    }


def ingest_revision(revision: Dict[str, Any], store: Any) -> Dict[str, Any]:
    """把源 DocumentRevision 幂等写入分片 ArtifactStore,作为 translate→import 闭环的入库点。

    import_result 的 integrity gate 要求同文档 revision shard 已存在;构 bundle 的 orchestrator
    本就持有 revision,故在此入库(store 仍是唯一真相源)。put_many 幂等:同 revision 重复 export 跳过。
    写库前对完整 revision 做 schema + 身份自洽校验(store._validate 不重算 revision 身份),拒绝把被
    编辑/损坏但仍过 schema 的 revision 落盘——否则坏 payload 入库或日后同 ID 冲突。
    """
    try:
        from .source_identity import verify_revision_identity
    except ImportError:
        from source_identity import verify_revision_identity
    errors = validate_artifact("document-revision", revision) + verify_revision_identity(revision)
    if errors:
        raise ValueError(f"refusing to ingest invalid revision: {errors}")
    return store.put_many(revision["document_id"], [revision])


def revision_from_source(provider: str, source_dir: Path, document_id: str) -> Dict[str, Any]:
    """只定位并构建指定 document 的 DocumentRevision——不解析整目录,无关文件的错误不影响目标。"""
    try:
        from .source_identity import build_document_revision
    except ImportError:
        from core.source_identity import build_document_revision
    source_id = document_id.rsplit(":", 1)[-1]
    path = Path(source_dir) / f"{source_id}.txt"
    if not path.is_file():
        raise ValueError(f"source file for {document_id} not found: {path}")
    rev = build_document_revision(provider, path)
    if rev["document_id"] != document_id:
        raise ValueError(f"built document_id {rev['document_id']} != requested {document_id}")
    return rev


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", type=Path, help="document-revision.json(与 --source-dir 二选一)")
    parser.add_argument("--source-dir", type=Path, help="源目录,配合 --provider/--document 现场适配 revision")
    parser.add_argument("--provider", choices=("pixiv", "fanbox"))
    parser.add_argument("--document", help="document_id,如 pixiv:18330282:27466576")
    parser.add_argument("--segment", action="append", default=None, help="repeatable;默认全部 body segment")
    parser.add_argument("--task-type", default="translate")
    parser.add_argument("--out", required=True, type=Path, help="job bundle 输出 json")
    parser.add_argument(
        "--store", type=str, default=None,
        help="ArtifactStore 根目录;给定则把源 revision 幂等入库(import-result 闭环前置)",
    )
    parser.add_argument(
        "--context", type=Path, default=None,
        help="可选 Context Pack 输入 JSON:{\"terminology\":[...],\"entities\":[...]};neighbors 自动派生",
    )
    args = parser.parse_args()

    # 区分"未传"(None,不入库)与"传了空串"(明显误用,如 Make 漏传 STORE=)——空串不能静默落到 cwd。
    if args.store is not None and not args.store.strip():
        parser.error("--store 不能为空路径")

    if args.revision:
        revision = json.loads(args.revision.read_text(encoding="utf-8"))
    elif args.source_dir and args.provider and args.document:
        revision = revision_from_source(args.provider, args.source_dir, args.document)
    else:
        parser.error("需 --revision,或 --source-dir + --provider + --document")

    if args.store:
        try:
            from .artifact_store import ArtifactStore
        except ImportError:
            from core.artifact_store import ArtifactStore
        ingest_revision(revision, ArtifactStore(Path(args.store)))

    terminology = entities = None
    if args.context:
        ctx = json.loads(args.context.read_text(encoding="utf-8"))
        if not isinstance(ctx, dict):
            parser.error("--context 必须是 JSON 对象 {terminology?, entities?}")
        unknown = sorted(set(ctx) - {"terminology", "entities"})
        if unknown:
            parser.error(f"--context 含未知顶层键 {unknown}(只允许 terminology/entities;防拼错被静默吞掉)")
        terminology = ctx.get("terminology")
        entities = ctx.get("entities")

    # 默认导出全部可翻译段(body + metadata.*),否则 metadata 无候选会导致渲染缺译文
    segment_ids = args.segment or [s["segment_id"] for s in revision["segments"]]
    bundle = export_job(
        revision, segment_ids, terminology=terminology, entities=entities, task_type=args.task_type
    )
    args.out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    store_note = f" store={args.store}" if args.store else ""
    print(f"task_id={bundle['task']['task_id']} segments={len(bundle['segments'])} out={args.out}{store_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
