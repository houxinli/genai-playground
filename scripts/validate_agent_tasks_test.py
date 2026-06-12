import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "validate_agent_tasks.py"
SPEC = importlib.util.spec_from_file_location("validate_agent_tasks", MODULE_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class AgentTaskValidatorTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        shutil.copytree(REPOSITORY_ROOT / "agent" / "schemas", self.root / "agent" / "schemas")
        shutil.copytree(REPOSITORY_ROOT / "agent" / "templates", self.root / "agent" / "templates")
        (self.root / "agent" / "tasks").mkdir()
        self.state_template = json.loads(
            (REPOSITORY_ROOT / "agent" / "templates" / "task-state.json").read_text()
        )
        self.checkpoint_template = json.loads(
            (REPOSITORY_ROOT / "agent" / "templates" / "checkpoint.json").read_text()
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_task(self, task_id="gh-1-one", branch="feat/one"):
        state = copy.deepcopy(self.state_template)
        state.update(
            {
                "task_id": task_id,
                "branch": branch,
                "status": "active",
                "last_checkpoint": {
                    "checkpoint_id": "cp-1",
                    "timestamp": "2026-06-12T00:00:00Z",
                    "agent": "test",
                    "summary": "Bootstrap task",
                    "observed_head": "abcdef0",
                },
            }
        )
        checkpoint = copy.deepcopy(self.checkpoint_template)
        checkpoint.update(
            {
                "checkpoint_id": "cp-1",
                "task_id": task_id,
                "branch": branch,
                "timestamp": "2026-06-12T00:00:00Z",
                "agent": "test",
                "observed_head": "abcdef0",
                "next_action": copy.deepcopy(state["next_action"]),
            }
        )
        task_dir = self.root / "agent" / "tasks" / task_id
        task_dir.mkdir()
        (task_dir / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (task_dir / "checkpoints.jsonl").write_text(
            json.dumps(checkpoint, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return task_dir, state, checkpoint

    def test_empty_tasks_directory_is_valid(self):
        self.assertEqual([], VALIDATOR.validate_repository(self.root))

    def test_valid_task_is_accepted(self):
        self._write_task()
        self.assertEqual([], VALIDATOR.validate_repository(self.root))

    def test_directory_must_match_task_id(self):
        task_dir, _, _ = self._write_task()
        task_dir.rename(task_dir.parent / "wrong-directory")
        errors = VALIDATOR.validate_repository(self.root)
        self.assertTrue(any("must match task_id" in error for error in errors))

    def test_branch_cannot_have_multiple_active_tasks(self):
        self._write_task("gh-1-one", "feat/shared")
        self._write_task("gh-2-two", "feat/shared")
        errors = VALIDATOR.validate_repository(self.root)
        self.assertTrue(any("multiple active tasks" in error for error in errors))

    def test_next_action_must_reference_in_progress_step(self):
        task_dir, state, _ = self._write_task()
        state["plan"][0]["status"] = "completed"
        (task_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        errors = VALIDATOR.validate_repository(self.root)
        self.assertTrue(any("must be in_progress" in error for error in errors))

    def test_last_checkpoint_must_match_log_tail(self):
        task_dir, state, _ = self._write_task()
        state["last_checkpoint"]["checkpoint_id"] = "cp-stale"
        (task_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        errors = VALIDATOR.validate_repository(self.root)
        self.assertTrue(any("last_checkpoint.checkpoint_id" in error for error in errors))

    def test_malformed_checkpoint_is_rejected(self):
        task_dir, _, _ = self._write_task()
        (task_dir / "checkpoints.jsonl").write_text("{not-json}\n", encoding="utf-8")
        errors = VALIDATOR.validate_repository(self.root)
        self.assertTrue(any("invalid JSON" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
