#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一 ArtifactStore:按 document 分片的 append-only JSONL + 原子批写 + 冲突/身份硬 gate。

设计见 system-design §2.7。要点:
- 分片路径 `store/<kind>/<provider>/<creator_id>/<source_id>.jsonl`,文件数=文档数而非 candidate 数;
  含冒号的 document_id 不直接当文件名,由三段拆出(document_id pattern 已保证 path-safe)。
- `put_many(document_id, artifacts)`:按 kind 分组 → 每(kind,document)一 shard → flock 锁 shard →
  读一次建 id map → 校验(schema + candidate 身份) → 冲突检测 → 写全量临时 shard + fsync +
  原子 rename + dir fsync。幂等仅凭 JSON 工件成立,不依赖任何外部索引。
- 冲突检测保留:同 id + 同 canonical payload skip,payload 不同 fatal(防 normalization 漂移/
  截断 digest/算法 bug/存储损坏)。candidate 写入前强制 `validate_candidate_identity`。
- `verify_references(artifact, resolver)`:cross-artifact 引用完整性,resolver 按 document 作用域解析;
  不替代 Task/Result stale-envelope 校验。
SQLite 投影(#55)只读本 store,不作第二个写入真相源。
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from .artifact_schemas import canonical_dumps, validate_artifact, validate_candidate_identity
except ImportError:  # core/ 在 sys.path 上
    from artifact_schemas import canonical_dumps, validate_artifact, validate_candidate_identity


def _segment_by_id(revision: Dict[str, Any], segment_id: str) -> Optional[Dict[str, Any]]:
    for seg in revision.get("segments", []):
        if seg.get("segment_id") == segment_id:
            return seg
    return None

# 每个 artifact kind 的自有 ID 字段(分片内幂等/冲突的主键)。
ID_FIELDS = {
    "document-revision": "revision_id",
    "candidate": "candidate_id",
    "attestation": "attestation_id",
    "evaluation": "evaluation_id",
    "document-version": "version_id",
    "annotation": "annotation_id",
}

# 提交顺序按引用依赖拓扑:被引用者先落盘。跨多 shard 无法做单事务原子提交(POSIX 多文件 rename
# 非事务),但按此序提交可保证任何崩溃前缀都引用完整(只会少写后续工件,可幂等重导补齐),不会
# 留下悬空引用。
COMMIT_ORDER = (
    "document-revision", "candidate", "attestation", "evaluation", "document-version", "annotation",
)

# 解析 (kind, artifact_id) → artifact 的作用域解析器。
Resolver = Callable[[str, str], Optional[Dict[str, Any]]]


class StoreConflictError(Exception):
    """同 id 不同 canonical payload:不可变工件被改/损坏/算法漂移,必须 fatal,不静默覆盖。"""


class StoreIntegrityError(Exception):
    """写入前 cross-artifact 引用完整性失败(悬空引用/source_hash 不符等),整批拒绝,不落盘。"""

    def __init__(self, reasons: List[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def verify_references(artifact: Dict[str, Any], resolver: Resolver) -> List[str]:
    """cross-artifact 引用完整性(system-design §2.7 integrity gate)。resolver 按 document 作用域
    解析 (kind, id)→工件。检查引用都指向真实工件、且业务不变量成立。**不替代** Task/Result
    stale-envelope 校验(那验 task_digest/result schema/执行边界)。返回错误列表,空=通过。"""
    kind = kind_of(artifact)
    errors: List[str] = []

    if kind == "candidate":
        errors += validate_candidate_identity(artifact)
        revision = resolver("document-revision", artifact["revision_id"])
        if revision is None:
            errors.append(f"candidate {artifact['candidate_id']}: revision {artifact['revision_id']} 不可解析")
        else:
            seg = _segment_by_id(revision, artifact["segment_id"])
            if seg is None:
                errors.append(f"candidate {artifact['candidate_id']}: segment {artifact['segment_id']} 不在 revision")
            elif seg.get("source_hash") != artifact["source_hash"]:
                errors.append(
                    f"candidate {artifact['candidate_id']}: source_hash {artifact['source_hash']} "
                    f"!= revision segment {seg.get('source_hash')}"
                )

    elif kind == "attestation":
        if resolver("candidate", artifact["candidate_id"]) is None:
            errors.append(f"attestation {artifact['attestation_id']}: candidate {artifact['candidate_id']} 不可解析")
        parent = artifact.get("parent_candidate_id")
        if parent is not None and resolver("candidate", parent) is None:
            errors.append(f"attestation {artifact['attestation_id']}: parent candidate {parent} 不可解析")

    elif kind == "evaluation":
        if resolver("candidate", artifact["candidate_id"]) is None:
            errors.append(f"evaluation {artifact['evaluation_id']}: candidate {artifact['candidate_id']} 不可解析")

    elif kind == "annotation":
        revision = resolver("document-revision", artifact["revision_id"])
        if revision is None:
            errors.append(f"annotation {artifact['annotation_id']}: revision {artifact['revision_id']} 不可解析")
        elif _segment_by_id(revision, artifact["segment_id"]) is None:
            errors.append(f"annotation {artifact['annotation_id']}: segment {artifact['segment_id']} 不在 revision")
        target = artifact.get("target_candidate_id")
        if target is not None:
            cand = resolver("candidate", target)
            if cand is None:
                errors.append(f"annotation {artifact['annotation_id']}: target candidate {target} 不可解析")
            else:
                if cand.get("revision_id") != artifact["revision_id"]:
                    errors.append(
                        f"annotation {artifact['annotation_id']}: target candidate revision "
                        f"{cand.get('revision_id')} != {artifact['revision_id']}"
                    )
                if cand.get("segment_id") != artifact["segment_id"]:
                    errors.append(
                        f"annotation {artifact['annotation_id']}: target candidate segment "
                        f"{cand.get('segment_id')} != {artifact['segment_id']}"
                    )

    elif kind == "document-version":
        parent = artifact.get("parent_version_id")
        if parent is not None and resolver("document-version", parent) is None:
            errors.append(f"version {artifact['version_id']}: parent version {parent} 不可解析")
        for segment_id, candidate_id in artifact.get("selections", {}).items():
            cand = resolver("candidate", candidate_id)
            if cand is None:
                errors.append(f"version {artifact['version_id']}: selection candidate {candidate_id} 不可解析")
                continue
            if cand.get("revision_id") != artifact.get("revision_id"):
                errors.append(
                    f"version {artifact['version_id']}: selection {candidate_id} 属于 revision "
                    f"{cand.get('revision_id')} != {artifact.get('revision_id')}"
                )
            if cand.get("segment_id") != segment_id:
                errors.append(
                    f"version {artifact['version_id']}: selection key segment {segment_id} "
                    f"!= candidate segment {cand.get('segment_id')}"
                )
        decisions = artifact.get("selection_decisions", {})
        if set(decisions) != set(artifact.get("selections", {})):
            errors.append(
                f"version {artifact['version_id']}: selection_decisions key 与 selections 不一致"
            )
        version_revision = artifact.get("revision_id")

        def _candidate_in_segment(candidate_id: str, segment_id: str, label: str) -> None:
            cand = resolver("candidate", candidate_id)
            if cand is None:
                errors.append(f"version {artifact['version_id']}: {label} {candidate_id} 不可解析")
                return
            if cand.get("revision_id") != version_revision:
                errors.append(
                    f"version {artifact['version_id']}: {label} {candidate_id} 属于 revision "
                    f"{cand.get('revision_id')} != {version_revision}"
                )
            if cand.get("segment_id") != segment_id:
                errors.append(
                    f"version {artifact['version_id']}: {label} {candidate_id} segment "
                    f"{cand.get('segment_id')} != {segment_id}"
                )

        for segment_id, decision in decisions.items():
            incumbent = decision.get("incumbent_candidate_id")
            if incumbent is not None:
                _candidate_in_segment(incumbent, segment_id, f"decision[{segment_id}] incumbent")
            for eval_id in decision.get("evaluation_ids", []):
                evaluation = resolver("evaluation", eval_id)
                if evaluation is None:
                    errors.append(
                        f"version {artifact['version_id']}: decision[{segment_id}] evaluation "
                        f"{eval_id} 不可解析"
                    )
                    continue
                # 证据必须确实评的是本 segment/revision 的候选,不能借用别处的 evaluation。
                _candidate_in_segment(
                    evaluation.get("candidate_id"), segment_id, f"decision[{segment_id}] evaluation {eval_id} candidate"
                )

    return errors


def kind_of(artifact: Dict[str, Any]) -> str:
    """由自有/判别字段推断 artifact kind(工件不显式带 kind)。引用字段(如 candidate_id 出现在
    attestation/evaluation 上)不参与判别 → 先判唯一自有 id,candidate 兜底。"""
    if "attestation_id" in artifact:
        return "attestation"
    if "evaluation_id" in artifact:
        return "evaluation"
    if "version_id" in artifact:
        return "document-version"
    if "annotation_id" in artifact:
        return "annotation"
    if "segments" in artifact and "revision_id" in artifact:
        return "document-revision"
    if "candidate_id" in artifact and "text" in artifact and "normalization_version" in artifact:
        return "candidate"
    raise ValueError(f"cannot infer artifact kind from fields: {sorted(artifact)[:6]}")


def _split_document_id(document_id: str) -> Tuple[str, str, str]:
    parts = document_id.split(":")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"invalid document_id (expect provider:creator_id:source_id): {document_id!r}")
    for part in parts:
        if "/" in part or part in ("", ".", ".."):
            raise ValueError(f"unsafe document_id component {part!r} in {document_id!r}")
    return parts[0], parts[1], parts[2]


def _read_shard(path: Path) -> Dict[str, Dict[str, Any]]:
    """把一个 JSONL shard 读成 id->artifact;空/不存在返回空 map。"""
    if not path.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        artifact = json.loads(line)
        out[artifact[ID_FIELDS[kind_of(artifact)]]] = artifact
    return out


def _atomic_write_shard(path: Path, artifacts: List[Dict[str, Any]]) -> None:
    """写全量 shard:同目录临时文件 + fsync + 原子 rename + dir fsync(中断不留半截 JSONL)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for artifact in artifacts:
            fh.write(json.dumps(artifact, ensure_ascii=False, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


class ArtifactStore:
    """单机优先的工件存储:JSON 是真相源,按文档分片,写入是唯一边界(schema+身份+冲突 gate)。"""

    def __init__(self, root: Path):
        self.root = Path(root)

    def shard_path(self, kind: str, document_id: str) -> Path:
        if kind not in ID_FIELDS:
            raise ValueError(f"unknown artifact kind: {kind!r}")
        provider, creator_id, source_id = _split_document_id(document_id)
        return self.root / kind / provider / creator_id / f"{source_id}.jsonl"

    def _validate(self, kind: str, artifact: Dict[str, Any]) -> None:
        errors = validate_artifact(kind, artifact)
        if errors:
            raise ValueError(f"{kind} schema invalid: {errors}")
        if kind == "candidate":
            id_errors = validate_candidate_identity(artifact)
            if id_errors:
                raise ValueError(f"candidate identity invalid: {id_errors}")

    def put_many(
        self, document_id: str, artifacts: List[Dict[str, Any]], verify: bool = True
    ) -> Dict[str, Any]:
        """把一批工件原子写入对应文档分片(写入边界唯一 gate)。两阶段保证"任一失败不落半批":
        阶段A 锁住全部相关 shard → 校验(schema + candidate 身份 + document_id 一致) → 冲突预检 →
              (verify 时)对全部 staged 工件跑 verify_references(resolver=现有∪本批 staged);
        阶段B 全部预检通过后,再统一对有变更的 shard 原子提交。
        verify=False 仅供测试纯机制(分片/冲突),生产路径默认强制 integrity。"""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for artifact in artifacts:
            kind = kind_of(artifact)
            self._validate(kind, artifact)  # schema + candidate 身份
            if "document_id" in artifact and artifact["document_id"] != document_id:
                raise ValueError(
                    f"{kind} 自带 document_id {artifact['document_id']} != 分片键 {document_id}"
                    "(拒绝路由到错误文档 shard)"
                )
            grouped.setdefault(kind, []).append(artifact)

        # 固定按 kind 排序加锁,避免并发 put_many 因加锁顺序不同而死锁。
        with contextlib.ExitStack() as stack:
            shards: Dict[str, Dict[str, Any]] = {}
            combined: Dict[Tuple[str, str], Dict[str, Any]] = {}  # (kind,id)->工件:现有∪staged
            for kind in sorted(grouped):
                id_field = ID_FIELDS[kind]
                path = self.shard_path(kind, document_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                lock_fh = stack.enter_context(path.with_suffix(path.suffix + ".lock").open("w"))
                fcntl.flock(lock_fh, fcntl.LOCK_EX)
                existing = _read_shard(path)
                for aid, art in existing.items():
                    combined[(kind, aid)] = art
                staged: Dict[str, Dict[str, Any]] = {}
                skipped_ids: List[str] = []
                for artifact in grouped[kind]:
                    aid = artifact[id_field]
                    prior = staged.get(aid) or existing.get(aid)
                    if prior is not None:
                        if canonical_dumps(prior) == canonical_dumps(artifact):
                            if aid not in staged:
                                skipped_ids.append(aid)
                            continue
                        raise StoreConflictError(
                            f"{kind} {aid} 已存在且内容不同({path});拒绝覆盖不可变工件"
                        )
                    staged[aid] = artifact
                    combined[(kind, aid)] = artifact
                shards[kind] = {"path": path, "existing": existing,
                                "staged": staged, "skipped_ids": skipped_ids}

            if verify:
                # 本批(现有∪staged)优先;不在本批的 kind(如更早入库的 revision)回落到已提交 shard。
                def resolver(k: str, i: str) -> Optional[Dict[str, Any]]:
                    if (k, i) in combined:
                        return combined[(k, i)]
                    return self.get(k, document_id, i)
                errors: List[str] = []
                for sh in shards.values():
                    for artifact in sh["staged"].values():
                        errors += verify_references(artifact, resolver)
                if errors:
                    raise StoreIntegrityError(errors)

            # 阶段B:全部预检通过后提交。逻辑失败已在阶段A排除;此处仅剩物理写。按引用依赖序
            # (被引用者先,见 COMMIT_ORDER)提交,使任何物理中断的崩溃前缀都引用完整、无悬空引用。
            report: Dict[str, Any] = {"document_id": document_id, "kinds": {}}
            for kind in sorted(shards, key=COMMIT_ORDER.index):
                sh = shards[kind]
                if sh["staged"]:
                    _atomic_write_shard(sh["path"], list(sh["existing"].values()) + list(sh["staged"].values()))
                report["kinds"][kind] = {
                    "written": len(sh["staged"]), "skipped": len(sh["skipped_ids"]),
                    "written_ids": list(sh["staged"].keys()), "skipped_ids": sh["skipped_ids"],
                }
            return report

    def put(self, document_id: str, artifact: Dict[str, Any], verify: bool = True) -> Dict[str, Any]:
        """单工件写入,委托给 put_many。"""
        return self.put_many(document_id, [artifact], verify=verify)

    def get(self, kind: str, document_id: str, artifact_id: str) -> Optional[Dict[str, Any]]:
        return _read_shard(self.shard_path(kind, document_id)).get(artifact_id)

    def exists(self, kind: str, document_id: str, artifact_id: str) -> bool:
        return self.get(kind, document_id, artifact_id) is not None

    def list_shard(self, kind: str, document_id: str) -> List[Dict[str, Any]]:
        return list(_read_shard(self.shard_path(kind, document_id)).values())

    def resolver_for(self, document_id: str) -> Resolver:
        """返回按 document 作用域的解析器,供 verify_references 解引用同文档工件。"""
        return lambda kind, artifact_id: self.get(kind, document_id, artifact_id)
