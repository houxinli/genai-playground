#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scoped 实体库(#83 P1b):人名/专名标准译名与坏译禁用,按作用域解析喂 Context Pack。

与 per-document Artifact Store 并列、独立:实体跨文档(scoped 到 creator/series/global),
按 scope 分片 `entities/<level>/<key>.jsonl`,**update 语义**(同 entity_id 覆盖,非 append)。
entity_id 由 scope+source 内容寻址稳定;记录可更新——可复现性由 task 端冻结 Context Pack 保证。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .artifact_schemas import canonical_digest, canonical_dumps, validate_artifact
except ImportError:  # core/ 在 sys.path 上
    from artifact_schemas import canonical_digest, canonical_dumps, validate_artifact

# scope 特异性:数值越大越具体。
_SCOPE_SPECIFICITY = {"global": 0, "provider": 1, "creator": 2, "series": 3, "document": 4}
_AUTHORITY = ("manual", "approved", "automatic")
_STATUS = ("locked", "approved", "candidate")


def entity_id_for(scope: Dict[str, Any], source: str) -> str:
    """entity_id 稳定内容寻址:同 (scope, source) 永远同 id;改 target/aliases 不改 id。"""
    return "entity_" + canonical_digest({"scope": scope, "source": source})[:24]


def _validate_scope(scope: Any) -> None:
    if not isinstance(scope, dict) or "level" not in scope or "key" not in scope:
        raise ValueError(f"entity.scope 必须是 {{level,key}}: {scope!r}")
    level, key = scope["level"], scope["key"]
    if level not in _SCOPE_SPECIFICITY:
        raise ValueError(f"未知 scope.level: {level!r}")
    if level == "global" and key is not None:
        raise ValueError("scope.level=global 时 key 必须为 null")
    if level != "global" and not (isinstance(key, str) and key):
        raise ValueError(f"scope.level={level} 时 key 必须为非空字符串")


def validate_entity_identity(entity: Dict[str, Any]) -> List[str]:
    """entity_id 必须 == 由 scope+source 重算(防 schema 过但 id 与定义字段不符)。"""
    expected = entity_id_for(entity.get("scope"), entity.get("source"))
    if entity.get("entity_id") != expected:
        return [f"entity_id 与 scope+source 不符: 声明 {entity.get('entity_id')} 实算 {expected}"]
    return []


def _safe_key(key: Optional[str]) -> str:
    """scope.key → path-safe 且**无碰撞**的文件名。

    仅做字符替换会让 `pixiv:a_b:c` 与 `pixiv:a:b_c` 撞同名 → 跨 scope 串读(Codex #88)。故在
    可读前缀后接全 key 的 sha8,保证每个 key 唯一映射一个分片文件。"""
    if key is None:
        return "_global"
    prefix = "".join(c if (c.isalnum() or c in "-_") else "_" for c in key)[:48]
    return f"{prefix}__{hashlib.sha256(key.encode('utf-8')).hexdigest()[:8]}"


