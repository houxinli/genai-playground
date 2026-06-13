#!/usr/bin/env python3
"""文档漂移检查:把"文档跟上现实"从纪律变成 CI 闸门。

检查机械可查的陈旧:
- 测试基线数字(AGENTS.md 唯一来源)必须等于实际 pytest 计数。
- PROJECT_STATUS「Component Status」里的 backtick 文件路径必须存在。
纯函数与文件/子进程 IO 分离,便于单测。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List

_BASELINE_RE = re.compile(r"baseline 是 (\d+) 测试")
_PATH_RE = re.compile(r"`([^`]+)`")
_COMPONENT_HEADING = "## Component Status"


def check_test_baseline(agents_text: str, actual_count: int) -> List[str]:
    """AGENTS.md 的测试基线数字必须 == 实际计数(单一来源,防漂移)。"""
    m = _BASELINE_RE.search(agents_text)
    if not m:
        return ["AGENTS.md: 找不到 'baseline 是 N 测试' 基线声明"]
    declared = int(m.group(1))
    if declared != actual_count:
        return [f"AGENTS.md: 测试基线写 {declared},实际 collect {actual_count}(请同 PR 更新)"]
    return []


def _component_section(status_text: str) -> str:
    lines = status_text.splitlines()
    out: List[str] = []
    collecting = False
    for line in lines:
        if line.startswith(_COMPONENT_HEADING):
            collecting = True
            continue
        if collecting and line.startswith("## "):
            break
        if collecting:
            out.append(line)
    return "\n".join(out)


_PATH_EXTS = (".py", ".json", ".md", ".sh", ".yml", ".yaml", ".mdc", ".txt")
# 组件表里的路径有的相对仓库根、有的相对 tasks/translation,两根都试一遍。
_PATH_ROOTS = ("", "tasks/translation")


def _looks_like_path(token: str) -> bool:
    if " " in token or "*" in token or "/" not in token:
        return False  # 跳过 CLI 命令(含空格)、glob、非路径 token
    if "<" in token or ">" in token:
        return False  # 跳过占位符模板,如 data/pixiv/<USER_ID>/
    return token.endswith("/") or token.endswith(_PATH_EXTS)


def check_component_paths(status_text: str, root: Path) -> List[str]:
    """Component Status 表里每个 backtick 文件路径必须存在(仓库根或 tasks/translation 下)。"""
    errors: List[str] = []
    section = _component_section(status_text)
    seen = set()
    for token in _PATH_RE.findall(section):
        token = token.strip()
        if token in seen or not _looks_like_path(token):
            continue
        seen.add(token)
        if not any((root / base / token).exists() for base in _PATH_ROOTS):
            errors.append(f"PROJECT_STATUS Component Status: 引用了不存在的路径 {token}")
    return errors


def _actual_test_count(root: Path) -> int:
    """pytest --collect-only 的用例数(只收集不执行)。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tasks/translation/src", "--collect-only", "-q"],
        cwd=root, capture_output=True, text=True,
    )
    m = re.search(r"(\d+) tests? collected", proc.stdout + proc.stderr)
    if m:
        return int(m.group(1))
    # 老版 pytest 回退:数 collected 行
    return len([l for l in proc.stdout.splitlines() if "::" in l])


def run(root: Path) -> List[str]:
    errors: List[str] = []
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    status = (root / "docs" / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    errors += check_test_baseline(agents, _actual_test_count(root))
    errors += check_component_paths(status, root)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = run(args.root)
    if errors:
        print("文档漂移检查失败:")
        for e in errors:
            print(f"- {e}")
        return 1
    print("文档漂移检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
