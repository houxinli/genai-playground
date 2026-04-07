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


if __name__ == "__main__":
    unittest.main()
