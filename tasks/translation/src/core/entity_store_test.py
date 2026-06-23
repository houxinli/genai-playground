#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scoped 实体库 + resolver(#83 P1b):身份/update 语义/fail-fast/scope 解析优先级/相关过滤。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from .entity_store import (
        EntityStore,
        _parse_rules_text,
        build_entity,
        entity_id_for,
        resolve_entities,
    )
except ImportError:  # core/ 在 sys.path 上
    from entity_store import (
        EntityStore,
        _parse_rules_text,
        build_entity,
        entity_id_for,
        resolve_entities,
    )


def _entity(level, key, source, target, *, authority="manual", status="approved",
            aliases=None, forbidden=None):
    scope = {"level": level, "key": key}
    e = {
        "schema_version": 1,
        "entity_id": entity_id_for(scope, source),
        "scope": scope,
        "source": source,
        "target": target,
        "type": "person",
        "authority": authority,
        "status": status,
        "updated_at": "2026-06-22T00:00:00Z",
    }
    if aliases:
        e["aliases"] = aliases
    if forbidden:
        e["forbidden"] = forbidden
    return e


PIXIV_CTX = {"provider": "pixiv", "creator_id": "50235390", "series": "S1", "document_id": "pixiv:50235390:12430834"}


class EntityIdTest(unittest.TestCase):
    def test_id_stable_over_scope_and_source(self):
        sc = {"level": "creator", "key": "pixiv:50235390"}
        self.assertEqual(entity_id_for(sc, "ユキ"), entity_id_for(sc, "ユキ"))
        self.assertNotEqual(entity_id_for(sc, "ユキ"), entity_id_for(sc, "マホ"))
        self.assertNotEqual(entity_id_for(sc, "ユキ"), entity_id_for({"level": "global", "key": None}, "ユキ"))

    def test_id_unchanged_by_target(self):
        # 改 target 不改 id(可更新语义的前提)
        sc = {"level": "global", "key": None}
        self.assertEqual(entity_id_for(sc, "ユキ"), entity_id_for(sc, "ユキ"))


class EntityStoreTest(unittest.TestCase):
    def test_put_and_update_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EntityStore(Path(tmp))
            store.put(_entity("creator", "pixiv:50235390", "ユキ", "小雪"))
            store.put(_entity("creator", "pixiv:50235390", "ユキ", "由纪"))  # 同 entity_id 覆盖
            recs = store.list_scope({"level": "creator", "key": "pixiv:50235390"})
            self.assertEqual(1, len(recs))
            self.assertEqual("由纪", recs[0]["target"])

    def test_put_rejects_tampered_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EntityStore(Path(tmp))
            e = _entity("global", None, "ユキ", "小雪")
            e["entity_id"] = "entity_" + "0" * 24
            with self.assertRaises(ValueError):
                store.put(e)

    def test_put_rejects_missing_field_and_bad_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EntityStore(Path(tmp))
            e = _entity("creator", "pixiv:50235390", "ユキ", "小雪")
            del e["target"]
            with self.assertRaises(ValueError):
                store.put(e)
            bad = _entity("global", "pixiv", "ユキ", "小雪")  # global 不应带 key
            bad["entity_id"] = entity_id_for(bad["scope"], bad["source"])
            with self.assertRaises(ValueError):
                store.put(bad)

    def test_distinct_keys_do_not_collide(self):
        # pixiv:a_b:c 与 pixiv:a:b_c 朴素消毒会撞同名 → 必须映射到不同分片且互不串读
        with tempfile.TemporaryDirectory() as tmp:
            store = EntityStore(Path(tmp))
            s1 = {"level": "document", "key": "pixiv:a_b:c"}
            s2 = {"level": "document", "key": "pixiv:a:b_c"}
            self.assertNotEqual(store.shard_path(s1), store.shard_path(s2))
            store.put(build_entity(s1, "ユキ", "甲"))
            store.put(build_entity(s2, "ユキ", "乙"))
            self.assertEqual("甲", store.list_scope(s1)[0]["target"])
            self.assertEqual("乙", store.list_scope(s2)[0]["target"])

    def test_shard_path_is_scope_safe(self):
        store = EntityStore(Path("/tmp/ent"))
        self.assertEqual(Path("/tmp/ent/global/_global.jsonl"),
                         store.shard_path({"level": "global", "key": None}))
        # 含 ':' 的 key 不直接当文件名
        p = store.shard_path({"level": "creator", "key": "pixiv:50235390"})
        self.assertNotIn(":", p.name)


