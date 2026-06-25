# Repository Guidelines

这份文档是本仓库开发规范的真相源。当前状态、近期工作另见
[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)；翻译目标架构见
[`tasks/translation/docs/system-design.md`](tasks/translation/docs/system-design.md)；稳定背景与排障见
[`docs/AGENT_CONTEXT.md`](docs/AGENT_CONTEXT.md)；跨 Codex/Claude Code/Cursor 的继续与交接协议见
[`docs/AGENT_WORKFLOW.md`](docs/AGENT_WORKFLOW.md)。

所有 Agent 与用户交流默认使用中文；代码、标识符与 commit message 遵循 §3 与 §10 的既有约定。

## 1. 项目结构与边界

- 顶层用 Conda `llm` 环境，由 `environment-llm.yml` / `environment-llm-mac.yml` 定义。
- 所有可执行入口走 `Makefile` 与 `scripts/` 下的管理脚本（`manage_vllm.sh`、`manage_translation.sh`、`monitor_translation.sh`），不要直接调底层 Python。
- 文档真相源：
  - `docs/PROJECT_STATUS.md` — 当前重点、组件状态、计划（短半衰期）
  - `tasks/translation/docs/system-design.md` — 翻译目标架构、数据模型、Agent 协议与迁移路线
  - `docs/AGENT_WORKFLOW.md` — 跨开发 Agent 的任务状态、继续、交接和 context management
  - `docs/AGENT_CONTEXT.md` — 稳定背景与运行环境（长半衰期）
  - `docs/journal/README.md` — 历史决策与排障日志（只增不改）
- 翻译子系统目录约定（`tasks/translation/`）：
  - `src/core/` — 流水线、translator、quality_checker、qa_gate、repairer、run_state、prompt、parser 等核心
  - `src/cli/` — argparse 入口、参数校验
  - `src/utils/` — `text/` `file/` `format/` `validation/` 等纯工具，无副作用
  - `src/scripts/` — 与主流水线强耦合的可执行脚本（`extract_chinese`, `cleanup_bilingual`, `batch_download_v1` 等）
  - `scripts/` — 与主流水线松耦合的离线脚本（Fanbox 下载、人名规则、繁简转换、修复脚本）
  - `config/presets.json` — CLI 预设；`profiles.default.json` — 采样参数
  - `data/` — 数据与提示资产（git-ignored 大文件）
  - `logs/` — 运行日志与 `translation_state.json`

新增脚本前先决定它属于上面哪一个目录，不要再制造平行目录。

## 2. 构建、测试与开发命令

- 准入：`conda activate llm`，或在命令前加 `conda run -n llm ...`。
- vLLM 生命周期：`make vllm-start[-bg]` / `make vllm-status` / `make vllm-logs` / `make vllm-stop`。切模型或切分支前先 `vllm-stop`。
- 翻译批量：`make translate-batch INPUT_DIR=...`、`make translate-batch-bg`；细粒度调试见 `python tasks/translation/src/translate.py --help`。
- 测试基线（必跑）：
  ```bash
  conda run -n llm python -m pytest tasks/translation/src -q
  ```
  当前 baseline 是 379 测试全绿，PR 合入前必须保持 ≥ 此基线。**此处是基线数字的唯一来源**
  （`make docs-drift` 在 CI 强制它 == 实际 `pytest --collect-only` 计数；改动测试数必须同 PR 更新这里）。
  （必须用 pytest 统跑：`unittest discover` 不执行 parser/prompt 下的 pytest 风格用例，会假绿。）

## 3. 编码风格

- Python 4 空格缩进；模块、变量、文件用 `snake_case`；类名 `CamelCase`；Make 目标 `kebab-case`。
- 公开函数加类型注解；多步骤函数附简短 docstring；行宽 ≈120 字符。
- 默认不写注释。只在 *为什么* 不直观、藏着隐性约束、有引用过的 bug workaround 时写一行。
- 不要 paraphrase 代码做的事（命名要承担这个职责）。不要在注释里写"为 X 任务添加"或"调用方 Y 用"，这种信息属于 commit message 或 PR。
- 格式化工具 `black` / `ruff format` 可选；只对你改过的文件跑，并提交格式化产生的 diff。
- 不要写"恢复/兼容/未来扩展"的占位代码（feature flag、未实装方法、旧字段 alias）。要么删，要么完整实装。

## 4. 配置与参数分层

| 层 | 文件 | 职责 |
| --- | --- | --- |
| CLI 预设 | `tasks/translation/config/presets.json` | 命令行快捷组合，可被显式参数覆盖 |
| 采样参数 | `tasks/translation/profiles.default.json` | 按段（yaml/body/bilingual_simple/quality_check）配置温度、top_p 等 |
| 运行时配置 | `src/core/config.py::TranslationConfig` | argparse → 运行时合并视图 |
| Profile 路由 | `src/core/profile_manager.py` | 按用途取采样参数 |
| Preset 加载 | `src/utils/presets.py` | 把 preset 应用到 `argparse.Namespace` |

