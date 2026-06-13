# 2026-06-13 翻译执行器 harness(共享 instruction pack + 自然语言适配)

## 背景

"本地 agent"经澄清=编码 agent(Claude Code/Cursor/Codex)当执行器,自然语言触发(非 make 命令)。
执行器需要一份 agent 中立的指令真相源 + 各 agent 薄适配(issue #57)。

## 改动

- `tasks/translation/docs/executor-instructions.md`:**单一真相源**——角色、job bundle 结构、翻译规则
  (复用现有 preface:逐行对照/禁止省略/引号「」/假名残留/不照抄原文)、result.json 格式
  (task_digest/source_hash 原样回填)、import 步骤、拒译时留空不造假。
- `.claude/skills/translate-job/SKILL.md`:Claude Code 薄 skill,自然语言 description 自动触发,正文指向
  instruction pack,不重复规则。
- `.cursor/rules/translate-job.mdc`:Cursor 适配(NSFW+Grok 路线),指向同一 pack。
- `make translate-bundle SOURCE/PROVIDER/DOCUMENT/OUT`:源目录→revision→job bundle 一步(包装
  source_adapter+export_job)。
- `.claude/settings.local.json` 加入 .gitignore。

## 验证

pytest 全量 187 绿(基线 186→187)。真实 SFW 作品(pixiv:18330282:27466576,310 段)
`make translate-bundle` 跑通;此前 SFW spike 已验 export→翻→import→eval 端到端 6/6 pass。

## 怎么用

- **SFW(Claude Code)**:对我说"用 translate-job 翻 pixiv:18330282:27466576",skill 自动触发,我按 pack 翻、import。
- **NSFW(Cursor+Grok)**:在 Cursor 里走 `.cursor/rules/translate-job.mdc`,Grok 按同一 pack 翻、import。
- 产出的 candidate 后续由 #50 保守择优、#52/#54 store 组织。
