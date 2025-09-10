#!/usr/bin/env python3
"""
规则QC逐行测试：测试所有逐行规则检查函数
"""
import unittest

from .length_check import validate_length_ratio_lines
from .repetition_check import has_excessive_repetition_lines
from .jp_copy_check import has_chinese_copying_japanese_lines
from .cjk_punctuation_check import validate_cjk_separators_lines


class TestRuleQCLines(unittest.TestCase):
    """测试所有规则QC逐行检查函数"""
    
    def test_length_check_lines(self):
        """测试长度比例逐行检查"""
        # 正常情况
        original = ["短原文", "中等长度的原文", "这是一段比较长的原文内容"]
        translated = ["短译文", "中等长度的译文", "这是一段比较长的译文内容"]
        result = validate_length_ratio_lines(original, translated)
        self.assertEqual(result, ['GOOD', 'GOOD', 'GOOD'])
        
        # 译文过短
        original = ["1234567890"]
        translated = ["短"]
        result = validate_length_ratio_lines(original, translated)
        self.assertEqual(result, ['BAD'])
        
        # 译文过长
        original = ["短原文"]
        translated = ["这是一段非常非常非常长的译文" * 10]
        result = validate_length_ratio_lines(original, translated)
        self.assertEqual(result, ['BAD'])
        
        # 空译文
        original = ["原文"]
        translated = [""]
        result = validate_length_ratio_lines(original, translated)
        self.assertEqual(result, ['BAD'])
        
        # 行数不匹配
        original = ["原文1", "原文2", "原文3"]
        translated = ["译文1", "译文2"]
        result = validate_length_ratio_lines(original, translated)
        self.assertEqual(result, ['GOOD', 'GOOD', 'BAD'])
    
    def test_repetition_check_lines(self):
        """测试重复检查逐行检查"""
        # 正常文本
        lines = ["正常文本，没有明显重复。", "另一行正常文本"]
        result = has_excessive_repetition_lines(lines)
        self.assertEqual(result, ['GOOD', 'GOOD'])
        
        # 单字符重复（12个相同字符）
        lines = ["啊" * 20]
        result = has_excessive_repetition_lines(lines)
        self.assertEqual(result, ['BAD'])
        
        # 片段重复（10字符片段重复8次）
        lines = ["ABCDE12345" * 8]
        result = has_excessive_repetition_lines(lines, segment_len=10, segment_count_threshold=5)
        self.assertEqual(result, ['BAD'])
        
        # 短文本（少于10字符）
        lines = ["短文本"]
        result = has_excessive_repetition_lines(lines)
        self.assertEqual(result, ['GOOD'])
        
        # 空行
        lines = [""]
        result = has_excessive_repetition_lines(lines)
        self.assertEqual(result, ['GOOD'])
    
    def test_jp_copy_check_lines(self):
        """测试日文复制检查逐行检查"""
        # 正常翻译
        original = ["これは日本語です"]
        translated = ["这是日语"]
        result = has_chinese_copying_japanese_lines(original, translated)
        self.assertEqual(result, ['GOOD'])
        
        # 完全相同且包含假名
        original = ["これは日本語です"]
        translated = ["これは日本語です"]
        result = has_chinese_copying_japanese_lines(original, translated)
        self.assertEqual(result, ['BAD'])
        
        # 完全相同但不包含假名（中文汉字）
        original = ["日本語"]
        translated = ["日本語"]
        result = has_chinese_copying_japanese_lines(original, translated)
        self.assertEqual(result, ['GOOD'])
        
        # 空行
        original = [""]
        translated = [""]
        result = has_chinese_copying_japanese_lines(original, translated)
        self.assertEqual(result, ['GOOD'])
        
        # 行数不匹配
        original = ["原文1", "原文2", "原文3"]
        translated = ["译文1", "译文2"]
        result = has_chinese_copying_japanese_lines(original, translated)
        self.assertEqual(result, ['GOOD', 'GOOD', 'BAD'])
    
    def test_cjk_punctuation_check_lines(self):
        """测试CJK标点检查逐行检查"""
        # 正常文本（有标点）
        lines = ["这是一段正常的中文文本，包含标点符号。"]
        result = validate_cjk_separators_lines(lines)
        self.assertEqual(result, ['GOOD'])
        
        # 长串无标点（80+字符）
        long_text = "这是一段非常长的中文文本没有任何标点符号" * 4  # 超过80字符
        lines = [long_text]
        result = validate_cjk_separators_lines(lines)
        self.assertEqual(result, ['BAD'])
        
        # 长串有标点
        long_text_with_punct = "这是一段非常长的中文文本，包含标点符号。" * 3  # 超过80字符但有标点
        lines = [long_text_with_punct]
        result = validate_cjk_separators_lines(lines)
        self.assertEqual(result, ['GOOD'])
        
        # 短文本
        lines = ["短文本"]
        result = validate_cjk_separators_lines(lines)
        self.assertEqual(result, ['GOOD'])
        
        # 空行
        lines = [""]
        result = validate_cjk_separators_lines(lines)
        self.assertEqual(result, ['GOOD'])
        
        # 混合情况
        lines = [
            "正常文本",
            "这是一段非常长的中文文本没有任何标点符号" * 4,  # BAD
            "另一段正常文本，有标点。"
        ]
        result = validate_cjk_separators_lines(lines)
        self.assertEqual(result, ['GOOD', 'BAD', 'GOOD'])
    
    def test_all_rules_integration(self):
        """测试所有规则的综合使用"""
        original_lines = [
            "1234567890",  # 10字符原文
            "これは日本語です",
            "这是一段非常长的中文文本没有任何标点符号" * 4,  # 80+字符
            "正常长度的原文内容"
        ]
        translated_lines = [
            "短",  # 长度检查：BAD (1/10 = 0.1 < 0.3)
            "これは日本語です",  # 日文复制检查：BAD
            "这是一段非常长的中文文本没有任何标点符号" * 4,  # CJK标点检查：BAD
            "正常长度的译文内容"  # 所有检查：GOOD
        ]
        
        # 长度检查
        length_result = validate_length_ratio_lines(original_lines, translated_lines)
        self.assertEqual(length_result, ['BAD', 'GOOD', 'GOOD', 'GOOD'])
        
        # 重复检查
        repetition_result = has_excessive_repetition_lines(translated_lines)
        self.assertEqual(repetition_result, ['GOOD', 'GOOD', 'GOOD', 'GOOD'])
        
        # 日文复制检查
        copy_result = has_chinese_copying_japanese_lines(original_lines, translated_lines)
        self.assertEqual(copy_result, ['GOOD', 'BAD', 'GOOD', 'GOOD'])
        
        # CJK标点检查
        punctuation_result = validate_cjk_separators_lines(translated_lines)
        self.assertEqual(punctuation_result, ['GOOD', 'GOOD', 'BAD', 'GOOD'])


if __name__ == "__main__":
    unittest.main()