新增 CLI flag 时：① argparse 默认值 ② `TranslationConfig` 字段 + `from_args` 映射 ③ 必要时在 `presets.json` 落预设。**不要绕过这条链路**直接读 `args.<x>`。

删除 CLI flag 时反向走完：先去 `presets.json`，再去 `TranslationConfig` + `from_args`，最后去 argparse。否则会留下幽灵字段。

## 5. 翻译流水线核心约定

- 生产唯一活路径：`bilingual_simple = True`。所有发布的 preset 都这么配。
- `pipeline.process_task` 按 `TranslationTask.mode` 分发到 `translate` / `repair`；新增模式应建在 task 层，不要再加并行入口。
- 输出状态由 `run_state.TranslationStateStore` 持久化为 `translation_state.json`，状态语义：`missing` / `partial` / `running` / `failed` / `complete`。新功能必须维护这个状态。
- 修复入口统一走 `--repair-existing`（主流水线 + `BilingualRepairer`）。`scripts/repair_bilingual.py` 是历史入口，未来要薄化。
- 名字一致性：人工规则文件优先（`--name-glossary-file`），自动预读保存到 `--name-glossary-output-dir`，正文翻译与人名预读可以走不同 provider（见 `*_openrouter_local_names` preset）。
- Prompt / parser 已经独立成包（`src/core/prompt/`、`src/core/parser/`）；新逻辑放对应包内，不要塞回 `translator.py` 或 `pipeline.py`。
- 上述是当前实现约束。新架构按 `system-design.md` 渐进迁移，不能在现有 TXT/JSON state 之外另起一套未接入主流程的平行状态。
- 目标架构中，JSON 是规范业务工件，SQLite 是可重建索引和调度层；Agent/API 只能创建 candidate/result，不能直接覆盖发布版本。
- **翻译执行器**(编码 Agent 当执行器把 job 翻成 candidate):规则与 `result.json` 格式的单一真相源是
  [`tasks/translation/docs/executor-instructions.md`](tasks/translation/docs/executor-instructions.md)；各 Agent 薄适配
  (`.agents/skills/translate-job` Codex、`.claude/skills/translate-job` Claude Code、`.cursor/rules/translate-job.mdc` Cursor)
  只指向它,不重复规则。NSFW 走 Cursor+Grok。
- 新增 candidate/version/annotation/task schema 时必须带 `schema_version`，并同时补 schema validation、round-trip 和 stale-result 测试。

## 6. 质量检测分工

- `src/core/quality_checker.py` — **在线**重试 gate：单批/单段翻译失败时是否再试一次。默认 `disable_llm_qc=true`，规则 QC 起主要作用。
- `src/core/qa_gate.py` — **离线**硬规则 gate：双语配对、假名残留、拒绝模板、失败标记、人名坏别名等；用 `--qa-report` 在完成后生成报告，用 `--repair-from-qa-report-dir` 把报告喂回 repair。
- `src/utils/validation/` — 纯函数级规则检测器（length / repetition / jp_copy / cjk_punctuation），被上面两层按需引用。
- 新增检测器先决定它是"重试用"还是"放行用"，再选挂载点。**不要再加第三层 QC**。

## 7. 测试约定

- 测试与代码共置，命名 `*_test.py`，使用标准 `unittest`。
- 涵盖正常路径与失败路径；翻译/修复相关测试用 `_FakeTranslator` 桩，不要真打模型。参考 `repairer_test.py`。
- 新加流水线分支必须同时加测试；改动 `pipeline.py` 而不补测试视为不完整。
- 测试数据放 `tasks/translation/data/test/`（git-ignore 友好），失败案例尽量提交 minimal repro。

## 8. 死代码与重复

- 删除分支时同步删它依赖的 helper、CLI flag、config 字段、文档段落（参考 2026-05 那次 enhanced_mode 清理）。
- 不允许新增"另一个 scripts 目录""另一个 repair 入口"等平行链路；先复用 / 改造现有路径。
- 发现孤儿 re-export、被 `getattr(args, 'x', None)` 默认值掩盖的死字段、永远走不到的 `if` 分支时，应顺手删除而不是绕过。

## 9. 日志、状态与可观测性

- 运行日志默认写 `tasks/translation/logs/`，最新一份用 `latest_translation.log` 软链。
- 单次运行的状态写入 `translation_state.json`（顶层目录 + 子目录都有）。排障从这里入手。
- `monitor_translation.sh` 提供 `status / monitor / stats` 三个视角。
- 引入新指标（耗时、token、成本）请扩展 `run_state` 的 `progress` 字段，不要再起新文件。
- 在新 workspace/index 落地前继续遵守上一条；迁移后指标进入统一 events/index，不允许同时维护两个互不一致的指标真相源。

## 10. 分支、checkpoint 与 PR

### 分支模型

