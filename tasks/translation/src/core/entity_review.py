#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entity Linking 闸门 + review 队列(#83 P1b-2a)。

抽取名字是外部 producer 的活(LLM/agent/人);本模块只造闸门:把抽取出的 proposal 链接到既有
实体,产出 candidate 实体与待裁决的 review 项,人工 approve 才晋升——系统性回避 #61(输出不被信任)。
链接用精确匹配(mention == entity.source 或 ∈ aliases);决策见 import_proposals。
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .artifact_schemas import canonical_digest, canonical_dumps, validate_artifact
    from .entity_store import EntityStore, _pick_winner, _reachable_scopes, build_entity
except ImportError:  # core/ 在 sys.path 上
    from artifact_schemas import canonical_digest, canonical_dumps, validate_artifact
    from entity_store import EntityStore, _pick_winner, _reachable_scopes, build_entity

_FALLBACK_CREATED_AT = "1970-01-01T00:00:00Z"


def review_id_for(mention: str, document_id: str, segment_id: Optional[str], suggested_target: Optional[str]) -> str:
    """review_id 内容寻址 over proposal 本质 → 同 proposal 重导幂等(status/decided_by 可变不入身份)。"""
    payload = {
        "mention": mention,
        "document_id": document_id,
        "segment_id": segment_id,
        "suggested_target": suggested_target,
    }
    return "review_" + canonical_digest(payload)[:24]


def validate_review_identity(review: Dict[str, Any]) -> List[str]:
    expected = review_id_for(
        review.get("mention"), review.get("document_id"),
        review.get("segment_id"), review.get("suggested_target"),
    )
    if review.get("review_id") != expected:
        return [f"review_id 与 proposal 本质不符: 声明 {review.get('review_id')} 实算 {expected}"]
    return []


