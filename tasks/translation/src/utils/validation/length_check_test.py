#!/usr/bin/env python3
import unittest

from .length_check import validate_length_ratio_lines


class TestLengthCheck(unittest.TestCase):
    def test_empty_translated(self):
        result = validate_length_ratio_lines(["原文"], [""])
        self.assertEqual(result, ['BAD'])

    def test_too_short(self):
        result = validate_length_ratio_lines(["1234567890"], ["短"])
        self.assertEqual(result, ['BAD'])

    def test_too_long(self):
        result = validate_length_ratio_lines(["短原文"], ["这是一段非常非常非常长的译文" * 10])
        self.assertEqual(result, ['BAD'])

    def test_ok_range(self):
        result = validate_length_ratio_lines(["原文ABCDE"], ["译文ABCDE"])
        self.assertEqual(result, ['GOOD'])


if __name__ == "__main__":
    unittest.main()



