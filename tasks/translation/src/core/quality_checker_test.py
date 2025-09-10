#!/usr/bin/env python3
import unittest
import sys
from pathlib import Path

# 确保可以从仓库根导入 tasks.translation 包
_FILE = Path(__file__).resolve()
_REPO_ROOT = _FILE.parents[4]  # repo_root / tasks / translation / src / core / this_file
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tasks.translation.src.core.config import TranslationConfig
from tasks.translation.src.core.quality_checker import QualityChecker
from tasks.translation.src.core.logger import UnifiedLogger


class DummyStreamingHandler:
    def __init__(self, fixed_text: str):
        self.fixed_text = fixed_text

    def stream_with_params(self, model, messages, params):
        # 返回固定结果与一个简易token统计
        return self.fixed_text, {"input_tokens": 0, "output_tokens": len(self.fixed_text) // 2}


class TestQualityCheckerLLM(unittest.TestCase):
    def setUp(self):
        self.config = TranslationConfig()
        # 保障有日志器且不会因为缺少属性报错
        self.logger = UnifiedLogger.create_console_only()

    def test_llm_line_check_good(self):
        qc = QualityChecker(self.config, logger=self.logger)
        # 注入假的streaming_handler，返回GOOD
        qc.streaming_handler = DummyStreamingHandler("GOOD")
        ok, reason = qc.check_translation_quality_with_llm(
            original_text="彼は走った。\n立ち上がった。",
            translated_text="他跑了起来。\n他站起来了。",
        )
        self.assertTrue(ok, msg=reason)

    def test_llm_line_check_bad(self):
        qc = QualityChecker(self.config, logger=self.logger)
        # 注入假的streaming_handler，返回BAD
        qc.streaming_handler = DummyStreamingHandler("思考...\n结论: BAD")
        ok, reason = qc.check_translation_quality_with_llm(
            original_text="彼は走った。\n立ち上がった。",
            translated_text="彼は走った。\n他站起来了。",
        )
        self.assertFalse(ok)
        self.assertIn("BAD", reason)


if __name__ == "__main__":
    unittest.main()