class ReviewQueue:
    """单文件 append/update 队列(review_id 唯一,resolution 更新同记录)。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "entity-review.jsonl"

    def list_all(self) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def list_pending(self) -> List[Dict[str, Any]]:
        return [r for r in self.list_all() if r.get("status") == "pending"]

    def get(self, review_id: str) -> Optional[Dict[str, Any]]:
        for r in self.list_all():
            if r["review_id"] == review_id:
                return r
        return None

    def put(self, review: Dict[str, Any]) -> Dict[str, Any]:
        errors = validate_artifact("entity-review", review)
        if errors:
            raise ValueError(f"entity-review schema 不合法: {errors}")
        id_errors = validate_review_identity(review)
        if id_errors:
            raise ValueError(f"entity-review 身份不符: {id_errors}")
        records = {r["review_id"]: r for r in self.list_all()}
        records[review["review_id"]] = review  # update 语义
        self._atomic_write(list(records.values()))
        return review

    def _atomic_write(self, records: List[Dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        body = "".join(canonical_dumps(r) + "\n" for r in records)
        fd, tmp = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _validate_proposal(p: Any) -> None:
    if not isinstance(p, dict):
        raise ValueError(f"proposal 必须是对象: {p!r}")
    if not p.get("mention"):
        raise ValueError(f"proposal 缺 mention: {p!r}")
    if not p.get("document_id"):
        raise ValueError(f"proposal 缺 document_id: {p!r}")
    conf = p.get("confidence")
    if not isinstance(conf, (int, float)) or not (0 <= conf <= 1):
        raise ValueError(f"proposal.confidence 必须是 0..1 的数: {p!r}")


def _creator_scope(scope_ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"level": "creator", "key": f"{scope_ctx['provider']}:{scope_ctx['creator_id']}"}


def import_proposals(
    proposals: List[Dict[str, Any]],
    scope_ctx: Dict[str, Any],
    entity_store: EntityStore,
    queue: ReviewQueue,
    *,
    threshold: float = 0.8,
    created_at: str = _FALLBACK_CREATED_AT,
) -> List[Dict[str, Any]]:
    """链接判定 + 入队。决策(精确匹配):
    - 命中既有实体 + confidence<threshold → review(low_confidence_match)
    - 命中 + suggested_target 与实体 target 冲突 → review(target_conflict)
    - 命中 + 高置信 + 不冲突 → no-op(已有实体覆盖,不排队)
    - 未命中 + 有 suggested_target → 建 candidate 实体(automatic, creator scope)+ review(new_candidate)
    - 未命中 + 无 suggested_target → review(unmatched_needs_target)
    返回新建/更新的 review 项。
    """
    reachable = _reachable_scopes(scope_ctx)
    out: List[Dict[str, Any]] = []
    for p in proposals:
        _validate_proposal(p)
        mention = p["mention"]
        document_id = p["document_id"]
        segment_id = p.get("segment_id")
        suggested = p.get("suggested_target")
        confidence = float(p["confidence"])

        review_id = review_id_for(mention, document_id, segment_id, suggested)
        existing = queue.get(review_id)
        if existing is not None and existing.get("status") != "pending":
            continue  # 已裁决的 review 不被重导重开/不再改实体(幂等,保住人工决定)

        matches = [
            e for scope in reachable for e in entity_store.list_scope(scope)
            if e["source"] == mention or mention in e.get("aliases", [])
        ]
        reason: Optional[str] = None
        candidate_entity_id: Optional[str] = None
        new_entity: Optional[Dict[str, Any]] = None

        if matches:
            winner = _pick_winner(matches)
            candidate_entity_id = winner["entity_id"]  # 仅作证据;命中类 review 不晋升/不改既有实体
            if confidence < threshold:
                reason = "low_confidence_match"
            elif suggested and suggested != winner["target"]:
                reason = "target_conflict"
            else:
                continue  # 干净高置信命中 → 不排队
        else:
            if suggested:
                new_entity = build_entity(
                    _creator_scope(scope_ctx), mention, suggested,
                    authority="automatic", status="candidate", updated_at=created_at,
                )
                candidate_entity_id = new_entity["entity_id"]
                reason = "new_candidate"
            else:
                reason = "unmatched_needs_target"

        review = {
            "schema_version": 1,
            "review_id": review_id,
            "mention": mention,
            "document_id": document_id,
            "confidence": confidence,
            "reason": reason,
            "status": "pending",
            "created_at": created_at,
        }
        if segment_id is not None:
            review["segment_id"] = segment_id
        if candidate_entity_id is not None:
            review["candidate_entity_id"] = candidate_entity_id
        if suggested is not None:
            review["suggested_target"] = suggested
        if p.get("context"):
            review["context"] = p["context"]
        # 先校验 review,再写实体:避免 review 不合法时遗留孤儿 candidate 实体(被 resolver 误捡)。
        errors = validate_artifact("entity-review", review) + validate_review_identity(review)
        if errors:
            raise ValueError(f"entity-review 不合法,放弃本 proposal(不写实体): {errors}")
        if new_entity is not None:
            entity_store.put(new_entity)
        queue.put(review)
        out.append(review)
    return out


def _find_entity(entity_store: EntityStore, scope_ctx: Dict[str, Any], entity_id: str) -> Optional[Dict[str, Any]]:
    for scope in _reachable_scopes(scope_ctx):
        for e in entity_store.list_scope(scope):
            if e["entity_id"] == entity_id:
                return e
    return None


def _set_entity_status(entity_store: EntityStore, entity: Dict[str, Any], status: str) -> None:
    e = dict(entity)
    e["status"] = status
    e["authority"] = "approved" if status == "approved" else ("manual" if status == "locked" else e["authority"])
    entity_store.put(e)


def resolve_review(
    review_id: str,
    decision: str,
    decided_by: str,
    queue: ReviewQueue,
    entity_store: EntityStore,
    scope_ctx: Dict[str, Any],
    *,
    locked: bool = False,
) -> Dict[str, Any]:
    """approve → 关联 candidate 实体 status candidate→approved(--locked 则 locked);dismiss → 实体保留 candidate。"""
    if decision not in ("approved", "dismissed"):
        raise ValueError("decision 必须是 approved 或 dismissed")
    review = queue.get(review_id)
    if review is None:
        raise ValueError(f"review 不存在: {review_id}")
    # 晋升与否取决于「被指实体当前是否仍是可晋升的自动候选」(status=candidate & authority=automatic),
    # 而非可变的 review.reason —— reason 会随重导在 new_candidate/low_confidence_match 间翻转(Codex #91)。
    # 既有 approved/locked/manual 实体不被 approve 改动(不降级 locked,Codex #90 F1)。
    if decision == "approved" and review.get("candidate_entity_id"):
        entity = _find_entity(entity_store, scope_ctx, review["candidate_entity_id"])
        if entity is not None and entity.get("status") == "candidate" and entity.get("authority") == "automatic":
            _set_entity_status(entity_store, entity, "locked" if locked else "approved")
    review = dict(review)
    review["status"] = decision
    review["decided_by"] = decided_by
    return queue.put(review)


def _scope_ctx_from_document(document_id: str) -> Dict[str, Any]:
    provider, creator_id, _ = document_id.split(":")
    return {"provider": provider, "creator_id": creator_id, "document_id": document_id}


def main() -> int:
    parser = argparse.ArgumentParser(description="Entity Linking review 队列闸门(#83 P1b-2a)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import", help="导入 proposals JSON → 链接 + 入队")
    imp.add_argument("--proposals", required=True, type=Path, help="proposals JSON 数组")
    imp.add_argument("--entity-store", required=True, type=Path)
    imp.add_argument("--queue", required=True, type=Path, help="review 队列根目录")
    imp.add_argument("--document", required=True, help="document_id(派生 scope)")
    imp.add_argument("--threshold", type=float, default=0.8)

    lst = sub.add_parser("list", help="列出 pending review")
    lst.add_argument("--queue", required=True, type=Path)

    for name in ("approve", "dismiss"):
        sp = sub.add_parser(name, help=f"{name} 一条 review")
        sp.add_argument("--review-id", required=True)
        sp.add_argument("--entity-store", required=True, type=Path)
        sp.add_argument("--queue", required=True, type=Path)
        sp.add_argument("--document", required=True, help="document_id(派生 scope)")
        sp.add_argument("--by", required=True, help="decided_by")
        if name == "approve":
            sp.add_argument("--locked", action="store_true", help="晋升为 locked(人工显式)")

    args = parser.parse_args()

    if args.cmd == "import":
        proposals = json.loads(args.proposals.read_text(encoding="utf-8"))
        if not isinstance(proposals, list):
            parser.error("--proposals 必须是 JSON 数组")
        out = import_proposals(
            proposals, _scope_ctx_from_document(args.document),
            EntityStore(args.entity_store), ReviewQueue(args.queue), threshold=args.threshold,
        )
        print(f"queued {len(out)} review items into {args.queue}")
        return 0
    if args.cmd == "list":
        for r in ReviewQueue(args.queue).list_pending():
            print(json.dumps(r, ensure_ascii=False))
        return 0
    # approve / dismiss
    decision = "approved" if args.cmd == "approve" else "dismissed"
    resolve_review(
        args.review_id, decision, args.by, ReviewQueue(args.queue),
        EntityStore(args.entity_store), _scope_ctx_from_document(args.document),
        locked=getattr(args, "locked", False),
    )
    print(f"{args.cmd} {args.review_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
