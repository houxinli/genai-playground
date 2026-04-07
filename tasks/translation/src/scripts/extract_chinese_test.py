#!/usr/bin/env python3
import sys
import json
import tempfile
import unittest
from pathlib import Path


_FILE = Path(__file__).resolve()
_REPO_ROOT = _FILE.parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tasks.translation.src.scripts.extract_chinese import merge_chinese_files


def _make_bilingual_article() -> str:
    return "\n".join(
        [
            "---",
            "novel_id: 2001",
            "title: Original Safe Title",
            "create_date: 2024-01-01T00:00:00+09:00",
            "---",
            "原文1",
            "译文1",
            "原文2",
            "译文2",
        ]
    )


class TestExtractChinesePackagingRegression(unittest.TestCase):
    def test_merge_falls_back_to_original_title_when_translation_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "story_bilingual"
            source_dir = root / "story"
            source_dir.mkdir(parents=True, exist_ok=True)
            input_dir.mkdir(parents=True, exist_ok=True)
            article = input_dir / "2001.txt"
            article.write_text(_make_bilingual_article(), encoding="utf-8")
            (source_dir / "2001.meta.json").write_text(
                json.dumps({"novel_id": 2001, "title": "Original Safe Title"}, ensure_ascii=False),
                encoding="utf-8",
            )

            output_file = root / "merged.txt"
            ok = merge_chinese_files(
                [input_dir],
                include_original=False,
                min_lines=0,
                output_override=output_file,
            )

            self.assertTrue(ok)
            self.assertTrue(output_file.exists())
            merged = output_file.read_text(encoding="utf-8")
            self.assertIn("第1章 Original Safe Title", merged)


if __name__ == "__main__":
    unittest.main()
