#!/usr/bin/env python3
import unittest

from tasks.translation.src.utils.validation.jp_copy_check import has_chinese_copying_japanese


class TestJpCopyCheck(unittest.TestCase):
    def test_detect_copy_when_same_and_kana(self):
        orig = "\n".join([
            "彼は走った。",
            "彼は転んだ。",
            "立ち上がった。",
        ])
        tran = "\n".join([
            "彼は走った。",
            "彼は転んだ。",
            "他站起来了。",
        ])
        self.assertTrue(has_chinese_copying_japanese(orig, tran, bilingual=True))

    def test_no_copy_when_translated(self):
        orig = "\n".join([
            "彼は走った。",
            "彼は転んだ。",
            "立ち上がった。",
        ])
        tran = "\n".join([
            "他跑了起来。",
            "他摔倒了。",
            "他站了起来。",
        ])
        self.assertFalse(has_chinese_copying_japanese(orig, tran, bilingual=True))


if __name__ == "__main__":
    unittest.main()


