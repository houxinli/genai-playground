import unittest
from pathlib import Path

from scripts import check_code_readmes as ccr


class CheckCodeReadmesTest(unittest.TestCase):
    def test_infers_code_ancestors_and_excludes_data_like_dirs(self):
        dirs = ccr.code_directories([
            "scripts/manage_vllm.sh",
            "tasks/translation/src/core/pipeline.py",
            "tasks/translation/src/core/testdata/golden/sample.json",
            "tasks/translation/config/presets.json",
            "agent/tasks/gh-1/state.json",
            "docs/PROJECT_STATUS.md",
        ])
        self.assertIn("scripts", dirs)
        self.assertIn("tasks", dirs)
        self.assertIn("tasks/translation", dirs)
        self.assertIn("tasks/translation/src", dirs)
        self.assertIn("tasks/translation/src/core", dirs)
        self.assertNotIn("tasks/translation/src/core/testdata", dirs)
        self.assertNotIn("tasks/translation/config", dirs)
        self.assertNotIn("agent/tasks", dirs)
        self.assertNotIn("docs", dirs)

    def test_harness_roots_are_code_directories(self):
        dirs = ccr.code_directories([
            ".agents/skills/translate/SKILL.md",
            ".claude/skills/extract-names/SKILL.md",
            ".cursor/rules/translate.mdc",
            ".github/workflows/tests.yml",
        ])
        self.assertIn(".agents", dirs)
        self.assertIn(".agents/skills", dirs)
        self.assertIn(".agents/skills/translate", dirs)
        self.assertIn(".claude/skills/extract-names", dirs)
        self.assertIn(".cursor/rules", dirs)
        self.assertNotIn(".github", dirs)

    def test_missing_readmes_uses_supplied_exists_predicate(self):
        root = Path("/repo")
        dirs = {"scripts", "tasks/translation/src"}
        existing = {root / "scripts" / "README.md"}
        missing = ccr.missing_readmes(root, dirs, exists=lambda path: path in existing)
        self.assertEqual(["tasks/translation/src"], missing)


if __name__ == "__main__":
    unittest.main()
