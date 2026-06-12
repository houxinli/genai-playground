# 2026-06-12 CI 假绿修复:pytest 统跑与被遗漏的测试

## 背景

Codex review(PR #5)指出 `unittest discover` 只收集 `unittest.TestCase`,
parser/prompt 下 52 个 pytest 风格用例被导入但从未执行;sunday 还有 3 套离线
suite 不在 CI 名单。叠加此前发现的 `scripts/` 缺 `__init__.py`,"基线全绿"
长期高估了覆盖(issue #15)。

## 改动

- CI 与 pre-push 的 translation 套件改为 `python -m pytest tasks/translation/src -q`,
  基线 59 → **110**。
- sunday CI/hook 补 `collectors.amc_test`、`collectors.fandango_test`、
  `ratings.tests.rottentomatoes_fetcher_test`。
- `install-git-hooks.sh` 用 `git rev-parse --git-path hooks`,worktree/submodule 可安装。
- AGENTS.md/PROJECT_STATUS 基线命令与数字更新。

## 被新覆盖暴露并顺手修复的真 bug

1. `builder_test.py` 两处断言措辞过时(enhancement preface 资产已改版、行号接续 few-shot
   是契约),按现行为更新——该测试从未运行过,无人发现。
2. `collectors/amc.py`:`button.get_text(strip=True)` 把嵌套 `<span>IMAX</span>` 并入
   时间文本导致解析失败、场次静默丢失;改为只取直接文本节点(amc_test 两用例由此转绿)。

## 教训

测试"被收集"≠"被执行"。新增测试后必须确认计数上升;讨论基线永远引用具体数字。
