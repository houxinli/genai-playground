#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite 可重建投影:在 ArtifactStore(JSONL 工件)之上建只读派生索引,做跨文档查询。

**SQLite 只是投影,不是真相源**(§2.1):任何业务事实都在 JSON 工件里;删库可用 rebuild_index
从 JSONL 全量重建。document_id 由 shard 路径 `<kind>/<provider>/<creator>/<source>.jsonl` 推得
(attestation/evaluation 工件本身无 document_id 字段也能定位)。producer 在 attestation、verdict
在 evaluation;evaluation 无 segment_id,经 candidate_id join 取 segment。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE candidate (
    candidate_id TEXT PRIMARY KEY, document_id TEXT, provider TEXT, creator_id TEXT,
    source_id TEXT, revision_id TEXT, segment_id TEXT, source_hash TEXT, text_len INTEGER
);
CREATE TABLE attestation (
    attestation_id TEXT PRIMARY KEY, candidate_id TEXT, document_id TEXT,
    producer_type TEXT, producer_name TEXT, producer_model TEXT, purpose TEXT, legacy_label TEXT
);
CREATE TABLE evaluation (
    evaluation_id TEXT PRIMARY KEY, candidate_id TEXT, document_id TEXT, verdict TEXT
);
CREATE TABLE segment (
    revision_id TEXT, segment_id TEXT, document_id TEXT, provider TEXT, creator_id TEXT,
    source_id TEXT, seg_kind TEXT, PRIMARY KEY (revision_id, segment_id)
);
CREATE INDEX ix_cand_doc ON candidate(document_id);
CREATE INDEX ix_cand_seg ON candidate(document_id, segment_id);
CREATE INDEX ix_cand_author ON candidate(provider, creator_id);
CREATE INDEX ix_att_cand ON attestation(candidate_id);
CREATE INDEX ix_att_producer ON attestation(producer_name);
CREATE INDEX ix_eval_cand ON evaluation(candidate_id);
CREATE INDEX ix_eval_verdict ON evaluation(verdict);
"""

_INDEXED_KINDS = ("candidate", "attestation", "evaluation", "document-revision")


def _doc_parts(shard: Path):
    """从 shard 路径 .../<kind>/<provider>/<creator>/<source>.jsonl 还原 (provider, creator, source, document_id)。"""
    provider, creator_id, source_id = shard.parts[-3], shard.parts[-2], shard.stem
    return provider, creator_id, source_id, f"{provider}:{creator_id}:{source_id}"


def _read_jsonl(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def _insert(conn: sqlite3.Connection, kind: str, shard: Path) -> None:
    provider, creator_id, source_id, doc = _doc_parts(shard)
    for art in _read_jsonl(shard):
        if kind == "candidate":
            conn.execute(
                "INSERT OR REPLACE INTO candidate VALUES (?,?,?,?,?,?,?,?,?)",
                (art["candidate_id"], doc, provider, creator_id, source_id,
                 art.get("revision_id"), art.get("segment_id"), art.get("source_hash"),
                 len(art.get("text", ""))),
            )
        elif kind == "attestation":
            p = art.get("producer", {}) or {}
            conn.execute(
                "INSERT OR REPLACE INTO attestation VALUES (?,?,?,?,?,?,?,?)",
                (art["attestation_id"], art.get("candidate_id"), doc,
                 p.get("type"), p.get("name"), p.get("model"),
                 art.get("purpose"), art.get("legacy_label")),
            )
        elif kind == "evaluation":
            conn.execute(
                "INSERT OR REPLACE INTO evaluation VALUES (?,?,?,?)",
                (art["evaluation_id"], art.get("candidate_id"), doc, art.get("verdict")),
            )
        elif kind == "document-revision":
            for seg in art.get("segments", []):
                conn.execute(
                    "INSERT OR REPLACE INTO segment VALUES (?,?,?,?,?,?,?)",
                    (art["revision_id"], seg["segment_id"], doc, provider, creator_id,
                     source_id, seg.get("kind")),
                )


def rebuild_index(store_root: Path, db_path: Path) -> Dict[str, int]:
    """从 JSONL 工件全量重建 SQLite 投影(DROP+CREATE)。返回各表行数。"""
    store_root, db_path = Path(store_root), Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        for tbl in ("candidate", "attestation", "evaluation", "segment"):
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        conn.executescript(_SCHEMA)
        for kind in _INDEXED_KINDS:
            kind_dir = store_root / kind
            if not kind_dir.is_dir():
                continue
            for shard in sorted(kind_dir.rglob("*.jsonl")):
                _insert(conn, kind, shard)
        conn.commit()
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("candidate", "attestation", "evaluation", "segment")}
    finally:
        conn.close()
    return counts


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def segment_evidence(conn: sqlite3.Connection, document_id: str, segment_id: str) -> Dict[str, List[dict]]:
    """某 segment 的所有 candidate(含 producer/verdict join)+ attestation。"""
    cands = [dict(r) for r in conn.execute(
        """SELECT c.candidate_id, c.text_len, a.producer_name, a.producer_model, a.legacy_label, e.verdict
           FROM candidate c
           LEFT JOIN attestation a ON a.candidate_id = c.candidate_id
           LEFT JOIN evaluation e ON e.candidate_id = c.candidate_id
           WHERE c.document_id = ? AND c.segment_id = ?
           ORDER BY c.candidate_id""", (document_id, segment_id))]
    atts = [dict(r) for r in conn.execute(
        """SELECT a.attestation_id, a.candidate_id, a.producer_name, a.purpose, a.legacy_label
           FROM attestation a JOIN candidate c ON c.candidate_id = a.candidate_id
           WHERE c.document_id = ? AND c.segment_id = ?
           ORDER BY a.attestation_id""", (document_id, segment_id))]
    return {"candidates": cands, "attestations": atts}


def candidates_for_document(conn: sqlite3.Connection, document_id: str) -> List[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT candidate_id, segment_id, source_hash, text_len
           FROM candidate WHERE document_id = ? ORDER BY segment_id, candidate_id""", (document_id,))]


def evaluations_for_document(conn: sqlite3.Connection, document_id: str) -> List[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT e.evaluation_id, e.candidate_id, c.segment_id, e.verdict
           FROM evaluation e JOIN candidate c ON c.candidate_id = e.candidate_id
           WHERE e.document_id = ? ORDER BY c.segment_id, e.evaluation_id""", (document_id,))]


def candidates_for_author(conn: sqlite3.Connection, provider: str, creator_id: str) -> List[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT candidate_id, document_id, segment_id
           FROM candidate WHERE provider = ? AND creator_id = ?
           ORDER BY document_id, segment_id""", (provider, creator_id))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path, help="ArtifactStore 根目录")
    parser.add_argument("--db", required=True, type=Path, help="SQLite 投影输出路径")
    args = parser.parse_args()
    if not str(args.store).strip() or not str(args.db).strip():
        parser.error("--store / --db 不能为空")
    counts = rebuild_index(args.store, args.db)
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
