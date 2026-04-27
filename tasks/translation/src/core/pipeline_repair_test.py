#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


_FILE = Path(__file__).resolve()
_REPO_ROOT = _FILE.parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tasks.translation.src.core.config import TranslationConfig
from tasks.translation.src.core.pipeline import TranslationPipeline
from tasks.translation.src.core.task import TranslationTask


class TestTranslationPipelineRepairTask(unittest.TestCase):
    def test_process_task_delegates_repair_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            pipeline = TranslationPipeline(
                TranslationConfig(log_dir=base / "logs", llm_provider="vllm")
            )
            task = TranslationTask(
                original_path=base / "source.txt",
                existing_bilingual_path=base / "source_bilingual.txt",
                output_path=base / "source_bilingual_fixed.txt",
                mode="repair",
            )

            pipeline.process_repair_task = mock.Mock(return_value=True)

            self.assertTrue(pipeline.process_task(task))
            pipeline.process_repair_task.assert_called_once_with(task)


if __name__ == "__main__":
    unittest.main()
