# 2026-06-13 文档漂移 CI 闸门

## 背景

本会话反复出现同一元模式:靠人记的纪律(跑全套测试、读 review、reconcile 文档)在高速迭代下衰减。
每次真正止住的修复都是把规则变成机械闸门(CI、validator、checklist)。文档滞后(PROJECT_STATUS 写
149/186 而实际 186/188)是同一类——本任务把它也变成闸门(issue #59)。

## 改动

- `scripts/check_docs_drift.py`(+6 测试):① AGENTS.md 测试基线数字 == 实际 `pytest --collect-only` 计数;
  ② PROJECT_STATUS「Component Status」的 backtick 文件路径必须存在(跳过 glob/占位符/CLI 示例,双根解析)。
- `make docs-drift`;CI 跑 docs-drift + check_docs_drift_test。
- **PR 设计耦合**(CI step):PR 改了 `schemas/` 或新增 `core/*.py` 却没动 system-design/PROJECT_STATUS → fail。
- **去重**:测试基线数字只留 AGENTS.md 一处,PROJECT_STATUS 指向它。
- AGENTS §10 / PR 模板:写明"改契约/schema/架构的 PR 必须同 PR 更新设计文档"。
- 顺手修正 186→188 的现存滞后。

## 验证

make docs-drift 通过;故意改错基线/删引用路径都能 fail;全量 188 绿;check_docs_drift_test 6 绿。

## 元教训

纪律性规则在速度下必然衰减;能机械校验的事实就交给 CI 闸门,设计跟着改它的代码同 PR 走,不留批量 reconcile。
