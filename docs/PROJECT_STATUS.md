# Project Status

> 当前项目状态、组件健康度和开发计划的真相源。
> 新的 agent / 新的对话优先读这份文档，再进入具体子系统文档。

**最后更新**: 2026-06-12

## Start Here

建议按下面顺序建立上下文：

1. [`../README.md`](../README.md)
2. [`PROJECT_STATUS.md`](PROJECT_STATUS.md)
3. [`AGENT_WORKFLOW.md`](AGENT_WORKFLOW.md)（跨 Agent 继续/交接时）
4. [`AGENT_CONTEXT.md`](AGENT_CONTEXT.md)
5. [`../tasks/translation/docs/system-design.md`](../tasks/translation/docs/system-design.md)
6. [`../tasks/translation/README.md`](../tasks/translation/README.md)
7. [`journal/README.md`](journal/README.md)

## Repository Snapshot

- 当前主战场是 `tasks/translation`。
- `tasks/sunday-movies` 仍在仓库内，但当前处于维护模式，不是近期主要开发方向。
- 常用运行环境是 `conda` 的 `llm` 环境。
- 当前生产路径仍是“下载 -> 翻译 -> 修复/清理 -> 打包”。
- 下一阶段的架构目标已收敛为：JSON 规范工件 + 可重建 SQLite 索引、segment 多候选版本、
  API/Agent 双执行路线、用户 annotation 与非破坏性 repair。
- 开发侧已定义 Codex/Claude Code/Cursor 共用的 branch-level task state 与 append-only checkpoint 协议。

## Current Focus

当前目标是先建立新的文档/segment/candidate/version 基础，再在其上实现 QA 闭环、Agent harness、
跨文本一致性、并发调度和用户 review。完整目标设计见
[`tasks/translation/docs/system-design.md`](../tasks/translation/docs/system-design.md)。

开发任务本身的跨会话上下文由 [`AGENT_WORKFLOW.md`](AGENT_WORKFLOW.md) 和 `agent/tasks/` 管理；
它与翻译业务的 Agent job/result 协议是两层不同系统，不能共用状态文件。

设计原则：

- JSON 保存不可变、可移植、可审阅的业务工件。
- SQLite/WAL 只承担可重建索引、review queue、worker lease 和运行指标。
- API、本地模型、Codex、Claude Code、Cursor 和人工编辑统一生产 candidate，不直接覆盖发布物。
- bilingual/zh 是由确定版本渲染的派生产物，不再兼任 checkpoint 和修复数据库。
- repair 只生成新 candidate；只有 QA 与选择策略确认改善后才进入新版本。

## Component Status

