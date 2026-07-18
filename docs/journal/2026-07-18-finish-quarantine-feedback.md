# Finish 隔离状态显式失败

## 背景

修复存量译文时，原 job 与 finish 使用了不同的实体上下文。stale 防护正确隔离了 result，
但 CLI 只显示 `published: 0, errors: 0` 并返回成功，容易让人误判为择优策略保留了旧版本。

## 改动

- finish 摘要分别统计 quarantine、unresolved 和 document QA failure。
- 这些阻断状态使命令返回非零，并输出含具体原因的完整文档报告。
- quarantine 报告给出可执行的下一步：让 SOURCE、ENTITY_STORE 与 prepare 保持一致。
- translate skill 同步记录该约束，禁止通过手改 result/ref 绕过 stale 防护。

## 验证

- 用 `pixiv:104039620:27543152` 的真实旧 job 复现上下文不一致，命令显示
  `quarantined: 1`、digest mismatch 和 `next_action`，并返回非零。
- 使用原 job 的空实体上下文重跑后正常发布，translate verify 通过，study 随当前译文重渲染。
- `conda run -n llm python -m pytest tasks/translation/src -q`（476 passed）
- `make docs-drift`
- `git diff --check`

## 关联

- Issue #190
- Campaign #185

