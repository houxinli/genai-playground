#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entity Linking 闸门(#83 P1b-2a):决策树/队列 update 语义/身份 gate/晋升。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from .entity_review import (
        ReviewQueue,
        import_proposals,
        resolve_review,
        review_id_for,
    )
    from .entity_store import EntityStore, build_entity
except ImportError:  # core/ 在 sys.path 上
    from entity_review import ReviewQueue, import_proposals, resolve_review, review_id_for
    from entity_store import EntityStore, build_entity


DOC = "pixiv:50235390:12430834"
CTX = {"provider": "pixiv", "creator_id": "50235390", "document_id": DOC}
CREATOR = {"level": "creator", "key": "pixiv:50235390"}


def _proposal(mention, *, target=None, confidence=0.95, segment_id=None, context=None):
    p = {"mention": mention, "document_id": DOC, "confidence": confidence}
    if target is not None:
        p["suggested_target"] = target
    if segment_id is not None:
        p["segment_id"] = segment_id
    if context is not None:
        p["context"] = context
    return p


class Harness:
    def __init__(self, tmp):
        self.estore = EntityStore(Path(tmp) / "ent")
        self.queue = ReviewQueue(Path(tmp) / "q")

    def imp(self, props, **kw):
        return import_proposals(props, CTX, self.estore, self.queue, **kw)


class ReviewIdTest(unittest.TestCase):
    def test_stable_and_excludes_mutable(self):
        a = review_id_for("ユキ", DOC, None, "小雪")
        self.assertEqual(a, review_id_for("ユキ", DOC, None, "小雪"))
        self.assertNotEqual(a, review_id_for("マホ", DOC, None, "小雪"))


class QueueTest(unittest.TestCase):
    def test_put_update_and_identity_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = ReviewQueue(Path(tmp))
            r = {
                "schema_version": 1, "review_id": review_id_for("ユキ", DOC, None, None),
                "mention": "ユキ", "document_id": DOC, "confidence": 0.5,
                "reason": "unmatched_needs_target", "status": "pending", "created_at": "2026-06-22T00:00:00Z",
            }
            q.put(r)
            r2 = dict(r); r2["status"] = "approved"
            q.put(r2)  # update 语义,同 id 覆盖
            self.assertEqual(1, len(q.list_all()))
            self.assertEqual([], q.list_pending())
            bad = dict(r); bad["review_id"] = "review_" + "0" * 24
            with self.assertRaises(ValueError):
                q.put(bad)


