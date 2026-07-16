#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""篇内实体 first-wins 记忆、Agent names.tsv 与 review 接线测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import entity_harvest as eh
    from .entity_review import ReviewQueue
    from .entity_store import EntityStore, build_entity, resolve_entities
except ImportError:
    import entity_harvest as eh
    from entity_review import ReviewQueue
    from entity_store import EntityStore, build_entity, resolve_entities


DOC = "pixiv:700000:700001"
SCOPE = {"level": "creator", "key": "pixiv:700000"}
SCOPE_CONTEXT = {"provider": "pixiv", "creator_id": "700000", "document_id": DOC}


def _segment(index, source):
    return {
        "segment_id": f"rev_aaaaaaaa:{index:06d}:bbbbbbbb",
        "kind": "body",
        "source_text": source,
    }


def _revision():
    return {
        "document_id": DOC,
        "segments": [
            _segment(0, "カルアが笑った。"),
            _segment(1, "カルアの胸。"),
            _segment(2, "普通の一文。"),
        ],
    }


class EntityMemoryTest(unittest.TestCase):
    def test_parse_simple_te_protocol(self):
        translation, entities = eh.parse_executor_response(
            "T\t卡尔亚笑了。\nE\tカルア\t卡尔亚\nE\t王都\t王都"
        )
        self.assertEqual("卡尔亚笑了。", translation)
        self.assertEqual(
            [{"source": "カルア", "target": "卡尔亚"}, {"source": "王都", "target": "王都"}],
            entities,
        )

    def test_plain_single_line_response_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "首行"):
            eh.parse_executor_response("普通译文。")

    def test_multiline_response_requires_te_protocol(self):
        with self.assertRaisesRegex(ValueError, "首行"):
            eh.parse_executor_response("译文\n额外解释")
        with self.assertRaisesRegex(ValueError, "第 2 行"):
            eh.parse_executor_response("T\t译文\n多余说明")

    def test_first_use_locks_and_later_variant_only_rewrites_current_text(self):
        locked = {}
        text, first, conflicts = eh.apply_observations(
            "カルアが笑った。", "卡尔亚笑了。", [{"source": "カルア", "target": "卡尔亚"}], locked
        )
        self.assertEqual("卡尔亚笑了。", text)
        self.assertEqual({"カルア": "卡尔亚"}, locked)
        self.assertEqual([{"source": "カルア", "target": "卡尔亚"}], first)
        self.assertEqual([], conflicts)

        text, first, conflicts = eh.apply_observations(
            "カルアの胸。", "卡露亚的胸。", [{"source": "カルア", "target": "卡露亚"}], locked
        )
        self.assertEqual("卡尔亚的胸。", text)
        self.assertEqual({"カルア": "卡尔亚"}, locked)
        self.assertEqual([], first)
        self.assertEqual("卡露亚", conflicts[0]["observed_target"])

    def test_context_target_wins_before_first_observation(self):
        locked = eh.context_targets({"entities": [{"source": "カルア", "target": "卡尔亚"}]})
        text, first, _ = eh.apply_observations(
            "カルアが来た。", "卡露亚来了。", [{"source": "カルア", "target": "卡露亚"}], locked
        )
        self.assertEqual("卡尔亚来了。", text)
        self.assertEqual([], first)

    def test_hallucinated_or_unused_observation_is_ignored(self):
        locked = {}
        text, first, conflicts = eh.apply_observations(
            "普通の一文。", "普通的一句。", [{"source": "カルア", "target": "卡尔亚"}], locked
        )
        self.assertEqual("普通的一句。", text)
        self.assertEqual(([], [], {}), (first, conflicts, locked))

    def test_finding_round_trip(self):
        finding = eh.entity_finding("カルア", "卡尔亚", _segment(0, "x")["segment_id"], 1)
        entities = eh.entities_from_result({"findings": [finding]})
        self.assertEqual(("カルア", "卡尔亚", 1.0), (
            entities[0]["source"], entities[0]["target"], entities[0]["confidence"]
        ))

    def test_names_tsv_rejects_non_first_translation(self):
        self.assertEqual({"カルア": "卡尔亚"}, eh.parse_locked_names_tsv("カルア\t卡尔亚\n"))
        with self.assertRaisesRegex(ValueError, "first-wins"):
            eh.parse_locked_names_tsv("カルア\t卡尔亚\nカルア\t卡露亚\n")

    def test_agent_names_require_actual_use_and_do_not_repropose_context(self):
        revision = _revision()
        bundle = {
            "segments": revision["segments"],
            "context_pack": {"entities": [{"source": "カルア", "target": "卡尔亚"}]},
        }
        translations = {0: "卡露亚笑了。", 1: "卡露亚的胸。", 2: "普通的一句。"}
        normalized, findings = eh.apply_locked_names(bundle, translations, {"カルア": "卡露亚"})
        self.assertEqual("卡尔亚笑了。", normalized[0])
        self.assertEqual("卡尔亚的胸。", normalized[1])
        self.assertEqual([], findings)

        bundle["context_pack"] = {"entities": []}
        normalized, findings = eh.apply_locked_names(bundle, translations, {"カルア": "卡露亚"})
        self.assertEqual("卡露亚笑了。", normalized[0])
        self.assertEqual("卡露亚", eh.entities_from_result({"findings": findings})[0]["target"])
        with self.assertRaisesRegex(ValueError, "target"):
            eh.apply_locked_names(bundle, translations, {"カルア": "不存在的译名"})


class EntityReviewTest(unittest.TestCase):
    def _entity(self, source="カルア", target="卡尔亚"):
        return {"source": source, "target": target, "type": "person", "confidence": 1.0, "variants": []}

    def test_enqueue_creates_pending_candidate_not_active_constraint(self):
        with tempfile.TemporaryDirectory() as temp:
            entity_root = Path(temp) / "entities"
            queue_root = Path(temp) / "reviews"
            reviews = eh.enqueue_entity_reviews(_revision(), [self._entity()], entity_root, queue_root)
            self.assertEqual("new_candidate", reviews[0]["reason"])
            self.assertEqual("pending", ReviewQueue(queue_root).list_all()[0]["status"])
            candidate = EntityStore(entity_root).list_scope(SCOPE)[0]
            self.assertEqual(("candidate", "automatic", "person"), (
                candidate["status"], candidate["authority"], candidate["type"]
            ))
            self.assertEqual([], resolve_entities(SCOPE_CONTEXT, "カルア", EntityStore(entity_root)))

    def test_enqueue_does_not_overwrite_existing_approved_entity(self):
        with tempfile.TemporaryDirectory() as temp:
            entity_root = Path(temp) / "entities"
            store = EntityStore(entity_root)
            store.put(build_entity(SCOPE, "カルア", "卡露拉", status="approved"))
            reviews = eh.enqueue_entity_reviews(
                _revision(), [self._entity()], entity_root, Path(temp) / "reviews"
            )
            self.assertEqual("target_conflict", reviews[0]["reason"])
            self.assertEqual("卡露拉", store.list_scope(SCOPE)[0]["target"])

    def test_enqueue_ignores_hallucinated_source_not_in_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            reviews = eh.enqueue_entity_reviews(
                _revision(),
                [self._entity("不存在", "幻觉")],
                Path(temp) / "entities",
                Path(temp) / "reviews",
            )
            self.assertEqual([], reviews)


if __name__ == "__main__":
    unittest.main()
