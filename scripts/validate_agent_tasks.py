#!/usr/bin/env python3
"""Validate cross-agent task state, checkpoints, and repository invariants."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ACTIVE_TASK_STATUSES = {"planned", "active", "blocked"}
TERMINAL_TASK_STATUSES = {"complete", "cancelled"}


def _load_json(path: Path, errors: list[str]) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        return None


def _load_schema(path: Path, errors: list[str]) -> dict[str, Any] | None:
    schema = _load_json(path, errors)
    if schema is None:
        return None
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        errors.append(f"{path}: invalid JSON Schema: {exc}")
        return None
    return schema


def _validate_document(
    path: Path,
    document: Any,
    validator: Draft202012Validator,
    errors: list[str],
) -> None:
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{path}: schema error at {location}: {error.message}")


def _parse_timestamp(value: str, path: Path, errors: list[str]) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{path}: invalid timestamp: {value}")
        return None


def _validate_plan(state_path: Path, state: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    plan = state["plan"]
    step_ids = [step["id"] for step in plan]
    if len(step_ids) != len(set(step_ids)):
        errors.append(f"{state_path}: plan step ids must be unique")

    steps = {step["id"]: step for step in plan}
    for step in plan:
        for dependency in step["depends_on"]:
            if dependency not in steps:
                errors.append(
                    f"{state_path}: step {step['id']} depends on missing step {dependency}"
                )
            elif dependency == step["id"]:
                errors.append(f"{state_path}: step {step['id']} cannot depend on itself")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            errors.append(f"{state_path}: plan contains a dependency cycle at {step_id}")
            return
        visiting.add(step_id)
        for dependency in steps[step_id]["depends_on"]:
            if dependency in steps:
                visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in steps:
        visit(step_id)

    in_progress = [step for step in plan if step["status"] == "in_progress"]
    if len(in_progress) > 1:
        errors.append(f"{state_path}: at most one plan step may be in_progress")

    next_action = state["next_action"]
    if next_action is not None:
        step = steps.get(next_action["step_id"])
        if step is None:
            errors.append(
                f"{state_path}: next_action references missing step {next_action['step_id']}"
            )
        elif step["status"] != "in_progress":
            errors.append(
                f"{state_path}: next_action step {step['id']} must be in_progress, "
                f"not {step['status']}"
            )

    status = state["status"]
    if status in {"planned", "active"}:
        if len(in_progress) != 1:
            errors.append(f"{state_path}: {status} task must have exactly one in_progress step")
        if next_action is None:
            errors.append(f"{state_path}: {status} task must define next_action")
    elif status in TERMINAL_TASK_STATUSES:
        if in_progress:
            errors.append(f"{state_path}: terminal task cannot have an in_progress step")
        if next_action is not None:
            errors.append(f"{state_path}: terminal task must set next_action to null")

    active_blockers = [blocker for blocker in state["blockers"] if blocker["status"] == "active"]
    if status == "blocked" and not active_blockers:
        errors.append(f"{state_path}: blocked task must have at least one active blocker")
    if status == "complete":
        unfinished = [
            step["id"] for step in plan if step["status"] not in {"completed", "skipped"}
        ]
        if unfinished:
            errors.append(
                f"{state_path}: complete task has unfinished steps: {', '.join(unfinished)}"
            )
        if active_blockers:
            errors.append(f"{state_path}: complete task cannot have active blockers")

    return steps


def _load_checkpoints(
    path: Path,
    validator: Draft202012Validator,
    errors: list[str],
) -> list[dict[str, Any]]:
    if not path.exists():
        errors.append(f"{path}: missing checkpoints.jsonl")
        return []

    checkpoints: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"{path}: cannot read checkpoints: {exc}")
        return []

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            errors.append(f"{path}:{line_number}: blank lines are not allowed")
            continue
        try:
            checkpoint = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{line_number}: invalid JSON: {exc}")
            continue
        _validate_document(
            Path(f"{path}:{line_number}"),
            checkpoint,
            validator,
            errors,
        )
        if isinstance(checkpoint, dict):
            checkpoints.append(checkpoint)
    return checkpoints


def _validate_checkpoints(
    task_dir: Path,
    state: dict[str, Any],
    steps: dict[str, dict[str, Any]],
    validator: Draft202012Validator,
    errors: list[str],
) -> None:
    checkpoints_path = task_dir / "checkpoints.jsonl"
    checkpoints = _load_checkpoints(checkpoints_path, validator, errors)
    checkpoint_ids: set[str] = set()
    previous_timestamp: datetime | None = None

    for checkpoint in checkpoints:
        checkpoint_id = checkpoint.get("checkpoint_id")
        if checkpoint_id in checkpoint_ids:
            errors.append(f"{checkpoints_path}: duplicate checkpoint_id {checkpoint_id}")
        checkpoint_ids.add(checkpoint_id)

        if checkpoint.get("task_id") != state["task_id"]:
            errors.append(
                f"{checkpoints_path}: checkpoint {checkpoint_id} task_id does not match state"
            )
        if checkpoint.get("branch") != state["branch"]:
            errors.append(
                f"{checkpoints_path}: checkpoint {checkpoint_id} branch does not match state"
            )

        step_id = checkpoint.get("step_id")
        if step_id is not None and step_id not in steps:
            errors.append(
                f"{checkpoints_path}: checkpoint {checkpoint_id} references missing step {step_id}"
            )

        next_action = checkpoint.get("next_action")
        if isinstance(next_action, dict) and next_action.get("step_id") not in steps:
            errors.append(
                f"{checkpoints_path}: checkpoint {checkpoint_id} next_action references "
                f"missing step {next_action.get('step_id')}"
            )

        timestamp = checkpoint.get("timestamp")
        if isinstance(timestamp, str):
            parsed = _parse_timestamp(timestamp, checkpoints_path, errors)
            if parsed is not None and previous_timestamp is not None and parsed < previous_timestamp:
                errors.append(f"{checkpoints_path}: checkpoint timestamps must be monotonic")
            if parsed is not None:
                previous_timestamp = parsed

    last_checkpoint = state["last_checkpoint"]
    if last_checkpoint is None:
        if checkpoints:
            errors.append(
                f"{task_dir / 'state.json'}: last_checkpoint is null but checkpoint log is not empty"
            )
        return

    if not checkpoints:
        errors.append(
            f"{task_dir / 'state.json'}: last_checkpoint is set but checkpoint log is empty"
        )
        return

    latest = checkpoints[-1]
    for field in ("checkpoint_id", "timestamp", "agent", "observed_head"):
        if last_checkpoint[field] != latest.get(field):
            errors.append(
                f"{task_dir / 'state.json'}: last_checkpoint.{field} does not match "
                f"the final checkpoint"
            )


def validate_repository(root: Path) -> list[str]:
    """Return all validation errors for the repository rooted at ``root``."""

    root = root.resolve()
    errors: list[str] = []
    schemas_dir = root / "agent" / "schemas"
    templates_dir = root / "agent" / "templates"
    tasks_dir = root / "agent" / "tasks"

    state_schema = _load_schema(schemas_dir / "task-state.schema.json", errors)
    checkpoint_schema = _load_schema(schemas_dir / "checkpoint.schema.json", errors)
    if state_schema is None or checkpoint_schema is None:
        return errors

    format_checker = FormatChecker()
    state_validator = Draft202012Validator(state_schema, format_checker=format_checker)
    checkpoint_validator = Draft202012Validator(
        checkpoint_schema,
        format_checker=format_checker,
    )

    template_pairs = (
        (templates_dir / "task-state.json", state_validator),
        (templates_dir / "checkpoint.json", checkpoint_validator),
    )
    for template_path, validator in template_pairs:
        template = _load_json(template_path, errors)
        if template is not None:
            _validate_document(template_path, template, validator, errors)

    if not tasks_dir.exists():
        errors.append(f"{tasks_dir}: missing tasks directory")
        return errors

    active_tasks_by_branch: dict[str, list[Path]] = defaultdict(list)
    for state_path in sorted(tasks_dir.glob("*/state.json")):
        state = _load_json(state_path, errors)
        if not isinstance(state, dict):
            continue
        before_schema_errors = len(errors)
        _validate_document(state_path, state, state_validator, errors)
        if len(errors) != before_schema_errors:
            continue

        task_dir = state_path.parent
        if task_dir.name != state["task_id"]:
            errors.append(
                f"{state_path}: directory {task_dir.name} must match task_id {state['task_id']}"
            )

        if state["status"] in ACTIVE_TASK_STATUSES:
            active_tasks_by_branch[state["branch"]].append(state_path)

        steps = _validate_plan(state_path, state, errors)
        _validate_checkpoints(task_dir, state, steps, checkpoint_validator, errors)

    for branch, state_paths in sorted(active_tasks_by_branch.items()):
        if len(state_paths) > 1:
            joined = ", ".join(str(path) for path in state_paths)
            errors.append(f"branch {branch} has multiple active tasks: {joined}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    args = parser.parse_args()

    errors = validate_repository(args.root)
    if errors:
        print("Agent task validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Agent task validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
