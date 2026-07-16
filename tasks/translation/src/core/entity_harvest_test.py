#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""翻译后 LLM 专名收割的解析、篇内归一与 review 接线测试。"""

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


class EntityHarvestTest(unittest.TestCase):
    def _revision_and_translations(self):
        segments = [
            _segment(0, "カルアが笑った。"),
            _segment(1, "カルアの胸。"),
            _segment(2, "普通の一文。"),
        ]
        revision = {"document_id": DOC, "segments": segments}
        translations = {seg["segment_id"]: text for seg, text in zip(
            segments,
            ("卡尔亚笑了。", "卡露亚的胸。", "普通的一句。"),
        )}
        return revision, translations

    def test_parse_llm_entities_tolerates_noise_and_defaults(self):
        response = '好的:\n```json\n[{"source":"カルア","target":"卡尔亚","type":"person"},{"bad":1}]\n```'
        self.assertEqual(
            [{"source": "カルア", "target": "卡尔亚", "type": "person", "confidence": 0.5, "variants": []}],
            eh.parse_llm_entities(response),
        )

    def test_parse_drops_conflicting_targets_for_same_source(self):
        response = (
            '[{"source":"カルア","target":"卡尔亚","confidence":0.9},'
            '{"source":"カルア","target":"卡露拉","confidence":0.8}]'
        )
        self.assertEqual([], eh.parse_llm_entities(response))

    def test_parse_empty(self):
        self.assertEqual([], eh.parse_llm_entities("没有专名 []"))
        self.assertEqual([], eh.parse_llm_entities("乱七八糟没有数组"))

    def test_extract_via_llm_uses_bilingual_pairs(self):
        revision, translations = self._revision_and_translations()
        captured = {}

        def call_fn(messages):
            captured["messages"] = messages
            return '[{"source":"カルア","target":"卡尔亚","type":"person"}]'

        entities = eh.extract_entities_via_llm(revision, translations, call_fn)
        self.assertEqual("卡尔亚", entities[0]["target"])
        self.assertIn("カルア", captured["messages"][1]["content"])
        self.assertIn("卡露亚", captured["messages"][1]["content"])

    def test_extract_swallows_call_error(self):
        revision, translations = self._revision_and_translations()

        def fail(_messages):
            raise RuntimeError("api down")

        self.assertEqual([], eh.extract_entities_via_llm(revision, translations, fail))

    def test_context_target_overrides_conflicting_llm_target(self):
        entities = [{
            "source": "カルア",
            "target": "卡尔亚",
            "type": "person",
            "confidence": 0.9,
            "variants": ["卡露亚"],
        }]
        normalized = eh.enforce_context_targets(
            entities,
            [{"source": "カルア", "target": "卡露拉"}],
        )
        self.assertEqual("卡露拉", normalized[0]["target"])
        self.assertEqual(["卡尔亚", "卡露亚"], normalized[0]["variants"])
        self.assertEqual("卡尔亚", entities[0]["target"])

    def test_apply_entity_variants_only_changes_matching_source_segments(self):
        revision, translations = self._revision_and_translations()
        entities = [{
            "source": "カルア",
            "target": "卡尔亚",
            "type": "person",
            "confidence": 0.9,
            "variants": ["卡露亚"],
        }]
        self.assertEqual(1, eh.apply_entity_variants(revision["segments"], translations, entities))
        self.assertEqual("卡尔亚的胸。", translations[revision["segments"][1]["segment_id"]])
        self.assertEqual("普通的一句。", translations[revision["segments"][2]["segment_id"]])

    def test_enqueue_creates_pending_candidate_not_active_constraint(self):
        revision, _ = self._revision_and_translations()
        entities = [{
            "source": "カルア",
            "target": "卡尔亚",
            "type": "person",
            "confidence": 0.9,
            "variants": ["卡露亚"],
        }]
        with tempfile.TemporaryDirectory() as temp:
            entity_root = Path(temp) / "entities"
            queue_root = Path(temp) / "reviews"
            reviews = eh.enqueue_entity_reviews(revision, entities, entity_root, queue_root)
            self.assertEqual("new_candidate", reviews[0]["reason"])
            self.assertEqual("pending", ReviewQueue(queue_root).list_all()[0]["status"])
            candidate = EntityStore(entity_root).list_scope(SCOPE)[0]
            self.assertEqual(("candidate", "automatic", "person"), (
                candidate["status"], candidate["authority"], candidate["type"]
            ))
            self.assertEqual([], resolve_entities(SCOPE_CONTEXT, "カルア", EntityStore(entity_root)))

    def test_enqueue_does_not_overwrite_existing_approved_entity(self):
        revision, _ = self._revision_and_translations()
        entities = [{
            "source": "カルア",
            "target": "卡尔亚",
            "type": "person",
            "confidence": 0.9,
            "variants": [],
        }]
        with tempfile.TemporaryDirectory() as temp:
            entity_root = Path(temp) / "entities"
            store = EntityStore(entity_root)
            store.put(build_entity(SCOPE, "カルア", "卡露拉", status="approved"))
            reviews = eh.enqueue_entity_reviews(revision, entities, entity_root, Path(temp) / "reviews")
            self.assertEqual("target_conflict", reviews[0]["reason"])
            self.assertEqual("卡露拉", store.list_scope(SCOPE)[0]["target"])

    def test_enqueue_ignores_hallucinated_source_not_in_revision(self):
        revision, _ = self._revision_and_translations()
        entities = [{
            "source": "不存在",
            "target": "幻觉",
            "type": "person",
            "confidence": 0.9,
            "variants": [],
        }]
        with tempfile.TemporaryDirectory() as temp:
            reviews = eh.enqueue_entity_reviews(
                revision, entities, Path(temp) / "entities", Path(temp) / "reviews"
            )
            self.assertEqual([], reviews)


if __name__ == "__main__":
    unittest.main()
