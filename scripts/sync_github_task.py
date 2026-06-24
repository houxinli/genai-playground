#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 agent/tasks 的生命周期同步到 GitHub issue:

- bootstrap → 给 issue 挂 `agent-active` 标签
- complete  → 摘 `agent-active`,并评论最终 validation 摘要

**同步失败一律降级为提示,不抛异常、不改本地流程**(无网络 / 无 gh / 权限不足时 bootstrap 仍成功)。
gh 调用经可注入 `runner` 完成,便于测试 mock。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

ACTIVE_LABEL = "agent-active"
# runner(cmd) -> (ok, output)
Runner = Callable[[List[str]], Tuple[bool, str]]


def _subprocess_runner(cmd: List[str]) -> Tuple[bool, str]:
    import subprocess
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def _gh(args: List[str], runner: Runner) -> Tuple[bool, str]:
    try:
        return runner(["gh", *args])
    except Exception as exc:  # runner 自身异常也降级
        return False, f"{type(exc).__name__}: {exc}"


def sync_bootstrap(issue: int, runner: Runner = _subprocess_runner) -> Optional[str]:
    """挂 agent-active。返回 None 表示成功,否则返回提示串(非致命)。"""
    ok, out = _gh(["issue", "edit", str(issue), "--add-label", ACTIVE_LABEL], runner)
    return None if ok else f"[warn] 未能给 #{issue} 挂 {ACTIVE_LABEL} 标签(已忽略): {out}"


def sync_complete(issue: int, summary: str, runner: Runner = _subprocess_runner) -> Optional[str]:
    """摘 agent-active + 评论摘要。任一步失败都汇总成提示串返回(非致命)。"""
    warns: List[str] = []
    ok, out = _gh(["issue", "edit", str(issue), "--remove-label", ACTIVE_LABEL], runner)
    if not ok:
        warns.append(f"摘 {ACTIVE_LABEL} 失败: {out}")
    ok, out = _gh(["issue", "comment", str(issue), "--body", summary], runner)
    if not ok:
        warns.append(f"评论失败: {out}")
    return f"[warn] #{issue} 完成同步部分失败(已忽略): {'; '.join(warns)}" if warns else None


def summary_from_state(state: dict) -> str:
    """从 state 的 validation.last_results 拼最终验证摘要 comment。"""
    lines = [f"✅ 任务 `{state.get('task_id')}` 完成。", "", "最终验证:"]
    results = state.get("validation", {}).get("last_results", [])
    if results:
        for r in results:
            lines.append(f"- `{r.get('command')}` → **{r.get('status')}**: {r.get('summary', '')}")
    else:
        lines.append("- (state 未记录 validation 结果)")
    pr = state.get("github", {}).get("pull_request")
    if pr:
        lines.append("")
        lines.append(f"PR #{pr}")
    return "\n".join(lines)


def _load_state(task_dir: Path) -> dict:
    return json.loads((Path(task_dir) / "state.json").read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, choices=("bootstrap", "complete"))
    parser.add_argument("--issue", type=int, default=None, help="GitHub issue 号(complete 可从 state 读)")
    parser.add_argument("--task-dir", type=Path, default=None, help="agent/tasks/<id>(complete 取 issue+摘要)")
    args = parser.parse_args()

    issue = args.issue
    warn: Optional[str] = None
    if args.event == "bootstrap":
        if issue is None:
            print("[warn] bootstrap 同步缺 --issue,跳过", file=sys.stderr)
            return 0
        warn = sync_bootstrap(issue)
    else:  # complete
        if args.task_dir is None:
            print("[warn] complete 同步缺 --task-dir,跳过", file=sys.stderr)
            return 0
        try:
            state = _load_state(args.task_dir)
        except Exception as exc:
            print(f"[warn] 读 state 失败,跳过同步(已忽略): {exc}", file=sys.stderr)
            return 0
        issue = issue or state.get("github", {}).get("issue")
        if issue is None:
            print("[warn] state 无 issue 号,跳过 complete 同步", file=sys.stderr)
            return 0
        warn = sync_complete(int(issue), summary_from_state(state))

    if warn:
        print(warn, file=sys.stderr)
    return 0  # 永远非致命


if __name__ == "__main__":
    raise SystemExit(main())
