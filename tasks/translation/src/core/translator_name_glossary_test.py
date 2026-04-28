#!/usr/bin/env python3
"""Tests for name glossary prompt compaction."""

import unittest

try:
    from .translator import Translator
except ImportError:  # unittest discover may import this test as top-level core.translator_name_glossary_test.
    from tasks.translation.src.core.translator import Translator


class TranslatorNameGlossaryTest(unittest.TestCase):
    def test_manual_rule_uses_preferred_name_and_forbidden_aliases(self) -> None:
        translator = Translator.__new__(Translator)

        compact = translator._compact_name_glossary("タカオ=高尾|高男,高冈,高雄")

        self.assertEqual(compact, ["- タカオ => 高尾；禁止译为: 高男,高冈,高雄"])

    def test_formatted_block_explains_one_way_mapping(self) -> None:
        translator = Translator.__new__(Translator)

        block = translator._format_name_glossary_block("ハルカ=春香|春花")

        self.assertIn("“=>”后的中文名是唯一标准译名", block)
        self.assertIn("- ハルカ => 春香；禁止译为: 春花", block)


if __name__ == "__main__":
    unittest.main()
