# .claude/skills

## 作用

Claude Code skill 入口目录。当前主要用于兼容旧入口或 Claude 专用薄包装。

## 直接子项

- `extract-names/`：历史人名抽取 skill。
- `translate`：历史翻译入口文件；通用翻译规则已收敛到 `.agents/skills/translate/`。

## 维护规则

- 新翻译规则不要加在这里。
- 需要 Claude 专用行为时，只写最小触发说明并引用 `.agents/skills/`。
