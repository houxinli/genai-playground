#!/usr/bin/env python3
"""
测试规则QC集成到pipeline中
"""
import unittest
import sys
from pathlib import Path

# 确保可以从仓库根导入 tasks.translation 包
_FILE = Path(__file__).resolve()
_REPO_ROOT = _FILE.parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tasks.translation.src.core.quality_checker import QualityChecker
from tasks.translation.src.core.config import TranslationConfig


class TestRuleQCIntegration(unittest.TestCase):
    def setUp(self):
        self.config = TranslationConfig()
        self.qc = QualityChecker(self.config)

    def test_rule_qc_integration(self):
        """测试规则QC集成到基础检测中"""
        # 测试正常翻译
        original = "これは日本語です。\n彼は走った。"
        translated = "这是日语。\n他跑了起来。"
        
        result = self.qc.check_translation_quality_basic(original, translated)
        self.assertTrue(result[0], f"正常翻译应该通过: {result[1]}")
        
        # 测试长度问题 - 现在rule QC只做标记，不会直接导致基础检测失败
        original = "1234567890"
        translated = "短"
        
        result = self.qc.check_translation_quality_basic(original, translated)
        # 现在rule QC只做标记，基础检测会继续其他检查
        # 如果其他检查通过，基础检测就会通过
        self.assertTrue(result[0], f"rule QC现在只做标记，基础检测应该通过: {result[1]}")
        
        # 测试重复问题
        original = "正常文本"
        translated = "啊" * 20
        
        result = self.qc.check_translation_quality_basic(original, translated)
        # 重复检查会通过内部方法检测
        self.assertFalse(result[0], f"重复字符应该失败: {result[1]}")
        
        # 测试日文复制问题
        original = "これは日本語です"
        translated = "これは日本語です"
        
        result = self.qc.check_translation_quality_basic(original, translated)
        # 日文复制检查会通过内部方法检测
        self.assertFalse(result[0], f"日文复制应该失败: {result[1]}")
        
        # 测试CJK标点问题
        original = "短文本"
        translated = "这是一段非常长的中文文本没有任何标点符号" * 4  # 超过80字符
        
        result = self.qc.check_translation_quality_basic(original, translated)
        # CJK标点检查会通过内部方法检测
        self.assertFalse(result[0], f"CJK标点问题应该失败: {result[1]}")

    def test_rule_qc_lines_method(self):
        """测试逐行规则QC方法"""
        # 测试正常情况
        original = "これは日本語です。\n彼は走った。"
        translated = "这是日语。\n他跑了起来。"
        
        verdicts, summary, conclusion = self.qc.check_translation_quality_rules_lines(original, translated, bilingual=False)
        self.assertEqual(verdicts, ['GOOD', 'GOOD'], f"正常翻译应该都是GOOD: {verdicts}")
        self.assertEqual(conclusion, "不需要重译", f"正常翻译应该不需要重译: {conclusion}")
        
        # 测试混合情况（部分行有问题）
        original = "1234567890\n正常文本"
        translated = "短\n正常译文"
        
        verdicts, summary, conclusion = self.qc.check_translation_quality_rules_lines(original, translated, bilingual=False)
        self.assertEqual(verdicts, ['BAD', 'GOOD'], f"部分行有问题: {verdicts}")
        self.assertEqual(conclusion, "需要重译", f"有BAD行应该需要重译: {conclusion}")
        self.assertIn("BAD索引=[1]", summary, f"摘要应该包含BAD行信息: {summary}")

    def test_line_alignment_check(self):
        """测试行数对齐检查"""
        # 测试正常对齐
        original_lines = ["这是第一行", "这是第二行", "这是第三行"]
        translated_lines = ["This is line 1", "This is line 2", "This is line 3"]
        
        result = self.qc.check_line_alignment(original_lines, translated_lines)
        self.assertTrue(result[0], f"正常对齐应该通过: {result[1]}")
        
        # 测试行数不匹配
        original_lines = ["这是第一行", "这是第二行", "这是第三行"]
        translated_lines = ["This is line 1", "This is line 2"]  # 少一行
        
        result = self.qc.check_line_alignment(original_lines, translated_lines)
        self.assertFalse(result[0], f"行数不匹配应该失败: {result[1]}")
        self.assertIn("翻译行数不匹配", result[1])
        
        # 测试包含空白行的情况
        original_lines = ["这是第一行", "", "这是第三行"]  # 包含空白行
        translated_lines = ["This is line 1", "This is line 3"]  # 对应非空白行
        
        result = self.qc.check_line_alignment(original_lines, translated_lines)
        self.assertTrue(result[0], f"空白行应该被忽略: {result[1]}")


if __name__ == "__main__":
    unittest.main()

