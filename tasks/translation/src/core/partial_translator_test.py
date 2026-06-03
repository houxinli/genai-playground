#!/usr/bin/env python3
"""Regression tests: repair must not overwrite a valid translation with a placeholder."""

import unittest

try:
    from .partial_translator import PartialTranslationHelper
except ImportError:  # pragma: no cover - direct execution
    from partial_translator import PartialTranslationHelper


class _Config:
    context_lines = 3
    repair_context_lines = 0  # disable context payload noise


class _FakeTranslator:
    """Stub translator whose translate_lines_simple behaviour is configurable."""

    def __init__(self, *, ok, lines=None):
        self._ok = ok
        self._lines = lines or []
        self.logger = None
        self.current_output_path = None

    def translate_lines_simple(self, target_lines, previous_io=None, start_line_number=None, context_lines=None):
        if not self._ok:
            return [], "", False, {}, None
        return list(self._lines), "", True, {}, None


PLACEHOLDER = "[翻译未完成]"


class NonDestructiveRepairTest(unittest.TestCase):
    def _run(self, *, ok, lines, reference):
        helper = PartialTranslationHelper(_Config(), _FakeTranslator(ok=ok, lines=lines))
        body = ["モモのパイズリ。"]
        ref = list(reference)
        result = helper.translate_segments(body, [(0, 0)], reference_translations=ref)
        return result, ref

    def test_refusal_preserves_valid_reference(self):
        # Model refuses (ok=False); a good Chinese translation already exists.
        result, ref = self._run(ok=False, lines=[], reference=["モモ的乳交。"])
        self.assertEqual(result[0], "モモ的乳交。")
        self.assertEqual(ref[0], "モモ的乳交。")
        self.assertNotEqual(result[0], PLACEHOLDER)

    def test_refusal_without_reference_yields_placeholder(self):
        result, _ = self._run(ok=False, lines=[], reference=[None])
        self.assertEqual(result[0], PLACEHOLDER)

    def test_invalid_new_translation_falls_back_to_reference(self):
        # Re-translation comes back kana-only -> keep the prior valid translation.
        result, _ = self._run(ok=True, lines=["モモ"], reference=["モモ的乳交。"])
        self.assertEqual(result[0], "モモ的乳交。")

    def test_good_new_translation_replaces_reference(self):
        result, _ = self._run(ok=True, lines=["桃的乳交场面。"], reference=["モモ的乳交。"])
        self.assertEqual(result[0], "桃的乳交场面。")

    def test_japanese_only_reference_is_not_preserved(self):
        # A "same as source" line has no valid Chinese reference -> placeholder on refusal.
        result, _ = self._run(ok=False, lines=[], reference=["モモのパイズリ。"])
        self.assertEqual(result[0], PLACEHOLDER)


if __name__ == "__main__":
    unittest.main()
