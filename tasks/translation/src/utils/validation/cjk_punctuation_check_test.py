#!/usr/bin/env python3
import unittest

from tasks.translation.src.utils.validation.cjk_punctuation_check import validate_cjk_separators


class TestCjkPunctuationCheck(unittest.TestCase):
    def test_ok_with_punct(self):
        ok, reason = validate_cjk_separators("这是一个正常的中文句子，包含逗号和句号。")
        self.assertTrue(ok)

    def test_warn_without_punct(self):
        long_run = "这是一个很长的中文段落" + ("很长" * 50)
        ok, reason = validate_cjk_separators(long_run)
        self.assertFalse(ok)
        self.assertIn("缺少分隔标点", reason)


if __name__ == "__main__":
    unittest.main()



