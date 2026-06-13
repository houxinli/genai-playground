#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pixiv/Fanbox fixture 的 revision/segment ID 稳定性与 golden 回归测试。

revision_id 被 pin 成字面量:身份算法(canonical 载荷、adapter/segmentation 版本)任何变化
都会让本测试失败——这正是 system-design §5.2 要求的"算法版本变化必须产生新 revision"。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

try:
    from . import source_identity as si
    from .artifact_schemas import validate_artifact
except ImportError:  # core/ 直接在 sys.path 上
    import source_identity as si
    from artifact_schemas import validate_artifact


TESTDATA = Path(__file__).resolve().parent / "testdata"
FIXTURES = TESTDATA / "fixtures"
GOLDEN = TESTDATA / "golden"

CASES = {
    "pixiv-700001": {
        "provider": "pixiv",
        "source": FIXTURES / "pixiv" / "700001" / "700001.txt",
        "revision_id": "rev_17eed95790c6425841e5976b4de316e08ab389698a11d9f85e9ebf04119c890f",
    },
    "fanbox-800001": {
        "provider": "fanbox",
        "source": FIXTURES / "fanbox" / "800001" / "800001.txt",
        "revision_id": "rev_1a7aa0769861d62f6a38c9c2fdff02c94aa323871c3c632e1584275bc0638aca",
    },
}


def _golden(name: str, suffix: str) -> str:
    return (GOLDEN / f"{name}.{suffix}").read_text(encoding="utf-8")


def _parse_pairs(bilingual: str):
    """golden bilingual:每对为 源行/译行,空行分隔,返回 [(source, translation), ...]。"""
    blocks = [b for b in bilingual.strip().split("\n\n") if b.strip()]
    pairs = []
    for block in blocks:
        lines = block.splitlines()
        pairs.append((lines[0], lines[1]))
    return pairs


class RevisionStabilityTest(unittest.TestCase):
    def test_revision_id_is_pinned(self):
        for name, case in CASES.items():
            meta, body = si.parse_source(case["source"])
            self.assertEqual(
                case["revision_id"],
                si.compute_revision_id(case["provider"], meta, body),
                f"{name}: revision_id 漂移——身份算法若有意变更,请同步更新 golden 与 pin",
            )

    def test_build_matches_golden_and_schema(self):
        for name, case in CASES.items():
            built = si.build_document_revision(case["provider"], case["source"])
            golden = json.loads(_golden(name, "document-revision.json"))
            self.assertEqual(golden, built, name)
            self.assertEqual([], validate_artifact("document-revision", built), name)

    def test_build_is_deterministic(self):
        for case in CASES.values():
            a = si.build_document_revision(case["provider"], case["source"])
            b = si.build_document_revision(case["provider"], case["source"])
            self.assertEqual(a, b)

    def test_segment_ids_reference_revision_and_are_unique(self):
        for case in CASES.values():
            art = si.build_document_revision(case["provider"], case["source"])
            seg_ids = [s["segment_id"] for s in art["segments"]]
            self.assertEqual(len(seg_ids), len(set(seg_ids)))
            for seg in art["segments"]:
                self.assertTrue(seg["segment_id"].startswith(art["revision_id"] + ":"))
                self.assertTrue(seg["source_hash"].startswith(seg["segment_id"].rsplit(":", 1)[1]))

    def test_source_text_change_changes_revision(self):
        case = CASES["pixiv-700001"]
        meta, body = si.parse_source(case["source"])
        mutated = si.compute_revision_id(case["provider"], meta, body + ["新しい行。"])
        self.assertNotEqual(case["revision_id"], mutated)

    def test_algorithm_version_change_changes_revision(self):
        case = CASES["pixiv-700001"]
        meta, body = si.parse_source(case["source"])
        with mock.patch.object(si, "SEGMENTATION_VERSION", "nonempty-lines-v2"):
            bumped = si.compute_revision_id(case["provider"], meta, body)
        self.assertNotEqual(case["revision_id"], bumped)


class ProviderIdentityTest(unittest.TestCase):
    def test_provider_specific_creator_and_metadata(self):
        # Fanbox 读 creator.id 与 excerpt/published_at(非 Pixiv 的 author.id/caption/create_date)
        art = si.build_document_revision("fanbox", CASES["fanbox-800001"]["source"])
        self.assertEqual("fanbox:800000:800001", art["document_id"])
        self.assertEqual("800000", art["source"]["creator_id"])
        self.assertIn("published_at", art["metadata"])
        self.assertEqual("フィクスチャ用のサンプル。", art["metadata"]["caption"])
        # Pixiv 读 author.id
        art_p = si.build_document_revision("pixiv", CASES["pixiv-700001"]["source"])
        self.assertEqual("pixiv:700000:700001", art_p["document_id"])

    def test_missing_creator_id_raises(self):
        meta = {"post_id": "800001", "title": "x", "creator": {"name": "no-id"}}
        with self.assertRaises(ValueError):
            si._identity("fanbox", meta)
        # 字符串 "None" 也必须被拒绝,不得污染身份
        meta2 = {"novel_id": "1", "author": {"id": None}}
        with self.assertRaises(ValueError):
            si._identity("pixiv", meta2)


class GoldenRenderConsistencyTest(unittest.TestCase):
    def test_bilingual_pairs_match_body_segments(self):
        for name, case in CASES.items():
            art = si.build_document_revision(case["provider"], case["source"])
            body_sources = [s["source_text"] for s in art["segments"] if s["kind"] == "body"]
            pairs = _parse_pairs(_golden(name, "bilingual.txt"))
            self.assertEqual(body_sources, [src for src, _ in pairs], name)
            for _, translation in pairs:
                self.assertTrue(translation.strip(), f"{name}: golden 译文行不应为空")

    def test_zh_matches_bilingual_translations(self):
        for name in CASES:
            pairs = _parse_pairs(_golden(name, "bilingual.txt"))
            zh_lines = [l for l in _golden(name, "zh.txt").splitlines() if l.strip()]
            self.assertEqual([t for _, t in pairs], zh_lines, name)


class FixtureHygieneTest(unittest.TestCase):
    def test_fixtures_are_sfw_and_offline(self):
        # fixture 不得标记成人内容,且不引用真实下载/模型端点
        for case in CASES.values():
            meta, _ = si.parse_source(case["source"])
            self.assertEqual(0, int(meta.get("x_restrict", 0)))
            text = case["source"].read_text(encoding="utf-8")
            for banned in ("localhost", "openrouter", "api.openai", "huggingface"):
                self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()
