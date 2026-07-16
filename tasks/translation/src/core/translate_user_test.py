#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translate-user 通用编排:mock executor 跑 fixture 全链(翻译→发布→渲染→合并),不调网络。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import translate_user as tu
    from .artifact_store import ArtifactStore
except ImportError:  # core/ 在 sys.path 上
    import translate_user as tu
    from artifact_store import ArtifactStore


TESTDATA = Path(__file__).resolve().parent / "testdata"
SRC = TESTDATA / "fixtures" / "pixiv" / "700001" / "700001.txt"
BILINGUAL = TESTDATA / "golden" / "pixiv-700001.render.bilingual.txt"  # 现有译文作 incumbent
TR = {
    "朝の挨拶": "早晨的问候", "テスト用の短い文章です。": "用于测试的简短文章。",
    "[テスト, 日常]": "[テスト / 测试, 日常 / 日常]", "「おはよう」": "「早上好」",
    "今日はいい天気だ。": "今天天气真好。",
}


def _mk(tr):
    """按译表 tr 造 mock executor;走真实 translate_bundle 组装路径(逐段一 call)。"""
    def executor(bundle):
        def call(messages):
            line = [l for l in messages[1]["content"].splitlines() if l.startswith("[翻译这一段]")][0]
            return tr[line.split("] ", 1)[1]]
        try:
            from .openrouter_executor import translate_bundle
        except ImportError:
            from openrouter_executor import translate_bundle
        return translate_bundle(bundle, call, model="mock", completed_at="2026-06-13T00:00:00Z")
    return executor


_mock_executor = _mk(TR)


