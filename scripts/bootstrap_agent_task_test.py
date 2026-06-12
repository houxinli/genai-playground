import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPOSITORY_ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BOOTSTRAP = _load("bootstrap_agent_task")
VALIDATOR = _load("validate_agent_tasks")


class BootstrapAgentTaskTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        shutil.copytree(REPOSITORY_ROOT / "agent" / "schemas", self.root / "agent" / "schemas")
        shutil.copytree(REPOSITORY_ROOT / "agent" / "templates", self.root / "agent" / "templates")
        (self.root / "agent" / "tasks").mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _bootstrap(self, task_id="gh-1-one", branch="feat/one", **kwargs):
        return BOOTSTRAP.bootstrap_task(
            self.root,
            task_id=task_id,
            branch=branch,
            title="Test task",
            objective="Do one observable thing.",
            **kwargs,
        )

    def _task_dirs(self):
        return sorted(p.name for p in (self.root / "agent" / "tasks").iterdir())

    def test_bootstrap_creates_valid_task(self):
        task_dir = self._bootstrap(issue=42, status="active")
        self.assertTrue((task_dir / "state.json").is_file())
        self.assertEqual("", (task_dir / "checkpoints.jsonl").read_text(encoding="utf-8"))
        state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("gh-1-one", state["task_id"])
        self.assertEqual("feat/one", state["branch"])
        self.assertEqual(42, state["github"]["issue"])
        self.assertIsNone(state["github"]["pull_request"])
        self.assertIsNone(state["last_checkpoint"])
        self.assertEqual("S1", state["next_action"]["step_id"])
        self.assertEqual([], VALIDATOR.validate_repository(self.root))

    def test_bootstrap_rejects_duplicate_active_branch(self):
        self._bootstrap("gh-1-one", "feat/shared")
        with self.assertRaises(BOOTSTRAP.BootstrapError):
            self._bootstrap("gh-2-two", "feat/shared")
        self.assertEqual(["gh-1-one"], self._task_dirs())

    def test_bootstrap_rejects_existing_task_dir(self):
        self._bootstrap("gh-1-one", "feat/one")
        with self.assertRaises(BOOTSTRAP.BootstrapError):
            self._bootstrap("gh-1-one", "feat/other")
        self.assertEqual(["gh-1-one"], self._task_dirs())

    def test_bootstrap_rejects_invalid_task_id(self):
        for bad in ("AB", "Bad_ID", "-leading", "ab"):
            with self.assertRaises(BOOTSTRAP.BootstrapError):
                self._bootstrap(bad, "feat/bad")
        self.assertEqual([], self._task_dirs())

    def test_bootstrap_allows_branch_reuse_after_terminal_task(self):
        task_dir = self._bootstrap("gh-1-one", "feat/reuse")
        state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
        state["status"] = "complete"
        state["plan"][0]["status"] = "completed"
        state["next_action"] = None
        (task_dir / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._bootstrap("gh-2-two", "feat/reuse")
        self.assertEqual(["gh-1-one", "gh-2-two"], self._task_dirs())
        self.assertEqual([], VALIDATOR.validate_repository(self.root))

    def test_failed_validation_leaves_no_directory(self):
        (self.root / "agent" / "templates" / "task-state.json").write_text(
            json.dumps({"schema_version": 1}), encoding="utf-8"
        )
        with self.assertRaises(BOOTSTRAP.BootstrapError):
            self._bootstrap("gh-1-one", "feat/one")
        self.assertEqual([], self._task_dirs())


if __name__ == "__main__":
    unittest.main()
