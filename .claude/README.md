# .claude

## 作用

Claude Code 私有配置和薄 skill 入口目录。通用规则不应在这里维护第二份。

## 直接子项

- `settings.local.json`：本机 Claude Code 配置，可能包含本地偏好。
- `skills/`：Claude Code 可发现的薄 skill 入口。

## 维护规则

- 业务规则迁移到 `.agents/skills/`。
- 本目录只保留 Claude Code 需要的适配层。
