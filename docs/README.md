# Docs Index

## 主要文档

- 开发规范：[`../AGENTS.md`](../AGENTS.md) — 编码、目录、配置分层、测试、commit/PR 规则
- 当前状态与路线图：[`PROJECT_STATUS.md`](PROJECT_STATUS.md)
- 跨 Agent 开发工作流：[`AGENT_WORKFLOW.md`](AGENT_WORKFLOW.md) — Codex/Claude Code/Cursor 的继续、交接与状态协议
- 翻译系统目标设计：[`../tasks/translation/docs/system-design.md`](../tasks/translation/docs/system-design.md)
- 稳定背景（环境/排障）：[`AGENT_CONTEXT.md`](AGENT_CONTEXT.md)
- Journal 索引：[`journal/README.md`](journal/README.md)
- 翻译任务主文档：[`../tasks/translation/README.md`](../tasks/translation/README.md)
- 翻译脚本说明：[`../tasks/translation/scripts/README.md`](../tasks/translation/scripts/README.md)

## 使用建议

- **新 agent / 新对话**：按 `AGENTS.md` → `PROJECT_STATUS.md` → 子系统设计/README 的顺序读，
  环境问题再翻 `AGENT_CONTEXT.md`。
- **Codex / Claude Code / Cursor 交替开发**：读 `AGENT_WORKFLOW.md`，然后用同一条“继续”恢复当前任务。
- **准备改翻译架构或数据模型**：必须先读 `tasks/translation/docs/system-design.md`。
- **想直接跑翻译管线**：先读 `tasks/translation/README.md`。
- **想查历史决策与问题**：从 `journal/README.md` 进入。
- **想看脚本级命令**：读 `tasks/translation/scripts/README.md`。
