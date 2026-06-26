# .cursor/rules

## 作用

Cursor rule 文件目录，用于给 Cursor 提供最小入口和跨 Agent 工作流提醒。

## 直接子项

- `organize-progress.mdc`：提示 Cursor 使用仓库内 `docs/AGENT_WORKFLOW.md`，不要自建进度流程。
- `translate.mdc`：提示 Cursor 使用统一 translate skill 执行翻译。

## 维护规则

- Rule 只做路由和约束提醒。
- 详细业务规则放在仓库通用文档或 `.agents/skills/`。
