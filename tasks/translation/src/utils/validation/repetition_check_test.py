#!/usr/bin/env python3
import unittest

from .repetition_check import has_excessive_repetition_lines


class TestRepetitionCheck(unittest.TestCase):
    def test_no_repetition(self):
        result = has_excessive_repetition_lines(["正常文本，没有明显重复。"])
        self.assertEqual(result, ['GOOD'])

    def test_char_repetition(self):
        result = has_excessive_repetition_lines(["啊" * 20])
        self.assertEqual(result, ['BAD'])

    def test_segment_repetition(self):
        text = ("ABCDE12345" * 8)  # 8次重复
        result = has_excessive_repetition_lines([text], segment_len=10, segment_count_threshold=5)
        self.assertEqual(result, ['BAD'])


if __name__ == "__main__":
    unittest.main()



