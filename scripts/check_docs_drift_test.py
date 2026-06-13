import importlib.util
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("check_docs_drift", _ROOT / "scripts" / "check_docs_drift.py")
assert _SPEC and _SPEC.loader
CHECK = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(CHECK)


class TestBaselineTest(unittest.TestCase):
    def test_matching_baseline_passes(self):
        self.assertEqual([], CHECK.check_test_baseline("当前 baseline 是 188 测试全绿", 188))

    def test_stale_baseline_fails(self):
        errs = CHECK.check_test_baseline("当前 baseline 是 186 测试全绿", 188)
        self.assertTrue(any("186" in e and "188" in e for e in errs))

    def test_missing_baseline_fails(self):
        self.assertTrue(CHECK.check_test_baseline("无基线声明", 188))


class ComponentPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "sub").mkdir(); (self.root / "sub" / "real.py").write_text("x", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _status(self, body: str) -> str:
        return f"# S\n\n## Component Status\n\n{body}\n\n## Next\n\n`ignored/after.py`\n"

    def test_existing_path_passes(self):
        self.assertEqual([], CHECK.check_component_paths(self._status("| c | ok | `sub/real.py` |"), self.root))

    def test_missing_path_fails(self):
        errs = CHECK.check_component_paths(self._status("| c | ok | `sub/gone.py` |"), self.root)
        self.assertTrue(any("sub/gone.py" in e for e in errs))

    def test_glob_and_nonpath_skipped(self):
        body = "| c | ok | `tasks/**/*_test.py` | `schema_version` |"
        self.assertEqual([], CHECK.check_component_paths(self._status(body), self.root))

    def test_placeholder_and_command_skipped(self):
        # 占位符模板与含空格的 CLI 示例不当作路径
        body = "| c | ok | `data/pixiv/<USER_ID>/` | `src/x.py --flag` |"
        self.assertEqual([], CHECK.check_component_paths(self._status(body), self.root))

    def test_only_component_section_checked(self):
        # Next 区里的失效路径不计(只查 Component Status 区)
        self.assertEqual([], CHECK.check_component_paths(self._status("| c | ok | `sub/real.py` |"), self.root))


if __name__ == "__main__":
    unittest.main()
