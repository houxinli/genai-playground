# 2026-06-12 harness 强化:完成性校验与 review triage

## 背景

Codex review(PR #6)指出 validator 三个洞:in_progress 步骤可越过未完成依赖、
complete 任务不核对验证结果、complete 可无最终 checkpoint。gh-10 实测佐证:
bootstrap 默认 required_commands 为空,一路空着跑完无人拦。另:本轮发现 9 个 PR
的 21 条 Codex 意见全部未读即合并——协议缺 review triage 步骤(issue #14)。

## 改动

- validator 新增三条:in_progress 依赖须 completed/skipped;complete 须
  required_commands 非空且每条最新结果 passed;complete 须有最终 checkpoint。+5 测试。
- bootstrap 默认 required_commands(agent-validate),可用 --required-command 覆盖。
- AGENT_WORKFLOW §9 完成条件加入 review triage(修复/回复/转 issue 三选一);
  PR 模板 Handoff 增加对应勾选项。
- reconcile:gh-10 补记实际已跑的两条 required_commands。

## 验证

18 个 harness 测试全绿;新规则对真实仓库先红(逮到 gh-10)后绿(reconcile 后)。
新流程在 PR #22 首跑即生效:Codex 在修复本身中发现 --git-path 相对路径 P2,
修复+实测+回复后才合并。
