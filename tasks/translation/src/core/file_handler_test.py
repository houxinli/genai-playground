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
from tasks.translation.src.core.file_handler import FileHandler
from tasks.translation.src.core.logger import UnifiedLogger


def _make_partial_bilingual_content() -> str:
    lines = [
        "---",
        "novel_id: 1001",
        "title: 原始标题",
        "title: 中文标题",
        "create_date: 2024-01-01T00:00:00+09:00",
        "---",
    ]
    for i in range(12):
        lines.append(f"原文{i}：这是用于回归测试的内容。")
        lines.append(f"译文{i}：这是用于回归测试的内容。")
        if i == 2:
            lines.append("[翻译未完成]")
    return "\n".join(lines)


class TestFileHandlerPartialBilingualRegression(unittest.TestCase):
    def test_plan_tasks_does_not_skip_partial_bilingual_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            original = base / "1001.txt"
            output_dir = base.parent / f"{base.name}_zh"
            output_path = output_dir / "1001.txt"

            original.write_text("原文A\n原文B\n", encoding="utf-8")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path.write_text(_make_partial_bilingual_content(), encoding="utf-8")

            handler = FileHandler(
                TranslationConfig(),
                UnifiedLogger.create_console_only(),
                quality_checker=None,
            )

            tasks = handler.plan_tasks([str(original)])

            self.assertEqual(1, len(tasks))
            task = tasks[0]
            self.assertEqual("translate", task.mode)
            self.assertEqual(original, task.original_path)
            self.assertEqual(output_path, task.output_path)

    def test_plan_tasks_skips_bilingual_input_without_repair_flag(self) -> None:
        # 普通翻译误指向双语产物时必须跳过,不得未经 --repair-existing 静默转修复
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            bilingual_dir = base / "pixiv" / "50235390_bilingual"
            bilingual_dir.mkdir(parents=True, exist_ok=True)
            bilingual = bilingual_dir / "12430834.txt"
            bilingual.write_text("---\nnovel_id: 1\n---\n原文A\n译文A\n", encoding="utf-8")

            handler = FileHandler(
                TranslationConfig(),
                UnifiedLogger.create_console_only(),
                quality_checker=None,
            )

            tasks = handler.plan_tasks([str(bilingual)])

            self.assertEqual([], tasks)

    def test_plan_tasks_builds_repair_task_for_existing_bilingual(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            original_dir = base / "pixiv" / "50235390"
            bilingual_dir = base / "pixiv" / "50235390_bilingual"
            original_dir.mkdir(parents=True, exist_ok=True)
            bilingual_dir.mkdir(parents=True, exist_ok=True)

            original = original_dir / "12430834.txt"
            bilingual = bilingual_dir / "12430834.txt"
            original.write_text("---\nnovel_id: 1\n---\n原文A\n", encoding="utf-8")
            bilingual.write_text("---\nnovel_id: 1\n---\n原文A\n[翻译未完成]\n", encoding="utf-8")

            handler = FileHandler(
                TranslationConfig(repair_existing=True),
                UnifiedLogger.create_console_only(),
                quality_checker=None,
            )

            tasks = handler.plan_tasks([str(original)])

            self.assertEqual(1, len(tasks))
            task = tasks[0]
            self.assertEqual("repair", task.mode)
            self.assertEqual(original, task.original_path)
            self.assertEqual(bilingual, task.existing_bilingual_path)
            self.assertEqual(
                base / "pixiv" / "50235390_bilingual_fixed" / "12430834.txt",
                task.output_path,
            )


if __name__ == "__main__":
    unittest.main()
