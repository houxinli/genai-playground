# .agents

## 作用

仓库内通用 Agent 资产目录。这里放跨 Codex、Claude Code、Cursor 等 harness 复用的技能与执行说明。

## 直接子项

- `skills/`：仓库级通用技能目录；业务规则应优先放在这里，而不是复制到各 harness 私有目录。

## 维护规则

- 通用规则放 `.agents/skills/`。
- Harness 私有目录只保留薄触发入口，避免规则漂移。
