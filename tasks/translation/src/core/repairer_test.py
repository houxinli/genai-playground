#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path


_FILE = Path(__file__).resolve()
_REPO_ROOT = _FILE.parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tasks.translation.src.core.config import TranslationConfig
from tasks.translation.src.core.logger import UnifiedLogger
from tasks.translation.src.core.qa_gate import TranslationQAGate
from tasks.translation.src.core.repairer import BilingualRepairer
from tasks.translation.src.core.task import TranslationTask


class _FakeTranslator:
    def __init__(self) -> None:
        self.logger = None
        self.streaming_handler = None
        self.current_output_path = None

    def translate_lines_simple(
        self,
        target_lines,
        previous_io=None,
        start_line_number=1,
        context_lines=None,
    ):
        translated = []
        for line in target_lines:
            text = line.strip()
            if text == "ふた行目。":
                translated.append("第二行。")
            elif text == "拒否行。":
                translated.append("拒绝行。")
            else:
                translated.append("占位中文。")
        return translated, "", True, {}, None


class TestBilingualRepairer(unittest.TestCase):
    def test_repair_task_fixes_missing_lines_and_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            original_dir = base / "pixiv" / "50235390"
            bilingual_dir = base / "pixiv" / "50235390_bilingual"
            output_dir = base / "pixiv" / "50235390_bilingual_fixed"
            original_dir.mkdir(parents=True, exist_ok=True)
            bilingual_dir.mkdir(parents=True, exist_ok=True)

            original = original_dir / "12430834.txt"
            bilingual = bilingual_dir / "12430834.txt"
            output = output_dir / "12430834.txt"

            original.write_text(
                "---\nnovel_id: 1\n---\n一行目。\nふた行目。\n",
                encoding="utf-8",
            )
            bilingual.write_text(
                "---\nnovel_id: 1\n---\n一行目。\n第一行。\nふた行目。\n[翻译未完成]\n",
                encoding="utf-8",
            )

            config = TranslationConfig(log_dir=base / "logs", repair_existing=True)
            repairer = BilingualRepairer(
                config,
                _FakeTranslator(),
                UnifiedLogger.create_console_only(),
            )

            result = repairer.repair_task(
                TranslationTask(
                    original_path=original,
                    existing_bilingual_path=bilingual,
                    output_path=output,
                    mode="repair",
                )
            )

            self.assertTrue(result.success)
            self.assertEqual("complete", result.status)
            self.assertTrue(output.exists())

            content = output.read_text(encoding="utf-8")
            self.assertIn("一行目。\n第一行。", content)
            self.assertIn("ふた行目。\n第二行。", content)
            self.assertNotIn("[翻译未完成]", content)

    def test_repair_task_uses_qa_report_indices_for_refusal_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            original_dir = base / "pixiv" / "50235390"
            bilingual_dir = base / "pixiv" / "50235390_bilingual"
            output_dir = base / "pixiv" / "50235390_bilingual_fixed"
            report_path = base / "qa" / "50235390_bilingual_12430834.qa.json"
            original_dir.mkdir(parents=True, exist_ok=True)
            bilingual_dir.mkdir(parents=True, exist_ok=True)

            original = original_dir / "12430834.txt"
            bilingual = bilingual_dir / "12430834.txt"
            output = output_dir / "12430834.txt"

            original.write_text(
                "---\nnovel_id: 1\n---\n一行目。\n拒否行。\n",
                encoding="utf-8",
            )
            bilingual.write_text(
                "---\nnovel_id: 1\n---\n一行目。\n第一行。\n拒否行。\n抱歉，不能协助。\n",
                encoding="utf-8",
            )

            report = TranslationQAGate().run(bilingual, original)
            TranslationQAGate.write_report(report, report_path)

            config = TranslationConfig(log_dir=base / "logs", repair_existing=True)
            repairer = BilingualRepairer(
                config,
                _FakeTranslator(),
                UnifiedLogger.create_console_only(),
            )

            result = repairer.repair_task(
                TranslationTask(
                    original_path=original,
                    existing_bilingual_path=bilingual,
                    output_path=output,
                    mode="repair",
                ),
                qa_report_path=report_path,
            )

            self.assertTrue(result.success)
            content = output.read_text(encoding="utf-8")
            self.assertIn("拒否行。\n拒绝行。", content)
            self.assertNotIn("不能协助", content)


if __name__ == "__main__":
    unittest.main()
