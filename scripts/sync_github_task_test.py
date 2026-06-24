#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_github_task:mock gh runner 验证挂/摘标签、评论、失败降级、摘要生成。"""

import importlib.util
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPOSITORY_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNC = _load("sync_github_task")


def _recording_runner(results=None):
    """记录被调用的 gh 命令;results 按调用序给 (ok, out),缺省成功。"""
    calls = []
    results = list(results or [])

    def runner(cmd):
        calls.append(cmd)
        return results.pop(0) if results else (True, "")

    runner.calls = calls
    return runner


class SyncBootstrapTest(unittest.TestCase):
    def test_adds_active_label(self):
        r = _recording_runner()
        self.assertIsNone(SYNC.sync_bootstrap(34, runner=r))
        self.assertEqual([["gh", "issue", "edit", "34", "--add-label", "agent-active"]], r.calls)

    def test_failure_is_non_fatal_warning(self):
        r = _recording_runner([(False, "no auth")])
        warn = SYNC.sync_bootstrap(34, runner=r)
        self.assertIsNotNone(warn)
        self.assertIn("agent-active", warn)

    def test_runner_exception_degrades(self):
        def boom(cmd):
            raise RuntimeError("gh missing")
        self.assertIsNotNone(SYNC.sync_bootstrap(34, runner=boom))  # 不抛


class SyncCompleteTest(unittest.TestCase):
    def test_removes_label_and_comments(self):
        r = _recording_runner()
        self.assertIsNone(SYNC.sync_complete(34, "摘要", runner=r))
        self.assertEqual(["gh", "issue", "edit", "34", "--remove-label", "agent-active"], r.calls[0])
        self.assertEqual(["gh", "issue", "comment", "34", "--body", "摘要"], r.calls[1])

    def test_partial_failure_reports_but_non_fatal(self):
        r = _recording_runner([(True, ""), (False, "comment denied")])  # 摘标签成功、评论失败
        warn = SYNC.sync_complete(34, "摘要", runner=r)
        self.assertIsNotNone(warn)
        self.assertIn("评论失败", warn)


class SummaryTest(unittest.TestCase):
    def test_summary_includes_validation_and_pr(self):
        state = {
            "task_id": "gh-x", "github": {"issue": 34, "pull_request": 99},
            "validation": {"last_results": [{"command": "pytest", "status": "passed", "summary": "337 passed"}]},
        }
        s = SYNC.summary_from_state(state)
        self.assertIn("gh-x", s)
        self.assertIn("337 passed", s)
        self.assertIn("PR #99", s)


if __name__ == "__main__":
    unittest.main()