class TranslateUserTest(unittest.TestCase):
    def test_one_command_translates_publishes_renders_merges(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir()
            shutil.copy(BILINGUAL, bil_dir / "700001.txt")  # 现有译文作 incumbent(元数据段可解析)
            store_root = tmp / "store"; render_dir = tmp / "out"
            m = tu.translate_user("pixiv", src_dir, store_root, render_dir, _mock_executor, bilingual_dir=bil_dir)
            self.assertEqual(1, m["summary"]["published"])
            self.assertEqual(0, m["summary"]["errors"])
            doc = m["documents"][0]["document_id"]
            store = ArtifactStore(store_root)
            # 翻译后:store 有新候选 + 版本 + 发布 ref;渲染产物 + 合并整本
            self.assertTrue(store.list_shard("candidate", doc))
            self.assertIsNotNone(store.current_ref(doc))
            zh = (render_dir / "700001.zh.txt").read_text(encoding="utf-8")
            self.assertIn("早上好", zh)            # 译文进了渲染
            book = (render_dir / f"{src_dir.name}_zh.txt").read_text(encoding="utf-8")
            self.assertIn("第1章", book)            # 合并整本
            self.assertIn("早上好", book)

    def test_limit_bounds_documents(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "auth"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            shutil.copy(SRC, src_dir / "700002.txt")  # 第二篇(同源,document_id 同 → 仅测 limit 计数)
            m = tu.translate_user("pixiv", src_dir, tmp / "s", None, _mock_executor, limit=1)
            self.assertEqual(1, m["summary"]["total"])

    def test_fresh_author_publishes_with_tags_fallback(self):
        # 无 legacy:title/caption/body 译文过 QA;tags「原词/中文」含假名 QA fail → 仅 tags 兜底 → 发布
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "auth"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            m = tu.translate_user("pixiv", src_dir, tmp / "s", tmp / "out", _mock_executor)
            self.assertEqual(1, m["summary"]["published"])

    def test_failing_title_publishes_reviewable_render(self):
        # QA fail 不阻断 render:无 incumbent 且只有本轮唯一候选时先发布可 review 版本,后续 patch 覆盖。
        bad = {**TR, "朝の挨拶": "朝の挨拶"}  # 标题原样照抄 = QA fail
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "auth"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            m = tu.translate_user("pixiv", src_dir, tmp / "s", tmp / "out", _mk(bad))
            self.assertEqual(1, m["summary"]["published"])
            self.assertEqual("ok", m["documents"][0]["status"])
            self.assertEqual(1, m["documents"][0]["review_required"])
            self.assertTrue(m["documents"][0]["rendered"])

    def test_uses_this_run_candidate_not_stale_shard(self):
        # Codex #107:store 已有上一轮非 legacy 候选时,本轮发布/渲染必须用本轮 executor 产物
        old = {**TR, "「おはよう」": "旧甲", "今日はいい天気だ。": "旧乙"}
        new = {**TR, "「おはよう」": "新甲", "今日はいい天気だ。": "新乙"}
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "auth"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            store_root = tmp / "s"; render_dir = tmp / "out"
            tu.translate_user("pixiv", src_dir, store_root, render_dir, _mk(old))   # 第一轮:旧译入库
            tu.translate_user("pixiv", src_dir, store_root, render_dir, _mk(new))   # 第二轮:新译
            zh = (render_dir / "700001.zh.txt").read_text(encoding="utf-8")
            self.assertIn("新甲", zh)
            self.assertNotIn("旧甲", zh)   # 不能渲染上一轮的陈旧候选

    def test_prepare_then_agent_translate_then_finish(self):
        # agent 路线:prepare 导出 bundle → (执行器翻译写 result) → finish 发布渲染合并
        import json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir()
            shutil.copy(BILINGUAL, bil_dir / "700001.txt")
            store_root = tmp / "store"; jobs_dir = tmp / "jobs"; results_dir = tmp / "results"
            render_dir = tmp / "out"; results_dir.mkdir()

            prep = tu.prepare_user("pixiv", src_dir, store_root, jobs_dir, bilingual_dir=bil_dir)
            self.assertEqual(1, len(prep["jobs"]))
            # 模拟执行器:读 job(=bundle)→ 翻译 → 写 result
            for j in prep["jobs"]:
                bundle = json.loads(Path(j["job"]).read_text(encoding="utf-8"))
                result = _mock_executor(bundle)
                (results_dir / f"{j['source_id']}.result.json").write_text(
                    json.dumps(result, ensure_ascii=False), encoding="utf-8")

            m = tu.finish_user("pixiv", src_dir, store_root, render_dir, results_dir, bilingual_dir=bil_dir)
            self.assertEqual(1, m["summary"]["published"])
            book = (render_dir / f"{src_dir.name}_zh.txt").read_text(encoding="utf-8")
            self.assertIn("早上好", book)

    def test_verify_true_after_finish_false_on_prepare_only(self):
        # #129:verify 独立核对落盘——finish 后 ok;只 prepare(Cursor 那种)→ ok=False(没 import/发布/渲染)
        import json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir(); shutil.copy(BILINGUAL, bil_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()

            prep = tu.prepare_user("pixiv", src_dir, store, jobs, bilingual_dir=bil_dir)
            # 只 prepare:还没翻、没 finish → verify 必须 False(这正是 Cursor 谎报的状态)
            v0 = tu.verify_user("pixiv", src_dir, store, render, results)
            self.assertFalse(v0["ok"])
            self.assertFalse(v0["documents"][0]["published"])  # 没 finish → 没发布
            self.assertFalse(v0["documents"][0]["rendered"])   # 没渲染产物
            self.assertFalse(v0["documents"][0]["result_json"])  # 没写 result(Cursor 谎报的核心)

            # 真翻 + finish 后 → verify True
            for j in prep["jobs"]:
                bundle = json.loads(Path(j["job"]).read_text(encoding="utf-8"))
                (results / f"{j['source_id']}.result.json").write_text(
                    json.dumps(_mock_executor(bundle), ensure_ascii=False), encoding="utf-8")
            tu.finish_user("pixiv", src_dir, store, render, results, bilingual_dir=bil_dir)
            v1 = tu.verify_user("pixiv", src_dir, store, render, results)
            self.assertTrue(v1["ok"], v1["documents"])
            self.assertTrue(v1["documents"][0]["published"])
            self.assertTrue(v1["documents"][0]["version_matches_source"])
            self.assertTrue(v1["documents"][0]["rendered"])

            # Codex #130:源改了(新 revision)但旧 ref 仍在 → verify 不能算通过
            (src_dir / "700001.txt").write_text(
                (src_dir / "700001.txt").read_text(encoding="utf-8") + "\n新增一段正文。\n", encoding="utf-8")
            v2 = tu.verify_user("pixiv", src_dir, store, render, results)
            self.assertFalse(v2["ok"])
            self.assertFalse(v2["documents"][0]["version_matches_source"])  # 旧版本不对应新源

    def test_finish_auto_assembles_from_tsv(self):
        # 紧凑路径:只写 <id>.zh.tsv(无 result.json)→ finish 自动组装并发布(少一个 assemble 步骤)
        import json as _json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir(); shutil.copy(BILINGUAL, bil_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()
            prep = tu.prepare_user("pixiv", src_dir, store, jobs, bilingual_dir=bil_dir)
            j = prep["jobs"][0]; sid = j["source_id"]
            bundle = _json.loads(Path(j["job"]).read_text(encoding="utf-8"))
            lines = [f"{i}\t{TR[seg['source_text']]}" for i, seg in enumerate(bundle["segments"])]
            (results / f"{sid}.zh.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")  # 只写 tsv

            m = tu.finish_user(
                "pixiv",
                src_dir,
                store,
                render,
                results,
                jobs_dir=jobs,
                bilingual_dir=bil_dir,
                producer_name="cursor-grok",
                model="grok-test",
            )
            self.assertEqual(1, m["summary"]["published"])
            self.assertTrue((results / f"{sid}.result.json").is_file())  # finish 自动从原始 job 组装出 result.json
            result = _json.loads((results / f"{sid}.result.json").read_text(encoding="utf-8"))
            self.assertEqual({"type": "harness", "name": "cursor-grok", "model": "grok-test"}, result["producer"])
            self.assertEqual({"cursor-grok"}, {c["result_candidate_key"] for c in result["candidates"]})

    def test_entity_store_wired_into_auto_mode(self):
        # Codex #151 review:自动路线(translate_user/translate_document)也须透传实体库,
        # 否则 make translate-user MODE=auto ENTITY_STORE=... 静默丢约束。
        try:
            from .entity_store import EntityStore, entity_id_for
        except ImportError:
            from entity_store import EntityStore, entity_id_for
        seen = {}
        def spy(bundle):
            seen["entities"] = bundle["context_pack"]["entities"]
            return _mock_executor(bundle)
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            es_root = tmp / "entities"
            scope = {"level": "creator", "key": "pixiv:700000"}
            EntityStore(es_root).put({"schema_version": 1, "entity_id": entity_id_for(scope, "おはよう"),
                "scope": scope, "source": "おはよう", "target": "早上好", "type": "person",
                "authority": "manual", "status": "approved", "updated_at": "2026-07-13T00:00:00Z"})
            tu.translate_user("pixiv", src_dir, tmp / "s", tmp / "out", spy, entity_store=es_root)
            self.assertEqual(["おはよう"], [e["source"] for e in seen["entities"]])

    def test_auto_mode_normalizes_harvested_variant_and_enqueues_review(self):
        try:
            from .entity_review import ReviewQueue
            from .entity_store import EntityStore, resolve_entities
        except ImportError:
            from entity_review import ReviewQueue
            from entity_store import EntityStore, resolve_entities

        translated = {**TR, "「おはよう」": "「早安」"}

        def extract(_messages):
            return (
                '[{"source":"おはよう","target":"早上好","type":"person",'
                '"confidence":0.9,"variants":["早安"]}]'
            )

        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"
            src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            entity_root = tmp / "entities"
            queue_root = tmp / "entity-reviews"
            manifest = tu.translate_user(
                "pixiv",
                src_dir,
                tmp / "store",
                tmp / "out",
                _mk(translated),
                entity_store=entity_root,
                entity_review_queue=queue_root,
                extract_fn=extract,
            )
            document = manifest["documents"][0]
            self.assertTrue(document["published"], document)
            self.assertEqual(1, document["entity_harvest_normalized_segments"])
            self.assertEqual(1, document["entity_reviews_enqueued"])
            rendered = (tmp / "out" / "700001.zh.txt").read_text(encoding="utf-8")
            self.assertIn("早上好", rendered)
            self.assertNotIn("早安", rendered)
            self.assertEqual(1, len(ReviewQueue(queue_root).list_pending()))
            store = EntityStore(entity_root)
            candidate = store.list_scope({"level": "creator", "key": "pixiv:700000"})[0]
            self.assertEqual("candidate", candidate["status"])
            scope_context = {
                "provider": "pixiv",
                "creator_id": "700000",
                "document_id": "pixiv:700000:700001",
            }
            self.assertEqual([], resolve_entities(scope_context, "おはよう", store))

    def test_entity_store_wired_into_prepare_and_finish(self):
        # gh-149/#83:实体库 → prepare 的 context_pack.entities;finish 必须同库(约束入 task 身份),
        # 中途改库 → digest 不符 → import 按 stale 隔离(协议行为)。
        import json as _json
        try:
            from .entity_store import EntityStore, entity_id_for
        except ImportError:
            from entity_store import EntityStore, entity_id_for
        def _ent(source, target):
            scope = {"level": "creator", "key": "pixiv:700000"}
            return {"schema_version": 1, "entity_id": entity_id_for(scope, source), "scope": scope,
                    "source": source, "target": target, "type": "person",
                    "authority": "manual", "status": "approved",
                    "updated_at": "2026-07-11T00:00:00Z"}
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()
            es_root = tmp / "entities"
            es = EntityStore(es_root)
            es.put(_ent("おはよう", "早上好"))   # 源文出现 → 注入
            es.put(_ent("マホ", "真穗"))          # 源文未出现 → 不注入
            prep = tu.prepare_user("pixiv", src_dir, store, jobs, entity_store=es_root)
            j = prep["jobs"][0]; sid = j["source_id"]
            bundle = _json.loads(Path(j["job"]).read_text(encoding="utf-8"))
            ents = bundle["context_pack"]["entities"]
            self.assertEqual(["おはよう"], [e["source"] for e in ents])
            self.assertEqual("早上好", ents[0]["target"])
            # 翻译 + finish(同库)→ 正常发布
            tsv = results / f"{sid}.zh.tsv"
            tsv.write_text("\n".join(
                f"{i}\t{TR[seg['source_text']]}" for i, seg in enumerate(bundle["segments"])) + "\n",
                encoding="utf-8")
            m = tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs,
                               entity_store=es_root, producer_name="cursor-grok")
            self.assertTrue(m["documents"][0]["published"], m["documents"][0])
            # finish 不带库(或库已变)→ task 身份不一致 → stale 隔离,不污染发布
            m2 = tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs,
                                producer_name="cursor-grok")
            self.assertEqual("translate_quarantined", m2["documents"][0]["status"])

    def test_blank_tsv_rows_block_version_not_holey_publish(self):
        # gh-142 回归:填空 TSV 的空行曾被 reviewable 放宽路径选中 → 212 篇带洞发布。
        # 空译文候选必须不可选 → 整篇 unresolved 阻断,不产带洞版本。
        import json as _json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()
            prep = tu.prepare_user("pixiv", src_dir, store, jobs)
            j = prep["jobs"][0]; sid = j["source_id"]
            bundle = _json.loads(Path(j["job"]).read_text(encoding="utf-8"))
            rows = []
            for i, seg in enumerate(bundle["segments"]):
                t_ = "" if i == 3 else TR[seg["source_text"]]  # 一行留空
                rows.append(f"{i}\t{seg['source_text'][:8]}\t{t_}")
            (results / f"{sid}.zh.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
            m = tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs,
                               producer_name="cursor-grok")
            d = m["documents"][0]
            self.assertEqual("unresolved", d["status"])
            self.assertFalse(d.get("published"))
            self.assertIsNone(ArtifactStore(store).current_ref(d["document_id"]))  # 不产带洞发布

    def test_blank_tags_candidate_also_blocked(self):
        # Codex #153 review:空译文守卫必须先于 tags 兜底——否则空 tags 候选仍被无条件选中发布。
        import json as _json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()
            prep = tu.prepare_user("pixiv", src_dir, store, jobs)
            j = prep["jobs"][0]; sid = j["source_id"]
            bundle = _json.loads(Path(j["job"]).read_text(encoding="utf-8"))
            rows = []
            for i, seg in enumerate(bundle["segments"]):
                t_ = "" if seg["kind"] == "metadata.tags" else TR[seg["source_text"]]  # 只留空 tags 行
                rows.append(f"{i}\t{seg['source_text'][:8]}\t{t_}")
            (results / f"{sid}.zh.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
            m = tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs,
                               producer_name="cursor-grok")
            d = m["documents"][0]
            self.assertEqual("unresolved", d["status"])
            self.assertIsNone(ArtifactStore(store).current_ref(d["document_id"]))

    def test_finish_republishes_after_tsv_repair_with_lineage(self):
        # gh-142 修复潮踩坑:此前 finish 遇已有 ref 永不推进("ref_exists_kept"),
        # 修复只更新 rendered、store ref 长期指向旧坏版本。现在:TSV 改过 → 带 parent
        # 血缘重建 version 并 CAS 推进 ref;TSV 没改 → 幂等,published 且版本不变。
        import json as _json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()
            # 生产修复形态:无 bilingual incumbent(挑战者直接生效)
            prep = tu.prepare_user("pixiv", src_dir, store, jobs)
            j = prep["jobs"][0]; sid = j["source_id"]
            bundle = _json.loads(Path(j["job"]).read_text(encoding="utf-8"))
            tsv = results / f"{sid}.zh.tsv"
            tsv.write_text("\n".join(
                f"{i}\t{TR[seg['source_text']]}" for i, seg in enumerate(bundle["segments"])) + "\n",
                encoding="utf-8")
            m1 = tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs,
                                producer_name="cursor-grok")
            v1 = m1["documents"][0]["version_id"]
            self.assertTrue(m1["documents"][0]["published"])
            # 幂等重跑:版本不变、published、无 republished
            m2 = tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs,
                                producer_name="cursor-grok")
            self.assertEqual(v1, m2["documents"][0]["version_id"])
            self.assertTrue(m2["documents"][0]["published"])
            self.assertNotEqual("republished", m2["documents"][0].get("status"))
            # 修 TSV(重译一行)→ finish 必须推进 ref,且新版本带 parent 血缘
            lines = tsv.read_text(encoding="utf-8").splitlines()
            lines[3] = lines[3].split("\t")[0] + "\t「早安」"
            tsv.write_text("\n".join(lines) + "\n", encoding="utf-8")
            m3 = tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs,
                                producer_name="cursor-grok")
            d3 = m3["documents"][0]
            self.assertEqual("republished", d3["status"])
            self.assertEqual(v1, d3["previous_version_id"])
            st = ArtifactStore(store)
            doc = d3["document_id"]
            cur = st.current_ref(doc)
            self.assertEqual(d3["version_id"], cur["version_id"])  # ref 已推进
            ver = st.get("document-version", doc, cur["version_id"])
            self.assertEqual(v1, ver.get("parent_version_id"))  # 血缘
            self.assertIn("「早安」", (render / f"{sid}.zh.txt").read_text(encoding="utf-8"))  # 修复生效
            # verify 全绿(rendered 与 current ref 一致)
            v = tu.verify_user("pixiv", src_dir, store, render, results)
            self.assertTrue(v["ok"], v["documents"])
            self.assertTrue(v["documents"][0]["rendered_matches_ref"])
            # 人为把 ref 拨回旧版本(rendered 仍是新的)→ verify 必须抓到漂移
            st.publish(doc, v1, expected_version_id=cur["version_id"])
            v_drift = tu.verify_user("pixiv", src_dir, store, render, results)
            self.assertFalse(v_drift["ok"])
            self.assertFalse(v_drift["documents"][0]["rendered_matches_ref"])

    def test_finish_tsv_overwrites_partial_result(self):
        # Cursor 实测回归:完整 tsv 后仍遗留早期 partial result 时,finish 必须重组,不能使用缺段旧 result。
        import json as _json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir(); shutil.copy(BILINGUAL, bil_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()
            prep = tu.prepare_user("pixiv", src_dir, store, jobs, bilingual_dir=bil_dir)
            j = prep["jobs"][0]; sid = j["source_id"]
            bundle = _json.loads(Path(j["job"]).read_text(encoding="utf-8"))
            lines = [f"{i}\t{TR[seg['source_text']]}" for i, seg in enumerate(bundle["segments"])]
            (results / f"{sid}.zh.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
            # assemble_result 要求全段,所以直接模拟旧 partial result 的合法外形:同 digest 但 candidates 缺段。
            full = tu.result_assemble.assemble_result(
                bundle,
                {i: TR[seg["source_text"]] for i, seg in enumerate(bundle["segments"])},
                producer_name="cursor-grok",
                model="grok-test",
            )
            partial = {**full, "candidates": full["candidates"][:2]}
            (results / f"{sid}.result.json").write_text(_json.dumps(partial, ensure_ascii=False), encoding="utf-8")

            m = tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs, bilingual_dir=bil_dir)
            self.assertEqual(1, m["summary"]["published"])
            repaired = _json.loads((results / f"{sid}.result.json").read_text(encoding="utf-8"))
            self.assertEqual(len(bundle["segments"]), len(repaired["candidates"]))
            self.assertEqual({"type": "harness", "name": "cursor-grok", "model": "grok-test"}, repaired["producer"])
            self.assertEqual({"cursor-grok"}, {c["result_candidate_key"] for c in repaired["candidates"]})

    def test_finish_tsv_assemble_uses_original_job_catches_source_change(self):
        # Codex #136:tsv 用原始 job 组装;prepare 后改源 → 旧译文身份不符 → import 隔离,不发到错 revision
        import json as _json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir(); shutil.copy(BILINGUAL, bil_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()
            prep = tu.prepare_user("pixiv", src_dir, store, jobs, bilingual_dir=bil_dir)
            j = prep["jobs"][0]; sid = j["source_id"]
            bundle = _json.loads(Path(j["job"]).read_text(encoding="utf-8"))
            lines = [f"{i}\t{TR[seg['source_text']]}" for i, seg in enumerate(bundle["segments"])]
            (results / f"{sid}.zh.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
            # prepare 之后改源(同段数也不行)
            (src_dir / "700001.txt").write_text(
                (src_dir / "700001.txt").read_text(encoding="utf-8").replace("「おはよう」", "「こんにちは」"),
                encoding="utf-8")
            m = tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs, bilingual_dir=bil_dir)
            # 旧译文(原始 job 身份)与当前源不符 → 不得 published
            self.assertEqual(0, m["summary"]["published"])

    def test_finish_uses_existing_result_without_jobs_dir(self):
        # Codex #138:已有可用 result.json(+tsv 也在)但没传 jobs_dir → 用现成 result,不报 error
        import json as _json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "53230930"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            bil_dir = tmp / "bil"; bil_dir.mkdir(); shutil.copy(BILINGUAL, bil_dir / "700001.txt")
            store = tmp / "store"; jobs = tmp / "jobs"; results = tmp / "results"; render = tmp / "out"
            results.mkdir()
            prep = tu.prepare_user("pixiv", src_dir, store, jobs, bilingual_dir=bil_dir)
            j = prep["jobs"][0]; sid = j["source_id"]
            bundle = _json.loads(Path(j["job"]).read_text(encoding="utf-8"))
            lines = [f"{i}\t{TR[seg['source_text']]}" for i, seg in enumerate(bundle["segments"])]
            (results / f"{sid}.zh.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
            tu.finish_user("pixiv", src_dir, store, render, results, jobs_dir=jobs, bilingual_dir=bil_dir)
            self.assertTrue((results / f"{sid}.result.json").is_file())
            # 第二次不带 jobs_dir(tsv 仍在)→ 用现成 result,不报 error
            m = tu.finish_user("pixiv", src_dir, store, render, results, bilingual_dir=bil_dir)
            self.assertEqual(0, m["summary"]["errors"])
            self.assertEqual("ok", m["documents"][0]["status"])

    def test_finish_respects_limit(self):
        # Codex #122:finish 也要按 limit 切片,不扫 limit 之外的文件(否则报无关 no_result)
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "a"; src_dir.mkdir()
            shutil.copy(SRC, src_dir / "700001.txt")
            shutil.copy(SRC, src_dir / "700002.txt")
            m = tu.finish_user("pixiv", src_dir, tmp / "s", tmp / "out", tmp / "empty", limit=1)
            self.assertEqual(1, m["summary"]["total"])  # 只扫前 1 篇

    def test_finish_without_result_is_no_result(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir = tmp / "a"; src_dir.mkdir(); shutil.copy(SRC, src_dir / "700001.txt")
            m = tu.finish_user("pixiv", src_dir, tmp / "s", tmp / "out", tmp / "empty_results")
            self.assertEqual("no_result", m["documents"][0]["status"])

    def test_unknown_executor_rejected(self):
        with self.assertRaises(ValueError):
            tu.make_translate_fn("nope")


if __name__ == "__main__":
    unittest.main()
