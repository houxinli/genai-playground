# Project Status

> 当前项目状态、组件健康度和开发计划的真相源。
> 新的 agent / 新的对话优先读这份文档，再进入具体子系统文档。

**最后更新**: 2026-06-13

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
- Schema、DocumentRevision/Segment、candidate 导入、translate Task/Result 往返和 candidate QA
  已进入主干；下一步是把候选安全地变成可审计 `DocumentVersion`。
- 开发侧已定义 Codex/Claude Code/Cursor 共用的 branch-level task state 与 append-only checkpoint 协议。

## Current Focus

当前目标从“继续补协议”转为“完成第一个安全 vertical slice”：

```text
source -> revision -> legacy/new candidates -> evaluations
       -> conservative recommendation -> draft version -> bilingual/zh
```

该数据平面 slice（身份→store→版本→保守选择→bilingual/zh）已完成。**下一步(2026-06-19 重排)：
Knowledge/context-builder 层 #83 P1a**——最小 context-builder 让 bundle 携带 Context Pack(术语+
作用域实体+邻句),它是翻译质量(人名一致性)的真正来源、harness 路径当前缺的上下文载体,且端到端
demo 须带上下文才有意义。完整顺序以 system-design §20.2 为准;此处与 §20.2 一致。

完整目标设计与实施检查点见
[`tasks/translation/docs/system-design.md`](../tasks/translation/docs/system-design.md)（§20.2 接下来推荐顺序）。

开发任务本身的跨会话上下文由 [`AGENT_WORKFLOW.md`](AGENT_WORKFLOW.md) 和 `agent/tasks/` 管理；
它与翻译业务的 Agent job/result 协议是两层不同系统，不能共用状态文件。

设计原则：

