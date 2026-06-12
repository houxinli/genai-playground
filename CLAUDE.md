# CLAUDE.md

开发规范的真相源是 [`AGENTS.md`](AGENTS.md)（Claude Code 与 Codex 都会读取本文件，这里只做指针，避免规范分裂为两份）。

进入任何任务前，按 `AGENTS.md` §12 的顺序建立上下文。

当用户只说“继续”或“交接”时，必须执行 [`docs/AGENT_WORKFLOW.md`](docs/AGENT_WORKFLOW.md)：
用当前 branch 匹配 `agent/tasks/*/state.json`，核对 Git 与最近 checkpoint，推进或交接唯一 `next_action`，
并在结束前更新 state/checkpoint。不要依赖 Claude Code 的聊天历史猜测进度。
