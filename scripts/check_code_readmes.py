#!/usr/bin/env python3
"""Check that tracked code directories have a README.md."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable


CODE_SUFFIXES = {".py", ".js", ".sh", ".mdc"}
CODE_FILENAMES = {"Makefile", "pre-push", "translate"}
HARNESS_ROOTS = {".agents", ".claude", ".cursor"}
EXCLUDED_PARTS = {"config", "data", "docs", "logs", "schemas", "testdata"}
EXCLUDED_PREFIXES = {
    ("agent", "tasks"),
    ("agent", "prompts"),
    ("agent", "templates"),
    (".github",),
}


def _has_prefix(parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(parts) >= len(prefix) and parts[: len(prefix)] == prefix


def _is_excluded(path: PurePosixPath) -> bool:
    parts = path.parts
    if any(_has_prefix(parts, prefix) for prefix in EXCLUDED_PREFIXES):
        return True
    return bool(set(parts) & EXCLUDED_PARTS)


def _is_code_file(path: PurePosixPath) -> bool:
    parts = path.parts
    if not parts or path.name == "README.md":
        return False
    if parts[0] in HARNESS_ROOTS:
        return True
    return path.suffix in CODE_SUFFIXES or path.name in CODE_FILENAMES


def code_directories(files: Iterable[str]) -> set[str]:
    """Return code directories inferred from tracked repository paths."""
    dirs: set[str] = set()
    for raw in files:
        path = PurePosixPath(raw)
        if _is_excluded(path) or not _is_code_file(path):
            continue
        parent = path.parent
        while str(parent) != ".":
            if not _is_excluded(parent):
                dirs.add(str(parent))
            parent = parent.parent
    return dirs


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def missing_readmes(
    root: Path,
    dirs: Iterable[str],
    *,
    exists: Callable[[Path], bool] | None = None,
) -> list[str]:
    exists = exists or Path.is_file
    missing = []
    for directory in sorted(dirs):
        if not exists(root / directory / "README.md"):
            missing.append(directory)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--list", action="store_true", help="print all inferred code directories")
    args = parser.parse_args()

    root = args.root.resolve()
    dirs = sorted(code_directories(tracked_files(root)))
    if args.list:
        for directory in dirs:
            print(directory)
        return 0

    missing = missing_readmes(root, dirs)
    if missing:
        print("Missing README.md in tracked code directories:", file=sys.stderr)
        for directory in missing:
            print(f"- {directory}", file=sys.stderr)
        return 1
    print(f"Code README coverage OK ({len(dirs)} directories).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
