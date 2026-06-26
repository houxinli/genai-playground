# .agents/skills

## 作用

存放仓库通用 Agent skill。每个子目录是一项可被不同本地开发 harness 复用的能力。

## 直接子项

- `translate/`：统一 TSV 翻译执行 skill；Codex、Claude Code、Cursor 都应引用这套规则。

## 维护规则

- 新 skill 使用独立子目录和 `SKILL.md`。
- 不在 harness 私有目录复制业务规则。