| 组件 | 状态 | 说明 | 主要入口 |
| --- | --- | --- | --- |
| Pixiv 下载 | 可用 | 终端链路可用，数据落到 `tasks/translation/data/pixiv/<USER_ID>/` | `tasks/translation/src/scripts/batch_download_v1.py` |
| Fanbox 下载 | 可用 | 浏览器脚本优先，终端链路依赖登录态 | `tasks/translation/scripts/fanbox_browser_downloader.js` |
| 主翻译流水线 | 可用 | 支持 `*_bilingual/`、`*_zh/` 输出；已支持 partial/failed/running/complete 判定，并可在完成后生成 QA 报告 | `tasks/translation/src/core/pipeline.py` |
| 输出状态持久化 | 新增完成 | 运行状态记录在配置的 `log_dir` 下的 `translation_state.json` | `tasks/translation/src/core/run_state.py` |
| 修复流程 | 可用 | 标准 repair 已支持经由 `src/translate.py --repair-existing` 进入主流水线；可注入人名规则，也可读取 QA 报告优先修复问题行 | `tasks/translation/src/translate.py` |
| 打包/提取中文 | 可用 | 已补 `.meta.json` / `index.json` 元数据回退 | `tasks/translation/src/scripts/extract_chinese.py` |
| 质量检测 | 可用 | 规则 QC + LLM QC 可工作；新增硬规则 QA gate，可检查双语配对、假名残留、拒绝模板、失败标记和人名坏别名 | `tasks/translation/src/core/qa_gate.py` |
| 人名一致性 | 可用 | 支持人工规则优先、自动预读候选保存、正文 OpenRouter + 本地 vLLM/MLX 抽名的分离运行时 | `tasks/translation/src/core/translator.py` |
| Preset 体系 | 基本可用 | 已新增 OpenRouter 正文翻译 + 本地人名预读 preset；来源拆分仍需继续完善 | `tasks/translation/config/presets.json` |
| 目标系统设计 | 已完成设计 | 已定义 JSON/SQLite 边界、candidate/version、API/Agent 协议、用户 annotation、跨文本知识与迁移顺序；尚未实现 | `tasks/translation/docs/system-design.md` |
| 开发 Agent 连续性 | 基础已落地 | 协议、Schema、validator、CI、GitHub 模板与 `make agent-bootstrap` 已实现；GitHub 状态同步待实现 | `docs/AGENT_WORKFLOW.md` |
| 存量内容盘点/QA 基线 | 已完成 | `inventory_content.py` 全库清单 + `qa_baseline.py` 硬规则基线（v2 含打包产物与截断检查）；1048 单元中 894 个含 error（v2.1 打包按章拆分），坏产物已隔离 | `tasks/translation/src/scripts/inventory_content.py` |
| 多候选与版本 | 未实现 | 当前仍以单份 bilingual/fixed 文件作为主要结果 | 目标见系统设计 |
| 翻译 Agent harness | 未实现 | 尚无统一翻译 task/result job export/import 协议 | 目标见系统设计 |
| 用户句级反馈 | 未实现 | 尚不能持久化“某句话有问题”并触发定向修复 | 目标见系统设计 |
| 跨文本知识库 | 未实现 | 当前主要依赖人工规则文件和单篇自动预读 | 目标见系统设计 |
| 并发调度 | 缺口明显 | 当前仍主要依赖手工并行，没有内建 worker 调度器 | `tasks/translation/src/core/pipeline.py` |
| 测试 | 基线健康 | pytest 统跑当前为 110 个测试全绿（unittest discover 会漏 pytest 风格用例） | `tasks/translation/src/**/*_test.py` |
| Sunday Movies | 维护模式 | 仓库中保留，但当前不作为近期规划重点 | `tasks/sunday-movies/` |

## Recent Engineering Changes

2026-06-12 主干收敛与首个 dogfood 任务（详见 [journal](journal/2026-06-12-trunk-split.md)）：

- 长期混合分支的 21 个未合并提交按子项目拆为 #3/#4/#5，rebase 线性合入 main，树等价验证无损。
- harness 经 #6 合入；#7 系统设计文档；#8 fitness 入库；旧分支删除，仓库收敛到唯一 `main`。
- 首个 dogfood 任务 `gh-9-agent-bootstrap`（issue #9）已按协议 bootstrap；存量盘点进入 backlog（#10）。

2026-06-12 跨 Agent 开发连续性：

- 增加 `agent/tasks/<task-id>/state.json` 与 append-only `checkpoints.jsonl` 的共享协议。
- 固定“继续”“交接”的恢复、校准、执行、验证和 checkpoint 语义。
- 为 task state 与 checkpoint 增加 JSON Schema 和模板。
- 增加 schema/跨文件不变量 validator、单元测试、Make 目标与 CI gate。
- 增加 Agent task Issue 和 PR handoff 模板。
- Codex、Claude Code、Cursor 共用仓库内状态，不依赖各自聊天历史。

2026-06-12 目标系统设计：

- 确定 JSON canonical artifacts + SQLite operational index 的双层存储边界。
- 确定 `DocumentRevision -> Segment -> Candidate -> Evaluation -> DocumentVersion -> Render` 数据链。
- 确定 API 与 Agent harness 共用 task/result JSON 协议。
- 确定单篇/跨文本实体一致性、用户 annotation 和非破坏性 repair 的目标模型。
- 制定从当前 bilingual 文件流水线到目标系统的七阶段迁移路线。

2026-06-02 非破坏性 repair：

- repair 重译失败时不再用占位符覆盖已有非空译文。
- 新增 6 个非破坏性 repair 测试，基线从 44 提升为 50。

2026-05-20 死代码清理与开发规范收敛：