- `main` 是唯一集成主干（trunk）。受 CI 守护，保持随时可发布。
- **一事一支一 PR**：每个独立任务从最新的 `main` 切一条短生命周期 topic 分支，命名 `feat/...`、`fix/...`、`refactor/...`、`chore/...`、`docs/...`。合并后删除。
- 切分支前先同步主干：`git fetch origin && git switch main && git pull --ff-only`。
- 不要再用以机器命名的长期"大杂烩"分支把多个子项目的改动堆在一起——那会让 PR 不可评审、回滚粒度过粗。
- 不同子项目（translation / sunday-movies / fitness / ytmusic）的改动应落在各自的 topic 分支与 PR 里，不要混提交。

### checkpoint 纪律

- **每完成一个独立子任务就提交**，不要一个会话攒成一个大提交。一个提交 = 一个能独立描述、能独立回滚的逻辑单元。
- 提交前确保该单元自洽：测试通过、无半成品。失败的步骤不要混进提交。
- 长任务和跨会话进度用 `agent/tasks/<task-id>/state.json` 与 append-only `checkpoints.jsonl`
  跟踪；不要用聊天记忆、journal 或 `PROJECT_STATUS.md` 代替执行游标。
- **每个合并的 PR 配一条 journal**（`docs/journal/YYYY-MM-DD.md` + 索引），记录动机、改动、验证、后续。
- 连续完成 3–5 个同一架构链路 PR 或跨越 Phase 边界时，必须单独做一次
  `system-design` / `PROJECT_STATUS` / GitHub issue reconcile，不能只追加 journal。
- **改契约/schema/架构决策的 PR，必须在同一个 PR 内更新 `system-design.md` 或 `PROJECT_STATUS.md`**——
  设计跟着改它的代码走,不留到批量 reconcile。CI `Design-doc coupling` 步骤强制:改了 `schemas/` 或新增
  `core/*.py` 却没动设计文档会 fail。文档里机械可查的事实(测试基线数字、组件路径)由 `make docs-drift` 在 CI 守护。

### Commit

- 用 Conventional Commits + 子系统 scope：`feat(translation): ...`、`fix(vllm): ...`、`refactor(translation): drop dead code`。
- 标题 ≤ 72 字符；body 写"为什么"。
- 选择性 `git add` 具体文件，不要 `git add -A` 把无关 WIP（如他人未完成的子项目）一起带进来。

### PR

- PR 描述应包含：动机/issue 链接、影响的 Make 目标、验证命令（至少 `python -m pytest tasks/translation/src` + 必要的 `make translate*` 调用）、必要日志或样本输出。
- PR 必须等 CI（`.github/workflows/tests.yml`）通过再合并。
- 翻译流水线 PR 至少由一位熟悉该子系统的 owner 评审。合并保持线性历史。
- 除非用户明确要求，不要 `--no-verify`、`--amend`、`push --force`。
- 本地可装 pre-push hook 在 push 前跑快测试：`bash scripts/install-git-hooks.sh`。

## 11. 跨 Agent 继续与交接

- 用户只说“继续”时，必须按 [`docs/AGENT_WORKFLOW.md`](docs/AGENT_WORKFLOW.md) 恢复当前分支任务：
  先检查 Git，再读取匹配当前 branch 的唯一 active task state、必要 context 和最近 checkpoint。
- 不依赖上一段聊天记录，不从 roadmap 或 journal 猜下一项工作。找不到唯一任务且无法从当前 branch/PR/Issue
  无歧义恢复时，停止并向用户确认。
- 执行前先校准 state 与 Git/文件/测试证据；冲突时以实际证据为准，并记录 reconcile checkpoint。
- 每轮只推进 `next_action` 对应的最小可验收单元。结束前更新 state、验证结果和 `checkpoints.jsonl`。
- 用户说“交接”时，不开始新的大步骤；只完成可运行的验证、更新状态并写清未提交改动和下一动作。
- 同一 branch/worktree 只允许 Codex、Claude Code、Cursor 顺序交替。并行开发必须拆 branch/worktree 和 task state。
- `agent/tasks/` 中一个 branch 最多有一个 `planned` / `active` / `blocked` 任务，一个任务最多一个
  `in_progress` step。
- 创建或更新 task state/checkpoint 后必须运行 `make agent-validate`。

## 12. 给新 Agent 的最小阅读路径

1. 本文件（开发规范）。
2. [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) — 现在在做什么、哪里是缺口。
3. [`docs/AGENT_WORKFLOW.md`](docs/AGENT_WORKFLOW.md) — 收到“继续/交接”或需要跨 harness 工作时必读。
4. [`tasks/translation/docs/system-design.md`](tasks/translation/docs/system-design.md) — 改架构、QA/repair、翻译 Agent 协议或版本模型时必读。
5. [`tasks/translation/README.md`](tasks/translation/README.md) — 怎么把当前翻译跑起来。
6. [`docs/AGENT_CONTEXT.md`](docs/AGENT_CONTEXT.md) — 稳定环境/CUDA/vLLM 背景，遇到具体环境问题时翻。
7. [`docs/journal/README.md`](docs/journal/README.md) — 历史决策，按需检索。

不要“先读 journal 重建上下文”。纯运行任务读 1 → 2 → 5；架构任务读 1 → 2 → 4；
跨 Agent 恢复任务读 1 → 2 → 3，再由 task state 指向其余文件。
