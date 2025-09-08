#!/usr/bin/env python3
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
import json
import pprint


class TestQCLLMBuildMessages(unittest.TestCase):
    def setUp(self):
        self.config = TranslationConfig()
        self.qc = QualityChecker(self.config)

    def test_build_quality_messages_format(self):
        messages = self.qc._build_quality_messages("ほらっ、とっとと歩け！", "喂，快点走！", bilingual=True)
        # 调试输出实际构造内容
        print("\n[QC messages built]: len=", len(messages))
        for i, m in enumerate(messages, 1):
            print(f"[{i}] role={m.get('role')}\n{(m.get('content') or '').strip()}\n---")
        # 从真实资产生成的期望文件读取 expected
        expected_path = Path(__file__).parents[2] / "data" / "test" / "qc_expected_messages.json"
        with expected_path.open("r", encoding="utf-8") as f:
            expected = json.load(f)

        # 展示完整差异
        self.maxDiff = None
        # 为避免文本文件末尾空白差异，逐项比较并strip
        self.assertEqual(len(messages), len(expected), msg=f"len mismatch: actual={len(messages)} expected={len(expected)}\nactual={messages}")
        for i, (m, e) in enumerate(zip(messages, expected), 1):
            self.assertEqual(m.get("role"), e.get("role"), msg=f"role mismatch at index {i}\nactual={m}\nexpected={e}")
            self.assertEqual((m.get("content") or "").strip(), (e.get("content") or "").strip(), msg=f"content mismatch at index {i}\nactual={m}\nexpected={e}")


if __name__ == "__main__":
    unittest.main()


