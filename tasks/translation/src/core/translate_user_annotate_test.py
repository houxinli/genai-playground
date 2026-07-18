#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""annotate 线(#174)e2e:prepare 注解 job → 注解 TSV → finish(评估/择优/注解版本/独立 ref)→ render study。"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

try:
    from . import translate_user as tu
    from .artifact_store import ArtifactStore
    from .translate_user_test import _mock_executor
except ImportError:
    import translate_user as tu
    from artifact_store import ArtifactStore
    from translate_user_test import _mock_executor


TESTDATA = Path(__file__).resolve().parent / "testdata"
SRC = TESTDATA / "fixtures" / "pixiv" / "700001" / "700001.txt"
BILINGUAL = TESTDATA / "golden" / "pixiv-700001.render.bilingual.txt"

# fixture 的 2 个 body 段(顺序即 job 段序)。
BODY = ["「おはよう」", "今日はいい天気だ。"]
ANN_OK = ["「おはよう」", "今日(きょう)はいい天気(てんき・天气)だ。"]  # 段0 不注(原样),段1 注解
ANN_BAD = ["「おはよう」", "今日はいい天気(てんき"]  # 括号不配对 → fail


def _write_tsv(path: Path, bundle: dict, lines: list) -> None:
    rows = []
    for i, seg in enumerate(bundle["segments"]):
        rows.append(f"{i}\t{seg['source_text'][:8]}\t{lines[i]}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


class AnnotatePipelineTest(unittest.TestCase):
    def _setup(self, tmp: Path):
        """翻译发布(前置)+ prepare 注解 job。返回 (src_dir, store_root, render_dir, jobs_dir, results_dir, bundle)。"""
        src_dir = tmp / "700000"; src_dir.mkdir()
        shutil.copy(SRC, src_dir / "700001.txt")
        bil_dir = tmp / "bil"; bil_dir.mkdir()
        shutil.copy(BILINGUAL, bil_dir / "700001.txt")
        store_root = tmp / "store"; render_dir = tmp / "out"
        m = tu.translate_user("pixiv", src_dir, store_root, render_dir, _mock_executor, bilingual_dir=bil_dir)
        assert m["summary"]["published"] == 1
        jobs_dir = tmp / "jobs"; results_dir = tmp / "results"; results_dir.mkdir()
        pm = tu.prepare_annotate_user("pixiv", src_dir, store_root, jobs_dir)
        assert pm["jobs"][0].get("job"), pm
        bundle = json.loads((jobs_dir / "700001.annotate.job.json").read_text(encoding="utf-8"))
        return src_dir, store_root, render_dir, jobs_dir, results_dir, bundle

    def test_annotate_job_is_body_only_with_annotate_task_type(self):
        with tempfile.TemporaryDirectory() as t:
            *_, bundle = self._setup(Path(t))
            self.assertEqual("annotate", bundle["task"]["task_type"])
            self.assertEqual(BODY, [s["source_text"] for s in bundle["segments"]])  # 只有 body 段

    def test_finish_publishes_annotate_channel_and_renders_study(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, store_root, render_dir, jobs_dir, results_dir, bundle = self._setup(tmp)
            _write_tsv(results_dir / "700001.annotate.tsv", bundle, ANN_OK)
            m = tu.finish_annotate_user("pixiv", src_dir, store_root, render_dir, results_dir,
                                        jobs_dir=jobs_dir, producer_name="tester")
            self.assertEqual(1, m["summary"]["published"], m)
            store = ArtifactStore(store_root)
            doc = m["documents"][0]["document_id"]
            # 注解版本发布在独立 channel,不动翻译 current ref
            self.assertIsNotNone(store.current_ref(doc, channel="annotate"))
            trans_ref = store.current_ref(doc)
            self.assertIsNotNone(trans_ref)
            self.assertNotEqual(trans_ref["version_id"], store.current_ref(doc, channel="annotate")["version_id"])
            # study 渲染:注解行 + 当前译文交织,未注解段原样
            study = (render_dir / "700001.study.txt").read_text(encoding="utf-8")
            self.assertIn("今日(きょう)はいい天気(てんき・天气)だ。", study)
            self.assertIn("今天天气真好。", study)      # 译文行来自翻译 current 版本
            self.assertIn("「おはよう」", study)         # 未注解段原样
            self.assertIn("title: 朝の挨拶", study)      # front-matter 保留(不注解)

    def test_failing_annotation_blocks_version(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, store_root, render_dir, jobs_dir, results_dir, bundle = self._setup(tmp)
            _write_tsv(results_dir / "700001.annotate.tsv", bundle, ANN_BAD)
            m = tu.finish_annotate_user("pixiv", src_dir, store_root, render_dir, results_dir,
                                        jobs_dir=jobs_dir, producer_name="tester")
            self.assertEqual(0, m["summary"]["published"])
            self.assertEqual(1, m["summary"]["unresolved"])
            detail = m["documents"][0]["unresolved_details"][0]
            self.assertEqual(1, detail["segment_index"])
            self.assertEqual(BODY[1], detail["source_text"])
            self.assertEqual(ANN_BAD[1], detail["candidates"][0]["candidate_text"])
            self.assertEqual("unbalanced_parens", detail["candidates"][0]["findings"][0]["code"])
            self.assertIsNone(ArtifactStore(store_root).current_ref(
                m["documents"][0]["document_id"], channel="annotate"))

    def test_cli_finish_returns_nonzero_with_failure_details(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, store_root, render_dir, jobs_dir, results_dir, bundle = self._setup(tmp)
            _write_tsv(results_dir / "700001.annotate.tsv", bundle, ANN_BAD)
            argv = [
                "translate_user.py", "--provider", "pixiv", "--source-dir", str(src_dir),
                "--store", str(store_root), "--mode", "finish", "--render-dir", str(render_dir),
                "--jobs-dir", str(jobs_dir), "--results-dir", str(results_dir),
                "--task-type", "annotate", "--producer", "tester",
            ]
            output = io.StringIO()
            with patch("sys.argv", argv), redirect_stdout(output):
                exit_code = tu.main()
            payload = json.loads(output.getvalue())
            self.assertEqual(1, exit_code)
            self.assertEqual("unresolved", payload["documents"][0]["status"])
            self.assertEqual(1, payload["documents"][0]["unresolved_details"][0]["segment_index"])

    def test_multi_producer_priority_selects_preferred(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, store_root, render_dir, jobs_dir, results_dir, bundle = self._setup(tmp)
            ann_a = ["「おはよう(问候语)」", "今日(きょう)はいい天気だ。"]
            _write_tsv(results_dir / "700001.annotate.aaa.tsv", bundle, ann_a)
            _write_tsv(results_dir / "700001.annotate.composer-2.5.tsv", bundle, ANN_OK)
            m = tu.finish_annotate_user("pixiv", src_dir, store_root, render_dir, results_dir,
                                        jobs_dir=jobs_dir, producer_priority=["composer-2.5", "aaa"])
            self.assertEqual(1, m["summary"]["published"], m)
            study = (render_dir / "700001.study.txt").read_text(encoding="utf-8")
            self.assertNotIn("「おはよう(问候语)」", study)
            self.assertIn("今日(きょう)はいい天気(てんき・天气)だ。", study)

    def test_repeated_finish_reuses_annotate_version(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, store_root, render_dir, jobs_dir, results_dir, bundle = self._setup(tmp)
            _write_tsv(results_dir / "700001.annotate.tsv", bundle, ANN_OK)
            first = tu.finish_annotate_user("pixiv", src_dir, store_root, render_dir, results_dir,
                                            jobs_dir=jobs_dir, producer_name="tester")
            store = ArtifactStore(store_root)
            doc = first["documents"][0]["document_id"]
            ref_before = store.current_ref(doc, channel="annotate")
            versions_before = len(store.list_shard("document-version", doc))
            attestations_before = len(store.list_shard("attestation", doc))

            second = tu.finish_annotate_user("pixiv", src_dir, store_root, render_dir, results_dir,
                                             jobs_dir=jobs_dir, producer_name="tester")

            self.assertEqual(ref_before, store.current_ref(doc, channel="annotate"))
            self.assertEqual(versions_before, len(store.list_shard("document-version", doc)))
            self.assertEqual(attestations_before, len(store.list_shard("attestation", doc)))
            self.assertEqual(first["documents"][0]["version_id"], second["documents"][0]["version_id"])

    def test_status_reports_workspace_progress(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, store_root, render_dir, jobs_dir, results_dir, bundle = self._setup(tmp)
            prepared = tu.status_annotate_user(
                "pixiv", src_dir, store_root, render_dir, results_dir, jobs_dir=jobs_dir)
            self.assertEqual("awaiting_result", prepared["documents"][0]["status"])

            _write_tsv(results_dir / "700001.annotate.composer-2.5.tsv", bundle, ANN_OK)
            ready = tu.status_annotate_user(
                "pixiv", src_dir, store_root, render_dir, results_dir, jobs_dir=jobs_dir)
            self.assertEqual("ready_to_finish", ready["documents"][0]["status"])

            tu.finish_annotate_user(
                "pixiv", src_dir, store_root, render_dir, results_dir,
                jobs_dir=jobs_dir, producer_priority=["composer-2.5"])
            published = tu.status_annotate_user(
                "pixiv", src_dir, store_root, render_dir, results_dir, jobs_dir=jobs_dir)
            self.assertEqual("published", published["documents"][0]["status"])
            self.assertTrue(published["documents"][0]["study"].endswith("700001.study.txt"))

    def test_translate_republish_does_not_touch_annotate_ref(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src_dir, store_root, render_dir, jobs_dir, results_dir, bundle = self._setup(tmp)
            _write_tsv(results_dir / "700001.annotate.tsv", bundle, ANN_OK)
            m = tu.finish_annotate_user("pixiv", src_dir, store_root, render_dir, results_dir,
                                        jobs_dir=jobs_dir, producer_name="tester")
            store = ArtifactStore(store_root)
            doc = m["documents"][0]["document_id"]
            ann_ref_before = store.current_ref(doc, channel="annotate")["version_id"]
            # 重新跑翻译(幂等 republish 路径)——注解 ref 不动
            tu.translate_user("pixiv", src_dir, store_root, render_dir, _mock_executor)
            self.assertEqual(ann_ref_before, store.current_ref(doc, channel="annotate")["version_id"])


if __name__ == "__main__":
    unittest.main()