- JSON 保存不可变、可移植、可审阅的业务工件。
- SQLite/WAL 只承担可重建索引、review queue、worker lease 和运行指标。
- API、本地模型、Codex、Claude Code、Cursor 和人工编辑统一生产 candidate，不直接覆盖发布物。
- bilingual/zh 是由确定版本渲染的派生产物，不再兼任 checkpoint 和修复数据库。
- repair 只生成新 candidate；只有 QA 与选择策略确认改善后才进入新版本。
- 硬规则 QA 是证据和 gate，不是语义质量排名；不能仅按 `error_count` 自动替换当前译文。
- recommendation 与 version creation 分离；无法证明 challenger 严格改善时保留 incumbent。
- 发布/current ref/批量 repair 前必须先建立统一 Artifact Store。

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
| candidate QA 评估 | 已完成 | 对 candidate 跑硬规则产出绑定 Evaluation；用于 gate/证据，不单独裁决语义优劣 | `tasks/translation/src/core/candidate_eval.py` |
| translate task/result 协议 | 最小闭环完成 | export-job + import-result 已往返；export 幂等入库 revision(#72);instruction pack + adapter(#57);job bundle 携带最小 Context Pack(术语/实体/邻句,折入 task 身份,#83 P1a);完整 Entity Store/Linking 与 review/repair job 待 #83 P1b | `tasks/translation/src/core/task_export.py` |
| result 导入(import-result) | 已完成(v3+store) | Task+Result → Candidate v3 + Attestation,写入分片 ArtifactStore:§5.4 stale 校验进 quarantine;内容寻址身份,同译文跨执行去重(一 Candidate + 多 Attestation),重放幂等 | `tasks/translation/src/core/result_import.py` |
| Legacy 导入 | 已完成(v3+store) | bilingual 反解 → Candidate v3 + legacy Attestation + DocumentRevision,写入分片 ArtifactStore:同译文跨目录代次去重为同一 Candidate,代次差异由 Attestation.legacy_label 区分;确定性幂等、截断容错 | `tasks/translation/src/core/legacy_import.py` |
| Source adapter / renderer | 已完成 | 目录→DocumentRevision 适配 + bilingual & zh shadow renderer(与现格式逐字节一致,golden 验证;zh 复刻 extract_chinese 字段变换,#42) | `tasks/translation/src/core/renderer.py` |
| Fixture/Golden 底座 | 已完成 | 合成脱敏 Pixiv/Fanbox fixture、golden document-revision/bilingual/zh、revision/segment ID pin 稳定性测试 | `tasks/translation/src/core/testdata/` |
| 业务工件 Schema | 基础完成 | 九类工件 JSON Schema（attestation、entity 等）、validate/round-trip/stale-result 测试与 CLI 校验已落地；DocumentVersion v2(#50)、entity(#83 P1b) | `tasks/translation/schemas/` |
| Candidate 身份 / Artifact Store | 已落地(#52+#54) | Candidate v3 内容寻址 + Attestation；Sharded `ArtifactStore`（按文档分片 JSONL + put_many 原子批写 + 冲突/身份硬 gate + `verify_references`）；legacy/result importer 已走 store。仍待 #55 SQLite 只读投影 | `tasks/translation/src/core/artifact_store.py` / 系统设计 §2.7 |
| 目标系统设计 | 分阶段实施 | P0 基础与 translate job 最小闭环已落地；2026-06-13 已按真实实现重新校准 | `tasks/translation/docs/system-design.md` |
| 开发 Agent 连续性 | 基础已落地 | 协议、Schema、validator、CI、GitHub 模板、`make agent-bootstrap`、`make docs-drift`(文档漂移闸门)与 PR 设计耦合检查已实现；GitHub 状态同步待实现 | `docs/AGENT_WORKFLOW.md` |
| 存量内容盘点/QA 基线 | 已完成 | `inventory_content.py` 全库清单 + `qa_baseline.py` 硬规则基线（v2 含打包产物与截断检查）；1048 单元中 894 个含 error（v2.1 打包按章拆分），坏产物已隔离 | `tasks/translation/src/scripts/inventory_content.py` |
| 多候选与版本 | 已完成保守择优(#50) | `version_select.py`:recommend_selection 判定表 + build_document_version v2 + render_version 渲染 bilingual;硬规则只做 gate,未证明严格改善则保留 incumbent。current ref 发布与自动 repair/Annotation 仍未做 | `tasks/translation/src/core/version_select.py` / Issue #50 |
| 翻译 Agent harness | 执行器就绪 | 共享 instruction pack + Claude skill / Cursor rule 薄适配 + `make translate-bundle`;SFW=Claude、NSFW=Cursor+Grok,同协议;context adapter(review/repair/knowledge)待实现 | `tasks/translation/docs/executor-instructions.md` |
| 用户句级反馈 | 未实现 | 尚不能持久化“某句话有问题”并触发定向修复 | 目标见系统设计 |
| 跨文本知识库 | 部分完成(#83 P1b-1/P1b-2a) | scoped 实体库 + resolver(entity_store.py)接入 Context Pack;Entity Linking 闸门 + review 队列(entity_review.py:抽取外部→链接→candidate→approve 晋升)。自动抽取器/模糊匹配/规则影响分析(P1b-2b)、instruction-pack(P1c)待做 | `entity_store.py` / `entity_review.py` / §7–8 / Issue #83 |
| 并发调度 | 缺口明显 | 当前仍主要依赖手工并行，没有内建 worker 调度器 | `tasks/translation/src/core/pipeline.py` |
| 测试 | 基线健康 | pytest 统跑全绿；基线数字唯一来源在 `AGENTS.md` §2，CI `docs-drift` 强制一致（unittest discover 会漏 pytest 风格用例） | `tasks/translation/src/**/*_test.py` |
| Sunday Movies | 维护模式 | 仓库中保留，但当前不作为近期规划重点 | `tasks/sunday-movies/` |

## Recent Engineering Changes

2026-06-13 Sharded ArtifactStore + integrity gate（#54，P1 第二步）：

- `artifact_store.ArtifactStore`：按 `store/<kind>/<provider>/<creator_id>/<source_id>.jsonl` 分片
  （文件数=文档数而非 candidate 数），`put_many(document_id, artifacts)` flock 锁 shard + 读一次建 id map
  + 校验（schema + candidate `validate_candidate_identity`）+ 冲突检测 + 写全量临时 + fsync + 原子 rename + dir fsync。
- 冲突保留：同 id 同 payload skip / 不同 payload `StoreConflictError`；幂等仅凭 JSONL，不依赖外部索引。
- `verify_references(artifact, resolver)`：candidate↔revision.source_hash、attestation/evaluation→真 candidate、
  version selection 同 revision/segment；resolver 按 document 作用域，不替代 stale-envelope 校验。
- legacy/result importer 迁移走 store（legacy 连 DocumentRevision 一并入库）；旧 flat write 移除。
- 写入边界强制 `verify_references`（resolver=现有∪本批∪已提交 shard），先锁全部 shard 预检（冲突+integrity）
  再按引用依赖序提交（逻辑预检失败不落盘；物理崩溃前缀引用完整、无悬空引用）；含 document_id 的 kind 强制与
  分片键一致；annotation/version 引用一致性（PR #69 两轮 review）。测试基线 208 → 229。

2026-06-13 Candidate v3 + Attestation（#52，P1 第一步）：

- Candidate 升级为 v3 纯内容工件（移除 producer/provenance/purpose/parent/created_at），
  `candidate_id = sha256({identity_version, revision_id, segment_id, source_hash, normalization_version, normalized_text})`，完整 64-hex。
- 新增 append-only Attestation schema 承接来源（producer/task·result digest/key/legacy_label/knowledge/created_at），attestation_id 确定性派生。
- `normalization_version=1` 冻结为 display-preserving（NFC + 去尾随空白，不折叠内部空白/不改标点）。
- legacy/result importer 迁移产出 v3 + attestation，**同译文跨 producer 去重 → 一个 Candidate + 多条 Attestation**。
- evaluation/document-version/annotation/task 的 candidate_id 引用同步收紧为 64-hex。
- review follow-up:`normalization_version` 收为 `const:1`;新增 `validate_candidate_identity`
  (text 已归一化 + candidate_id 与内容重算一致),在 importer 构建边界与 candidate_eval 强制调用
  (#54 的 `put_many` 也须调用);校验 CLI 对 candidate 也接身份强校验;pin 身份已知向量;
  system-design §6.2 改 v3 + §6.2a Attestation。测试基线 188 → 208。

2026-06-13 架构检查点：

- P0 Schema/fixture/adapter/legacy import 已落地，translate Task/Result/Candidate 最小往返已打通。
- candidate deterministic QA 已完成，但明确降级为 gate/证据，不能按 error 数直接定义“最佳译文”。
- 下一版本模型改为 recommendation 与 materialization 分离，并为每个 segment 保存选择证据。
- 识别出 Artifact Store 是进入发布、repair、SQLite 前必须补齐的核心边界。
- 测试基线更新为 186。

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

- DocumentRevision/Segment 已有 shadow path，但生产入口仍以 TXT 目录为主。
- candidate 已有 schema/import/evaluation；DocumentVersion v2 与 per-segment 选择证据已实现(#50)；current ref 发布未实现。
- translate Task/Result 最小闭环已完成；harness instruction pack + adapter 已落地(#57);translate job bundle 已可携带最小 Context Pack(术语/实体/邻句,#83 P1a);review/compare/repair 的 context bundle(引用外部工件)仍未实现(#83 P1b)。
- Artifact Store 已实现(#54:分片 JSONL + 原子批写 + 身份/冲突/引用硬 gate);写入统一走 store。
- 开发任务的跨 Agent 协议还没有 GitHub 状态同步（bootstrap 命令已完成，#9）。
- 存量 QA 基线 v2.1（2026-06-12，含顶层打包产物按章拆分与 missing_pair 检查）：
  1048 个单元（逐篇文件 + 打包章节）中 894 个含 error 级问题（kana 8757、
  same_as_source 5596、refusal 738、failure 501、empty 112；missing_pair 为 0——无结构性截断）。
  逐条修复依赖 P1 的 candidate/repair 闭环；报告见 `logs/inventory/qa_baseline.json`。
- 当前没有用户 annotation 生命周期和句级定向重译入口。
- 人名规则尚未实体化、作用域化和版本化，同名跨系列冲突仍需人工避免。
- **人名预读（name-glossary pre-reading）质量差**：本地模型自动抽取的人名候选词表错漏多
  （漏抽、错译、把普通词当人名、同名不统一），实测不可直接信任，仍需人工规则兜底。
  根因是单篇、无根基、无作用域的启发式 → **由 #83（Knowledge/Entity 库 + Entity Linking +
  context-builder）系统性取代**，#61 已关闭(打补丁定位作废)。
- **历史派生目录待清理**（#62，gated 在 #54 之后）：`data/**` 下 `*_bilingual/*_fixed/*_zh/*_v2/*_namefix/*_trial`
  等多代中间产物冗余，须在内容完整迁入 Artifact Store 且通过 integrity gate 后再归档/删除。
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

> P0 主链除 zh renderer（#42）外已完成；Artifact Store 从原“后期实现细节”提升为 P1 前置边界。

1. ~~存量内容库盘点、QA 基线与坏产物隔离~~（#10，已完成 2026-06-12：`inventory_content.py` +
   `qa_baseline.py`，3 个坏产物目录已隔离并记录 manifest）。
2. 为 `agent/tasks` 增加 GitHub 状态同步（bootstrap 命令已完成，#9）。
3. ~~固定 revision、candidate、evaluation、annotation、version、task、result 的 JSON Schema~~（#35，已完成 2026-06-13：`tasks/translation/schemas/` 七类 schema + 校验入口 + 15 个测试）。
4. ~~建立 Pixiv/Fanbox 最小 fixture、golden bilingual/zh 和 ID/hash 稳定性测试~~（#36，已完成 2026-06-13：`src/core/testdata/` 合成 fixture + golden + `source_identity.py` 稳定性测试）。
5. source adapter + `DocumentRevision/Segment` + renderer shadow path（#37：adapter 与 bilingual renderer 已完成,zh renderer 拆为 #42）。
6. ~~支持把现有 bilingual/fixed 文件导入为 legacy candidate~~（#38，已完成 2026-06-13：`legacy_import.py`,按目录标签确定性幂等导入,真实 momizi813 一篇 159 candidate 跑通）。

### P1: 多候选、版本与非破坏性闭环

实施顺序（2026-06-13 与 Codex 收敛）:**#52 → #54 → #50 →（#55 later）**。

1. ~~**#52** Candidate v3 + Attestation（内容寻址身份、文本等价去重）~~（已完成 2026-06-13：Candidate v3 纯内容 schema + Attestation append-only schema + 内容寻址 64-hex 身份 + display-preserving 归一化；legacy/result importer 迁移并去重）— #50 的前置。
2. ~~**#54** Sharded ArtifactStore + integrity gate（`verify_references`）+ legacy/result importer 迁移~~（已完成 2026-06-13：`artifact_store.py` 分片 JSONL + put_many 原子批写 + 冲突/身份硬 gate + verify_references；importer 走 store）。
3. **#50** 保守 recommendation（按判定表，error 只做 gate 不排名）+ `DocumentVersion` v2 + 从版本渲染 bilingual。
4. **#55** SQLite 可重建投影（vertical slice 之后，非硬前置）；zh renderer（#42）。
5. 执行器 harness:共享 instruction pack + 自然语言触发的 translate-job skill + Cursor/Codex 适配（NSFW 走 Cursor+Grok）。
6. repair 创建新 candidate，完成 QA -> compare -> select 闭环;CLI 级比较/选择/回滚/annotation;current ref 与 CAS。

### P2: API/Agent 双执行路线与知识一致性

1. ~~实现 translate task/result 的 `export-job` / `import-result` 最小闭环~~（#44/#46）。
2. **context-builder + Context Pack（#83 P1a）已提前为 Current Focus 的下一步**（先于端到端 demo / current ref，见 §20.2）；本节 P2 仅保留其后的 `validate-result`、review/repair task。
3. 为 Codex、Claude Code、Cursor 提供由同一 instruction pack 派生的薄适配。
4. 建立 scoped entity store、knowledge snapshot、entity linking review 和规则影响分析（#83，取代 #61）。
5. 将现有人工 name map 迁移为 locked entity translations，自动预读只进入 candidate（#83 播种，见 #62 迁移）。

> Housekeeping（#62）：历史派生目录清理/归档，硬性 gate 在 #54 完成且 integrity 校验无丢失之后执行。

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
- 连续完成 3–5 个同一架构链路的 PR，或跨越一个 Phase 边界时，必须做一次 design/status/issue reconcile。

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