- 删除 `enhanced_mode` 整条链路（`enhanced_mode.py`、`rule_detector.py`、CLI flag、config 字段、pipeline/file_handler 分支），生产路径一直走 `bilingual_simple`，该模式无 caller。
- 删除 `Translator.translate_text` / `_translate_with_stream` / `_build_messages` 死分支（引用了不存在的 `config.bilingual`）；非 `bilingual_simple` 路径统一走 `translate_body_text`。
- 删除 `utils/validation` 下孤儿校验器 `quality_validator` / `content_validator`。
- 净删除约 1557 行；当时测试基线保持 44 全绿。
- 开发规范收敛到 [`../AGENTS.md`](../AGENTS.md)；[`AGENT_CONTEXT.md`](AGENT_CONTEXT.md) 瘦身为稳定背景。

历史轮次（状态固化与 QA gate）已落地的关键改动：

- 新增 [`../tasks/translation/src/core/run_state.py`](../tasks/translation/src/core/run_state.py)，持久化 run/file 级状态。
- [`../tasks/translation/src/core/file_handler.py`](../tasks/translation/src/core/file_handler.py) 和 [`../tasks/translation/src/core/pipeline.py`](../tasks/translation/src/core/pipeline.py) 已统一输出路径语义，并识别 `missing/partial/running/failed/complete`。
- 修复流程已并回主入口：`translate.py --repair-existing` 可直接修复已有 bilingual 输出，并写入 `*_bilingual_fixed/`。
- [`../tasks/translation/src/scripts/extract_chinese.py`](../tasks/translation/src/scripts/extract_chinese.py) 已支持从源目录结构化元数据回退标题、ID、时间戳。
- [`../tasks/translation/src/core/quality_checker.py`](../tasks/translation/src/core/quality_checker.py) 修正了 `bilingual` 参数链路，避免运行时 `TypeError`。
- 新增 [`../tasks/translation/src/core/qa_gate.py`](../tasks/translation/src/core/qa_gate.py)，支持 `--qa-report` 跟随翻译/修复生成硬规则报告，也支持 `--qa-only` 检查已有输出；repair 可通过 `--repair-from-qa-report-dir` 消费 QA 报告中的问题行。
- 人名预读运行时已可独立配置：本地模型只做人名候选抽取，正文翻译仍可走 OpenRouter。
- [`../tasks/translation/config/presets.json`](../tasks/translation/config/presets.json) 新增 `fanbox_openrouter_local_names` 和 `pixiv_openrouter_local_names`。
- 已补回归测试：
  - [`../tasks/translation/src/core/file_handler_test.py`](../tasks/translation/src/core/file_handler_test.py)
  - [`../tasks/translation/src/core/pipeline_repair_test.py`](../tasks/translation/src/core/pipeline_repair_test.py)
  - [`../tasks/translation/src/core/repairer_test.py`](../tasks/translation/src/core/repairer_test.py)
  - [`../tasks/translation/src/scripts/extract_chinese_test.py`](../tasks/translation/src/scripts/extract_chinese_test.py)
  - [`../tasks/translation/src/core/quality_checker_qc_format_test.py`](../tasks/translation/src/core/quality_checker_qc_format_test.py)
  - [`../tasks/translation/src/core/quality_checker_test.py`](../tasks/translation/src/core/quality_checker_test.py)
  - [`../tasks/translation/src/core/qa_gate_test.py`](../tasks/translation/src/core/qa_gate_test.py)

## Known Gaps

- 当前没有规范化 `Document/Segment`，候选、QA、repair 和用户反馈只能围绕双语 TXT 工作。
- 当前没有 candidate/version 模型，实验结果依赖多个目录名保存，难以比较、回滚和审计。
- 当前没有统一 API/Agent job 协议，Codex/Claude Code/Cursor 无法可靠参与批量 review。
- 开发任务的跨 Agent 协议还没有 GitHub 状态同步（bootstrap 命令已完成，#9）。
- 存量 QA 基线 v2.1（2026-06-12，含顶层打包产物按章拆分与 missing_pair 检查）：
  1048 个单元（逐篇文件 + 打包章节）中 894 个含 error 级问题（kana 8757、
  same_as_source 5596、refusal 738、failure 501、empty 112；missing_pair 为 0——无结构性截断）。
  逐条修复依赖 P1 的 candidate/repair 闭环；报告见 `logs/inventory/qa_baseline.json`。
