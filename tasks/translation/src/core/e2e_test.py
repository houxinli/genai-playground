#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端 vertical slice:source → revision → legacy candidates → evaluations → 保守择优 →
DocumentVersion → publish(current ref)→ render bilingual。串真实函数,fixture 数据,不调模型。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from . import candidate_eval, legacy_import, source_identity as si, task_export as te, version_select
    from .artifact_store import ArtifactStore
except ImportError:  # core/ 在 sys.path 上
    import candidate_eval
    import legacy_import
    import source_identity as si
    import task_export as te
    import version_select
    from artifact_store import ArtifactStore


TESTDATA = Path(__file__).resolve().parent / "testdata"
SRC = TESTDATA / "fixtures" / "pixiv" / "700001" / "700001.txt"
RENDER_GOLDEN = TESTDATA / "golden" / "pixiv-700001.render.bilingual.txt"
BILINGUAL = RENDER_GOLDEN  # 全字段双键 bilingual(含 metadata 配对),legacy import 可覆盖全 segment


class EndToEndSliceTest(unittest.TestCase):
    def test_source_to_published_render(self):
        rev = si.build_document_revision("pixiv", SRC)
        doc = rev["document_id"]

        # 1) legacy bilingual → Candidate v3 + Attestation(既有译文=incumbent)
        cands, atts, issues = legacy_import.build_legacy_candidates("pixiv", SRC, BILINGUAL, "demo")
        self.assertEqual([], issues, issues)

        # 2) 入库(revision 先入,过 integrity gate)
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp))
            store.put_many(doc, [rev, *cands, *atts])

            # 3) 逐 candidate 跑确定性 QA → Evaluation,入库
            segs = {s["segment_id"]: s for s in rev["segments"]}
            evals = [candidate_eval.evaluate_candidate(c, segs[c["segment_id"]]["source_text"]) for c in cands]
            store.put_many(doc, evals)
            evals_by_cand = {}
            for ev in evals:
                evals_by_cand.setdefault(ev["candidate_id"], []).append(ev)

            # 4) 保守择优:legacy 候选作 incumbent(无挑战者)→ 每段都有可落地 selection
            segments_input = [
                {"segment_id": c["segment_id"],
                 "incumbent": {"candidate_id": c["candidate_id"], "evaluations": evals_by_cand[c["candidate_id"]]},
                 "challengers": []}
                for c in cands
            ]
            recs = version_select.recommend_selection(segments_input)
            self.assertEqual({s["segment_id"] for s in rev["segments"]}, {r["segment_id"] for r in recs})

            # 5) 建不可变 DocumentVersion v2,入库
            version = version_select.build_document_version(rev, recs, "workflow", "2026-01-01T00:00:00Z")
            store.put_many(doc, [version])

            # 6) 发布:current ref 指向该 version(发布≠创建)
            self.assertIsNone(store.current_ref(doc))
            store.publish(doc, version["version_id"], published_at="2026-02-02T00:00:00Z")
            self.assertEqual(version["version_id"], store.current_ref(doc)["version_id"])

            # 7) 从发布版本渲染 bilingual,逐字节符合 golden
            published = store.current_ref(doc)["version_id"]
            ver = store.get("document-version", doc, published)
            cands_by_id = {c["candidate_id"]: c for c in store.list_shard("candidate", doc)}
            out = version_select.render_version(rev, ver, cands_by_id, SRC.read_text(encoding="utf-8"))
            self.assertEqual(RENDER_GOLDEN.read_text(encoding="utf-8"), out)

    def test_translate_bundle_export_in_slice(self):
        # slice 旁路:同一 revision 也能导出 translate job bundle(自包含,供 harness 跑新候选)
        rev = si.build_document_revision("pixiv", SRC)
        ids = [s["segment_id"] for s in rev["segments"] if s["kind"] == "body"]
        bundle = te.export_job(rev, ids)
        self.assertEqual(len(ids), len(bundle["segments"]))
        self.assertIn("context_pack", bundle)


if __name__ == "__main__":
    unittest.main()
