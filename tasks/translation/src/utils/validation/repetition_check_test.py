#!/usr/bin/env python3
import unittest

from tasks.translation.src.utils.validation.repetition_check import has_excessive_repetition


class TestRepetitionCheck(unittest.TestCase):
    def test_no_repetition(self):
        self.assertFalse(has_excessive_repetition("正常文本，没有明显重复。"))

    def test_char_repetition(self):
        self.assertTrue(has_excessive_repetition("啊" * 20))

    def test_segment_repetition(self):
        text = ("ABCDE12345" * 6) + "尾巴"
        self.assertTrue(has_excessive_repetition(text, segment_len=5, segment_count_threshold=5))


if __name__ == "__main__":
    unittest.main()



