#!/usr/bin/env python3
"""Bootstrap a new agent task directory (state.json + empty checkpoints.jsonl) from the template."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


TASK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,}$")

DEFAULT_FIRST_STEP_TITLE = "把 scope、plan 与 next_action 具体化为本任务的真实步骤"
DEFAULT_NEXT_ACTION = (
    "将 state.json 的 scope/plan/next_action 从 bootstrap 占位内容具体化为本任务的真实步骤，"
    "然后运行 make agent-validate。"
)
DEFAULT_ACCEPTANCE = [
    "scope/plan/next_action 不再含 bootstrap 占位文案",
    "make agent-validate 通过",
]
SCOPE_PLACEHOLDER_IN = "(bootstrap 占位) 待补：本任务拥有的路径或子系统"
SCOPE_PLACEHOLDER_OUT = "(bootstrap 占位) 待补：明确排除的相邻工作"


class BootstrapError(Exception):
    """Raised when the task cannot be bootstrapped; nothing has been written."""


def _load_validator_module() -> Any:
    module_path = Path(__file__).resolve().with_name("validate_agent_tasks.py")
    spec = importlib.util.spec_from_file_location("validate_agent_tasks", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scan_active_branches(tasks_dir: Path) -> dict[str, str]:
    """Map branch -> task_id for every planned/active/blocked task state."""
    validator = _load_validator_module()
    branches: dict[str, str] = {}
    for state_path in sorted(tasks_dir.glob("*/state.json")):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BootstrapError(f"{state_path}: cannot inspect existing task: {exc}") from exc
        if not isinstance(state, dict):
            raise BootstrapError(f"{state_path}: state.json must contain an object")
        if state.get("status") in validator.ACTIVE_TASK_STATUSES:
            branches[str(state.get("branch"))] = str(state.get("task_id"))
    return branches


def build_state(
    template: dict[str, Any],
    *,
    task_id: str,
    branch: str,
    title: str,
    objective: str,
    issue: int | None,
    status: str,
    first_step_title: str,
    next_action_instruction: str,
    acceptance: list[str],
    scope_in: list[str],
    scope_out: list[str],
) -> dict[str, Any]:
    state = json.loads(json.dumps(template))
    state.update(
        {
            "task_id": task_id,
            "title": title,
            "status": status,
            "branch": branch,
            "objective": objective,
        }
    )
    state["github"] = {"issue": issue, "pull_request": None}
    state["scope"] = {"in": scope_in, "out": scope_out}
    state["plan"] = [
        {
            "id": "S1",
            "title": first_step_title,
            "status": "in_progress",
            "depends_on": [],
            "acceptance": acceptance,
        }
    ]
    state["next_action"] = {
        "step_id": "S1",
        "instruction": next_action_instruction,
        "acceptance": acceptance,
    }
    state["last_checkpoint"] = None
    state["next_task"] = None
    return state


def bootstrap_task(
    root: Path,
    *,
    task_id: str,
    branch: str,
    title: str,
    objective: str,
    issue: int | None = None,
    status: str = "planned",
    first_step_title: str = DEFAULT_FIRST_STEP_TITLE,
    next_action_instruction: str = DEFAULT_NEXT_ACTION,
    acceptance: list[str] | None = None,
    scope_in: list[str] | None = None,
    scope_out: list[str] | None = None,
) -> Path:
    """Create agent/tasks/<task_id>/ and return its path. Raises BootstrapError without writing."""

    root = root.resolve()
    tasks_dir = root / "agent" / "tasks"
    template_path = root / "agent" / "templates" / "task-state.json"

    if not TASK_ID_PATTERN.match(task_id):
        raise BootstrapError(
            f"invalid task_id {task_id!r}: must match {TASK_ID_PATTERN.pattern}"
        )
    if not branch.strip():
        raise BootstrapError("branch must not be empty")
    if status not in {"planned", "active"}:
        raise BootstrapError(f"bootstrap status must be planned or active, not {status!r}")
    if not tasks_dir.is_dir():
        raise BootstrapError(f"{tasks_dir}: missing tasks directory")
    if not template_path.is_file():
        raise BootstrapError(f"{template_path}: missing task-state template")

    task_dir = tasks_dir / task_id
    if task_dir.exists():
        raise BootstrapError(f"{task_dir}: task directory already exists")

    active_branches = _scan_active_branches(tasks_dir)
    if branch in active_branches:
        raise BootstrapError(
            f"branch {branch} already has active task {active_branches[branch]}; "
            "finish or cancel it first"
        )

    template = json.loads(template_path.read_text(encoding="utf-8"))
    state = build_state(
        template,
        task_id=task_id,
        branch=branch,
        title=title,
        objective=objective,
        issue=issue,
        status=status,
        first_step_title=first_step_title,
        next_action_instruction=next_action_instruction,
        acceptance=acceptance or list(DEFAULT_ACCEPTANCE),
        scope_in=scope_in or [SCOPE_PLACEHOLDER_IN],
        scope_out=scope_out or [SCOPE_PLACEHOLDER_OUT],
    )

    task_dir.mkdir()
    try:
        (task_dir / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (task_dir / "checkpoints.jsonl").write_text("", encoding="utf-8")
        errors = _load_validator_module().validate_repository(root)
        if errors:
            raise BootstrapError(
                "bootstrap produced an invalid repository state:\n"
                + "\n".join(f"- {error}" for error in errors)
            )
    except BaseException:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise
    return task_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True, help="e.g. gh-12-short-slug")
    parser.add_argument("--branch", required=True, help="topic branch owning this task")
    parser.add_argument("--title", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--issue", type=int, default=None, help="GitHub issue number")
    parser.add_argument("--status", choices=("planned", "active"), default="planned")
    parser.add_argument("--first-step-title", default=DEFAULT_FIRST_STEP_TITLE)
    parser.add_argument("--next-action", default=DEFAULT_NEXT_ACTION)
    parser.add_argument(
        "--acceptance",
        action="append",
        default=None,
        help="repeatable; acceptance lines for the first step",
    )
    parser.add_argument("--scope-in", action="append", default=None, help="repeatable")
    parser.add_argument("--scope-out", action="append", default=None, help="repeatable")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    args = parser.parse_args()

    try:
        task_dir = bootstrap_task(
            args.root,
            task_id=args.task_id,
            branch=args.branch,
            title=args.title,
            objective=args.objective,
            issue=args.issue,
            status=args.status,
            first_step_title=args.first_step_title,
            next_action_instruction=args.next_action,
            acceptance=args.acceptance,
            scope_in=args.scope_in,
            scope_out=args.scope_out,
        )
    except BootstrapError as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(f"Bootstrapped {task_dir.relative_to(args.root.resolve())}")
    print("Next: concretize scope/plan/next_action, then commit the task bootstrap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
