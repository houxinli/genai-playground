# 2026-06-12 task bootstrap 命令(首个 dogfood 任务收官)

## 背景

harness 协议落地后,创建任务仍需手工抄模板写 `state.json`,易留占位值、易违反
"同 branch 唯一活动任务"不变量。gh-9(issue #9)作为首个全程按协议推进的任务,
交付 bootstrap 命令把生命周期 §9 的 3-5 步自动化。

## 改动

- `scripts/bootstrap_agent_task.py` + 6 测试;`make agent-bootstrap`;CI 接入。
- 拒绝路径保证零写入:非法 task_id、目录已存在、同 branch 已有活动任务、写后校验失败均回滚。
- `AGENT_WORKFLOW.md` §9 与 `agent/README.md` 改用命令。

## 验证

13 个 harness 测试全绿;真仓库上对活动 branch 重复 bootstrap 被拒且 `agent/tasks` 零新增(PR #12)。

## 后续

- dogfood 复盘(协议 §13.6):state 字段粒度本轮够用;摩擦点是 checkpoint 手写 JSON 仍繁琐,
  可考虑后续加 `agent-checkpoint` 命令,暂不立项。
- `next_task` 已指向 #10(存量内容盘点),可用本命令直接 bootstrap。
