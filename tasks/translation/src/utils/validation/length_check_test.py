#!/usr/bin/env python3
import unittest

from tasks.translation.src.utils.validation.length_check import validate_length_ratio


class TestLengthCheck(unittest.TestCase):
    def test_empty_translated(self):
        ok, reason = validate_length_ratio("原文", "")
        self.assertFalse(ok)
        self.assertIn("译文为空", reason)

    def test_too_short(self):
        ok, reason = validate_length_ratio("1234567890", "短")
        self.assertFalse(ok)
        self.assertIn("译文过短", reason)

    def test_too_long(self):
        ok, reason = validate_length_ratio("短原文", "这是一段非常非常非常长的译文" * 10)
        self.assertFalse(ok)
        self.assertIn("译文过长", reason)

    def test_ok_range(self):
        ok, reason = validate_length_ratio("原文ABCDE", "译文ABCDE")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()