- 当前没有用户 annotation 生命周期和句级定向重译入口。
- 人名规则尚未实体化、作用域化和版本化，同名跨系列冲突仍需人工避免。
- 还没有内建的文件级并发调度器，批量任务提速仍依赖外部手动拆分。
- metadata 翻译、preset 选择、来源差异目前仍然耦合得不够清晰。
- 打包已经有元数据回退，但还没有完全摆脱对译后 YAML 的依赖。
- QA gate 已能把问题行交给 repair，但完整自动多轮闭环仍未实现。
- 成本、耗时、重试率等运行指标还没形成统一报表。

## Development Plan

> 可调整层在 GitHub:[Roadmap 看板](https://github.com/users/houxinli/projects/1)
> (P0 余项为 issue + `agent-ready`,P1–P3 为阶段占位卡;手机 App 可直接拖卡/改字段/建 issue)。
> 本节是阶段快照,由 Agent 在"整理进展"时与看板对齐,不在手机上直接编辑。

### P0: 协议与数据基础

1. ~~存量内容库盘点、QA 基线与坏产物隔离~~（#10，已完成 2026-06-12：`inventory_content.py` +
   `qa_baseline.py`，3 个坏产物目录已隔离并记录 manifest）。
2. 为 `agent/tasks` 增加 GitHub 状态同步（bootstrap 命令已完成，#9）。
3. 固定 revision、candidate、evaluation、annotation、version、task、result 的 JSON Schema。
4. 建立 Pixiv/Fanbox 最小 fixture、golden bilingual/zh 和 ID/hash 稳定性测试。
5. 建立 source adapter、`DocumentRevision/Segment` 和 renderer 的 shadow path。
6. 支持把现有 bilingual/fixed 文件导入为 legacy candidate，确保迁移不丢历史（以 1 的清单为输入）。

### P1: 多候选、版本与非破坏性闭环

1. 翻译结果按 segment 创建 candidate，不覆盖历史。
2. 用 `DocumentVersion` 保存 selection manifest，并从版本渲染 bilingual/zh。
3. QA finding 绑定 candidate + segment。
4. repair 创建新 candidate，完成 QA -> compare -> select 闭环。
5. 建立 CLI 级 candidate 比较、选择、回滚和用户 annotation。

### P2: API/Agent 双执行路线与知识一致性

1. 实现统一 task/result 协议和 `export-job` / `validate-result` / `import-result`。
2. 为 Codex、Claude Code、Cursor 提供由同一 instruction pack 派生的薄适配。
3. 建立 scoped entity store、knowledge snapshot、entity linking review 和规则影响分析。
4. 将现有人工 name map 迁移为 locked entity translations，自动预读只进入 candidate。

### P3: 调度、并发与体验

1. 增加可重建 SQLite/WAL 索引、review queue、worker lease 和 heartbeat。
2. 做文件级 `--workers N`、runtime 限速、失败重试和 token-aware batching。
3. 监控改为查询结构化状态与指标，不再解析日志文案。
4. candidate/version/annotation 稳定后，再实现 TUI 或 Web review 界面。

### 文档维护规则

- 只要“当前重点、组件状态、近期计划”发生了实质变化，就更新本文件。
- 稳定目标架构更新到 `tasks/translation/docs/system-design.md`，不要把完整设计复制回本文件。
- 只要有值得回溯的阶段性决策或问题处理，就新增一篇 journal 条目并在索引登记。
- `AGENT_CONTEXT.md` 保持偏稳定背景；不要再把短期任务清单长期堆在里面。

## Validation Baseline

当前推荐的基础验证命令：

```bash
conda run -n llm python -m pytest tasks/translation/src -q
```

如果只想回归本轮新增的关键测试：

```bash
conda run -n llm python -m unittest tasks.translation.src.core.file_handler_test
conda run -n llm python -m unittest tasks.translation.src.core.pipeline_repair_test
conda run -n llm python -m unittest tasks.translation.src.core.repairer_test
conda run -n llm python -m unittest tasks.translation.src.scripts.extract_chinese_test
conda run -n llm python -m unittest tasks.translation.src.core.quality_checker_test
conda run -n llm python -m unittest tasks.translation.src.core.quality_checker_qc_format_test
```
