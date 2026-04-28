#!/usr/bin/env python3
"""Tests for the bilingual name normalization helper script."""

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "normalize_bilingual_names.py"
SPEC = importlib.util.spec_from_file_location("normalize_bilingual_names", SCRIPT_PATH)
assert SPEC and SPEC.loader
normalize_bilingual_names = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = normalize_bilingual_names
SPEC.loader.exec_module(normalize_bilingual_names)


class NormalizeBilingualNamesScriptTest(unittest.TestCase):
    def test_auto_alias_rejects_canonical_with_trailing_text(self) -> None:
        self.assertFalse(normalize_bilingual_names.is_safe_auto_alias("高尾却", "高尾"))
        self.assertFalse(normalize_bilingual_names.is_safe_auto_alias("夏奈带", "夏奈"))

    def test_auto_alias_allows_distinct_known_variant_shape(self) -> None:
        self.assertTrue(normalize_bilingual_names.is_safe_auto_alias("高雄", "高尾"))


if __name__ == "__main__":
    unittest.main()