class DecisionTreeTest(unittest.TestCase):
    def test_clean_high_confidence_match_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.estore.put(build_entity(CREATOR, "ユキ", "小雪", status="approved"))
            out = h.imp([_proposal("ユキ", target="小雪", confidence=0.95)])
            self.assertEqual([], out)  # 干净高置信命中 → 不排队
            self.assertEqual([], h.queue.list_pending())

    def test_low_confidence_match_enqueues(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.estore.put(build_entity(CREATOR, "ユキ", "小雪", status="approved"))
            out = h.imp([_proposal("ユキ", target="小雪", confidence=0.3)])
            self.assertEqual("low_confidence_match", out[0]["reason"])

    def test_target_conflict_enqueues(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.estore.put(build_entity(CREATOR, "ユキ", "小雪", status="locked"))
            out = h.imp([_proposal("ユキ", target="雪子", confidence=0.95)])
            self.assertEqual("target_conflict", out[0]["reason"])
            # locked 实体不被 import 改动
            self.assertEqual("小雪", h.estore.list_scope(CREATOR)[0]["target"])

    def test_unmatched_with_target_creates_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            out = h.imp([_proposal("マホ", target="真秀", confidence=0.9)])
            self.assertEqual("new_candidate", out[0]["reason"])
            ent = h.estore.list_scope(CREATOR)
            self.assertEqual(1, len(ent))
            self.assertEqual("candidate", ent[0]["status"])
            self.assertEqual("automatic", ent[0]["authority"])
            self.assertEqual(ent[0]["entity_id"], out[0]["candidate_entity_id"])

    def test_unmatched_without_target_needs_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            out = h.imp([_proposal("ナゾ", confidence=0.9)])
            self.assertEqual("unmatched_needs_target", out[0]["reason"])
            self.assertEqual([], h.estore.list_scope(CREATOR))  # 无译名 → 不建实体

    def test_reimport_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.imp([_proposal("マホ", target="真秀", confidence=0.9)])
            h.imp([_proposal("マホ", target="真秀", confidence=0.9)])
            self.assertEqual(1, len(h.queue.list_all()))  # 同 proposal → 同 review_id
            self.assertEqual(1, len(h.estore.list_scope(CREATOR)))

    def test_malformed_proposal_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            with self.assertRaises(ValueError):
                h.imp([{"document_id": DOC, "confidence": 0.9}])  # 缺 mention
            with self.assertRaises(ValueError):
                h.imp([_proposal("X", confidence=2.0)])  # confidence 越界


class ResolveTest(unittest.TestCase):
    def test_approve_promotes_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            out = h.imp([_proposal("マホ", target="真秀", confidence=0.9)])
            rid = out[0]["review_id"]
            resolve_review(rid, "approved", "houxinli", h.queue, h.estore, CTX)
            ent = h.estore.list_scope(CREATOR)[0]
            self.assertEqual("approved", ent["status"])
            self.assertEqual("approved", h.queue.get(rid)["status"])
            self.assertEqual("houxinli", h.queue.get(rid)["decided_by"])

    def test_approve_locked_sets_locked_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            out = h.imp([_proposal("マホ", target="真秀", confidence=0.9)])
            resolve_review(out[0]["review_id"], "approved", "houxinli", h.queue, h.estore, CTX, locked=True)
            ent = h.estore.list_scope(CREATOR)[0]
            self.assertEqual("locked", ent["status"])
            self.assertEqual("manual", ent["authority"])

    def test_dismiss_keeps_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            out = h.imp([_proposal("マホ", target="真秀", confidence=0.9)])
            resolve_review(out[0]["review_id"], "dismissed", "houxinli", h.queue, h.estore, CTX)
            ent = h.estore.list_scope(CREATOR)[0]
            self.assertEqual("candidate", ent["status"])  # 实体保留 candidate
            self.assertEqual("dismissed", h.queue.get(out[0]["review_id"])["status"])

    def test_approve_conflict_does_not_downgrade_locked(self):
        # Codex #90 F1:approve target_conflict/low_conf 命中的 locked 实体绝不被降级
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            h.estore.put(build_entity(CREATOR, "ユキ", "小雪", authority="manual", status="locked"))
            out = h.imp([_proposal("ユキ", target="雪子", confidence=0.95)])
            self.assertEqual("target_conflict", out[0]["reason"])
            resolve_review(out[0]["review_id"], "approved", "houxinli", h.queue, h.estore, CTX)
            ent = h.estore.list_scope(CREATOR)[0]
            self.assertEqual("locked", ent["status"])       # 未被降级
            self.assertEqual("manual", ent["authority"])
            self.assertEqual("小雪", ent["target"])          # 未被改写

    def test_reimport_after_resolution_is_idempotent(self):
        # Codex #90 F2:已裁决的 review 不被重导重开,实体不被降级
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            out = h.imp([_proposal("マホ", target="真秀", confidence=0.9)])
            resolve_review(out[0]["review_id"], "approved", "houxinli", h.queue, h.estore, CTX)
            h.imp([_proposal("マホ", target="真秀", confidence=0.9)])  # 重导
            r = h.queue.get(out[0]["review_id"])
            self.assertEqual("approved", r["status"])        # 未被重开
            self.assertEqual("houxinli", r["decided_by"])    # 决定保住
            self.assertEqual("approved", h.estore.list_scope(CREATOR)[0]["status"])  # 实体未降级

    def test_invalid_review_does_not_orphan_entity(self):
        # Codex #90 F3:review 不合法(context 非字符串)时不得遗留孤儿 candidate 实体
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            with self.assertRaises(ValueError):
                h.imp([_proposal("マホ", target="真秀", confidence=0.9, context=123)])
            self.assertEqual([], h.estore.list_scope(CREATOR))  # 无孤儿实体


if __name__ == "__main__":
    unittest.main()
