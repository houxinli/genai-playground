# .cursor

## 作用

Cursor 私有规则目录。Cursor 入口应尽量薄，只负责把任务路由到仓库通用 skill 和文档。

## 直接子项

- `rules/`：Cursor 可加载的 `.mdc` 规则文件。

## 维护规则

- 不在 Cursor rule 内维护第二套业务流程。
- 翻译规则引用 `.agents/skills/translate/` 和 `tasks/translation/docs/executor-instructions.md`。