class EntityStore:
    """按 scope 分片的实体库;put 为 update 语义(同 entity_id 覆盖)。"""

    def __init__(self, root: Path):
        self.root = Path(root)

    def shard_path(self, scope: Dict[str, Any]) -> Path:
        _validate_scope(scope)
        return self.root / scope["level"] / f"{_safe_key(scope['key'])}.jsonl"

    def list_scope(self, scope: Dict[str, Any]) -> List[Dict[str, Any]]:
        path = self.shard_path(scope)
        if not path.is_file():
            return []
        out: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("scope") != scope:  # 分片应 1:1 对应 scope;不符=碰撞/损坏,拒绝静默串读
                raise ValueError(f"entity 分片 {path} 含异 scope 记录 {rec.get('scope')} != {scope}")
            out.append(rec)
        return out

    def put(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """校验 + 写入(同 entity_id 覆盖)。fail-fast:schema/身份/字段不合即 raise,不静默落盘。"""
        errors = validate_artifact("entity", entity)
        if errors:
            raise ValueError(f"entity schema 不合法: {errors}")
        _validate_scope(entity["scope"])
        id_errors = validate_entity_identity(entity)
        if id_errors:
            raise ValueError(f"entity 身份不符: {id_errors}")
        path = self.shard_path(entity["scope"])
        records = {r["entity_id"]: r for r in self.list_scope(entity["scope"])}
        records[entity["entity_id"]] = entity  # update 语义
        self._atomic_write(path, list(records.values()))
        return entity

    @staticmethod
    def _atomic_write(path: Path, records: List[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(canonical_dumps(r) + "\n" for r in records)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _reachable_scopes(scope_ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """由文档 scope 上下文展开可达 scope 链(global→…→document),缺项跳过。

    scope_ctx: {provider, creator_id, series?, document_id}。
    key 约定:provider=<provider>;creator=<provider>:<creator_id>;series=<provider>:<creator_id>:<series>;
    document=<document_id>。
    """
    provider = scope_ctx.get("provider")
    creator = scope_ctx.get("creator_id")
    series = scope_ctx.get("series")
    document = scope_ctx.get("document_id")
    scopes: List[Dict[str, Any]] = [{"level": "global", "key": None}]
    if provider:
        scopes.append({"level": "provider", "key": provider})
        if creator:
            scopes.append({"level": "creator", "key": f"{provider}:{creator}"})
            if series:
                scopes.append({"level": "series", "key": f"{provider}:{creator}:{series}"})
    if document:
        scopes.append({"level": "document", "key": document})
    return scopes


def _pick_winner(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """同一 source 跨 scope 选胜出者:scope 特异性优先;locked 不被更具体作用域里的非 locked/非 manual 覆盖。"""
    ordered = sorted(records, key=lambda r: _SCOPE_SPECIFICITY[r["scope"]["level"]], reverse=True)
    winner = ordered[0]
    for r in ordered[1:]:  # 越来越不具体
        if r.get("status") == "locked" and winner.get("status") != "locked" and winner.get("authority") != "manual":
            winner = r
    return winner


def resolve_entities(
    scope_ctx: Dict[str, Any],
    text: str,
    store: EntityStore,
) -> List[Dict[str, Any]]:
    """解析文档相关实体 → Context Pack entity 约束 {source,target,aliases?,forbidden?,scope?}。

    只注「相关」(§7.1):实体 source 或任一 alias 作为子串出现在 text 才注入,避免全局词典塞 prompt。
    同一 source 跨可达 scope 取胜出者(见 _pick_winner)。结果按 source 排序,确定性。
    """
    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for scope in _reachable_scopes(scope_ctx):
        for rec in store.list_scope(scope):
            if rec.get("status") == "candidate":
                continue
            by_source.setdefault(rec["source"], []).append(rec)

    out: List[Dict[str, Any]] = []
    for source, recs in by_source.items():
        winner = _pick_winner(recs)
        mentions = [source] + list(winner.get("aliases", []))
        if not any(m in text for m in mentions):
            continue  # 文档没出现 → 不注入
        constraint: Dict[str, Any] = {"source": source, "target": winner["target"]}
        if winner.get("aliases"):
            constraint["aliases"] = winner["aliases"]
        if winner.get("forbidden"):
            constraint["forbidden"] = winner["forbidden"]
        constraint["scope"] = winner["scope"]
        out.append(constraint)
    return sorted(out, key=lambda c: c["source"])


def build_entity(
    scope: Dict[str, Any],
    source: str,
    target: str,
    *,
    aliases: Optional[List[str]] = None,
    forbidden: Optional[List[str]] = None,
    readings: Optional[List[str]] = None,
    type: str = "person",
    authority: str = "manual",
    status: str = "approved",
    updated_at: str = "1970-01-01T00:00:00Z",
) -> Dict[str, Any]:
    """组装完整 entity(补 schema_version 与确定性 entity_id)。播种/工具用。"""
    entity = {
        "schema_version": 1,
        "entity_id": entity_id_for(scope, source),
        "scope": scope,
        "source": source,
        "target": target,
        "type": type,
        "authority": authority,
        "status": status,
        "updated_at": updated_at,
    }
    if readings:
        entity["readings"] = readings
    if aliases:
        entity["aliases"] = aliases
    if forbidden:
        entity["forbidden"] = forbidden
    return entity


def _parse_rules_text(text: str) -> List[Dict[str, Any]]:
    """人工规则文本 → [{source, target, forbidden?}]。每行 `源=译名` 或 `源=译名|坏译1,坏译2`;
    `#` 开头或空行跳过。只接受人工 curated 规则(不导入自动 namefix 报告——那是垃圾)。"""
    rules: List[Dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"规则行缺 '=': {line!r}")
        source, rhs = (p.strip() for p in line.split("=", 1))
        target, _, forb = rhs.partition("|")
        target = target.strip()
        if not source or not target:
            raise ValueError(f"规则行 source/target 不能为空: {line!r}")
        rule: Dict[str, Any] = {"source": source, "target": target}
        forbidden = [f.strip() for f in forb.split(",") if f.strip()]
        if forbidden:
            rule["forbidden"] = forbidden
        rules.append(rule)
    return rules


def main() -> int:
    parser = argparse.ArgumentParser(description="实体库播种:从人工 curated 规则建 manual 实体")
    parser.add_argument("--store", required=True, type=Path, help="实体库根目录")
    parser.add_argument("--scope-level", required=True, choices=tuple(_SCOPE_SPECIFICITY))
    parser.add_argument("--scope-key", default=None, help="非 global 必填,如 pixiv:50235390")
    parser.add_argument("--rules", required=True, type=Path, help="规则文件(.json 列表 或 文本 源=译名|坏译)")
    parser.add_argument("--status", default="approved", choices=tuple(_STATUS))
    args = parser.parse_args()

    scope = {"level": args.scope_level, "key": args.scope_key}
    try:
        _validate_scope(scope)
    except ValueError as exc:
        parser.error(str(exc))

    raw = args.rules.read_text(encoding="utf-8")
    if args.rules.suffix == ".json":
        rules = json.loads(raw)
        if not isinstance(rules, list):
            parser.error("--rules JSON 必须是对象数组")
    else:
        rules = _parse_rules_text(raw)

    store = EntityStore(args.store)
    written = 0
    for r in rules:
        entity = build_entity(
            scope, r["source"], r["target"],
            aliases=r.get("aliases"), forbidden=r.get("forbidden"), readings=r.get("readings"),
            type=r.get("type", "person"), authority="manual", status=args.status,
        )
        store.put(entity)
        written += 1
    print(f"seeded {written} entities into {args.store} scope={args.scope_level}:{args.scope_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
