#!/usr/bin/env python3
import unittest

from .cjk_punctuation_check import validate_cjk_separators_lines


class TestCjkPunctuationCheck(unittest.TestCase):
    def test_ok_with_punct(self):
        result = validate_cjk_separators_lines(["这是一个正常的中文句子，包含逗号和句号。"])
        self.assertEqual(result, ['GOOD'])

    def test_warn_without_punct(self):
        long_run = "这是一个很长的中文段落" + ("很长" * 50)  # 超过80字符
        result = validate_cjk_separators_lines([long_run])
        self.assertEqual(result, ['BAD'])


if __name__ == "__main__":
    unittest.main()



