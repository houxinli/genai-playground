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
        # 现实现仅包含 system + user 两段，验证关键文案
        self.assertEqual(len(messages), 2)
        sys_content = (messages[0].get("content") or "")
        self.assertIn("你是专业的翻译质量评估专家", sys_content)
        self.assertIn("为每一行给出0-1之间的分数", sys_content)
        self.assertIn("中文译文出现日语假名", sys_content)
        user_content = (messages[1].get("content") or "")
        self.assertIn("原文：", user_content)
        self.assertIn("译文：", user_content)

    def test_build_quality_messages_lines(self):
        # 验证逐行QC消息构建（system包含必需指令；user结构严格对齐）
        # 现实现采用打分制，不再输出 GOOD/BAD/结论/检查完成 的逐行模板
        orig_lines = ["「ほらっ、とっとと歩け！", "彼は走った。"]
        tran_lines = ["「喂，快点走！", "他跑了起来。"]
        messages = self.qc._build_quality_messages_lines(orig_lines, tran_lines, bilingual=True)
        # 至少包含 system 与 user
        self.assertGreaterEqual(len(messages), 2)
        sys_content = (messages[0].get("content") or "")
        self.assertIn("为每一行给出0-1之间的分数", sys_content)
        # 最后一个 user 段应包含原文/译文
        last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        user_content = (last_user.get("content") or "") if last_user else ""
        self.assertIn("原文：", user_content)
        self.assertIn("译文：", user_content)


if __name__ == "__main__":
    unittest.main()