class ResolveTest(unittest.TestCase):
    def _store(self, *entities):
        tmp = tempfile.mkdtemp()
        store = EntityStore(Path(tmp))
        for e in entities:
            store.put(e)
        return store

    def test_only_entities_present_in_text_are_injected(self):
        store = self._store(
            _entity("creator", "pixiv:50235390", "ユキ", "小雪"),
            _entity("creator", "pixiv:50235390", "マホ", "真秀"),
        )
        out = resolve_entities(PIXIV_CTX, "今日はユキと出かけた。", store)
        self.assertEqual(["ユキ"], [c["source"] for c in out])  # マホ 未出现 → 不注入

    def test_alias_presence_triggers_injection_and_constraint_shape(self):
        store = self._store(_entity("creator", "pixiv:50235390", "ユキ", "小雪",
                                     aliases=["ゆきちゃん"], forbidden=["雪"]))
        out = resolve_entities(PIXIV_CTX, "ゆきちゃん、おはよう", store)
        self.assertEqual(1, len(out))
        c = out[0]
        self.assertEqual("小雪", c["target"])
        self.assertEqual(["ゆきちゃん"], c["aliases"])
        self.assertEqual(["雪"], c["forbidden"])

    def test_more_specific_scope_wins(self):
        store = self._store(
            _entity("creator", "pixiv:50235390", "ユキ", "小雪"),
            _entity("document", "pixiv:50235390:12430834", "ユキ", "雪子"),  # 更具体
        )
        out = resolve_entities(PIXIV_CTX, "ユキ", store)
        self.assertEqual("雪子", out[0]["target"])

    def test_locked_not_overridden_by_lower_authority_more_specific(self):
        store = self._store(
            _entity("creator", "pixiv:50235390", "ユキ", "小雪", authority="manual", status="locked"),
            _entity("document", "pixiv:50235390:12430834", "ユキ", "雪子",
                    authority="automatic", status="candidate"),  # 更具体但低权
        )
        out = resolve_entities(PIXIV_CTX, "ユキ", store)
        self.assertEqual("小雪", out[0]["target"])  # locked 不被低权覆盖

    def test_manual_override_beats_less_specific_locked(self):
        store = self._store(
            _entity("global", None, "ユキ", "雪", authority="manual", status="locked"),
            _entity("document", "pixiv:50235390:12430834", "ユキ", "小雪",
                    authority="manual", status="approved"),  # 更具体 + 显式人工
        )
        out = resolve_entities(PIXIV_CTX, "ユキ", store)
        self.assertEqual("小雪", out[0]["target"])  # 显式人工 override 更具体 → 覆盖全局 locked

    def test_unrelated_scope_not_pulled(self):
        # 别的 creator 的同名实体不应被本文档解析到
        store = self._store(_entity("creator", "pixiv:99999999", "ユキ", "雪子"))
        out = resolve_entities(PIXIV_CTX, "ユキ", store)
        self.assertEqual([], out)

    def test_series_scope_resolved_only_when_series_in_ctx(self):
        # 系列作用域规则只在 scope_ctx 带 series 时可达(否则像 CLI 漏传 series 一样静默失效)
        store = self._store(_entity("series", "pixiv:50235390:S1", "ユキ", "小雪"))
        self.assertEqual("小雪", resolve_entities(PIXIV_CTX, "ユキ", store)[0]["target"])
        no_series = {k: v for k, v in PIXIV_CTX.items() if k != "series"}
        self.assertEqual([], resolve_entities(no_series, "ユキ", store))


class SeedTest(unittest.TestCase):
    def test_parse_rules_text(self):
        rules = _parse_rules_text("# 注释\nユキ=小雪|雪,雪子\n\nマホ=真秀\n")
        self.assertEqual(
            [{"source": "ユキ", "target": "小雪", "forbidden": ["雪", "雪子"]},
             {"source": "マホ", "target": "真秀"}],
            rules,
        )

    def test_parse_rules_text_rejects_malformed(self):
        with self.assertRaises(ValueError):
            _parse_rules_text("没有等号的行")
        with self.assertRaises(ValueError):
            _parse_rules_text("ユキ=")  # target 空

    def test_build_entity_and_put_round_trips(self):
        scope = {"level": "creator", "key": "pixiv:50235390"}
        with tempfile.TemporaryDirectory() as tmp:
            store = EntityStore(Path(tmp))
            e = build_entity(scope, "ユキ", "小雪", forbidden=["雪"], status="locked")
            store.put(e)
            recs = store.list_scope(scope)
            self.assertEqual(1, len(recs))
            self.assertEqual("manual", recs[0]["authority"])
            self.assertEqual("locked", recs[0]["status"])
            self.assertEqual(["雪"], recs[0]["forbidden"])


if __name__ == "__main__":
    unittest.main()
