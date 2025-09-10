#!/usr/bin/env python3
import unittest

from .jp_copy_check import has_chinese_copying_japanese_lines


class TestJpCopyCheck(unittest.TestCase):
    def test_detect_copy_when_same_and_kana(self):
        orig = [
            "彼は走った。",
            "彼は転んだ。",
            "立ち上がった。",
        ]
        tran = [
            "彼は走った。",
            "彼は転んだ。",
            "他站起来了。",
        ]
        result = has_chinese_copying_japanese_lines(orig, tran, bilingual=True)
        self.assertEqual(result, ['BAD', 'BAD', 'GOOD'])

    def test_no_copy_when_translated(self):
        orig = [
            "彼は走った。",
            "彼は転んだ。",
            "立ち上がった。",
        ]
        tran = [
            "他跑了起来。",
            "他摔倒了。",
            "他站了起来。",
        ]
        result = has_chinese_copying_japanese_lines(orig, tran, bilingual=True)
        self.assertEqual(result, ['GOOD', 'GOOD', 'GOOD'])


if __name__ == "__main__":
    unittest.main()


