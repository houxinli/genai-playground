# Shared Agent State

本目录保存 Codex、Claude Code、Cursor 共用的分支级开发任务状态。

协议见 [`../docs/AGENT_WORKFLOW.md`](../docs/AGENT_WORKFLOW.md)。

约定：

- 每个活动 branch 最多一个 `agent/tasks/<task-id>/state.json`。
- `state.json` 是当前执行游标。
- `checkpoints.jsonl` 是 append-only 交接日志。
- state 的 `last_checkpoint.checkpoint_id` 必须指向日志最后一条有效 checkpoint。
- checkpoint 记录写入时观察到的 branch/HEAD，以及任务内和无关的未提交文件。
- 状态文件纳入 Git，以支持跨机器和跨 harness 恢复。
- 不存 secret、私有翻译语料、完整命令日志或聊天记录。
- 不要直接复用模板中的 placeholder 值。

验证：

```bash
make agent-validate
make agent-validator-test
```
