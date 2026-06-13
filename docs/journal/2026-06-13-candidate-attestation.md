# 2026-06-13 Candidate v3 + Attestation 内容寻址身份拆分（#52，P1 第一步）

## 背景

旧 Candidate（v2）把"译文内容"和"谁/怎么产出"塞在同一工件里，且存在两套不一致的 candidate ID
（result importer 用 `candidate_id_for`、legacy importer 用 `legacy_candidate_id`，都是 16-hex 截断）。
这有两个根本问题：

- **无法去重**：同一句被 legacy + agent + grok 译成相同文本时，会产出多个不同 ID 的 Candidate
  （单作者 momizi813 按现有派生目录导入即约 5.5 万），存储不可扩展。
- **immutable 张力**：若第二个 producer 产出相同文本却要把来源追加进同一 Candidate，Candidate 就不再不可变。

与 Codex 在 issue #52 评论 round 1-2 收敛出的方案：Candidate / Attestation 二分 + 内容寻址身份。

## 改动

- **Candidate v3**：纯内容、不可变、content-addressed。字段只剩
  `candidate_id, document_id, revision_id, segment_id, source_hash, normalization_version, text`；
  `producer / provenance / purpose / parent_candidate_id / created_at` 全部移出。
- **Attestation**（新 append-only 工件）：承接来源，`attestation_id` 确定性派生 → 同 Result / 同 legacy
  重放不新增。同一 Candidate 可有多条 Attestation。
- **内容寻址身份**：`candidate_id = "cand_" + sha256(canonical{identity_version, revision_id,
  segment_id, source_hash, normalization_version, normalized_text})`，完整 64-hex。
  效果：同译文跨 producer → **一个 Candidate + 多条 Attestation**（文本等价自动去重）。
- **normalization_version=1 冻结为 display-preserving**：仅 NFC + 去尾随空白，不折叠内部空白、不改标点/引号，
  保证 `Candidate.text == 可直接渲染译文`（否则去重对、渲染会偏离原译）。
- **importer 迁移**：`legacy_import` / `result_import` 产出 v3 + Attestation。
- 一致性收紧：evaluation / document-version / annotation / task.existing_candidate_ids 的
  `candidate_id` 引用模式同步改为 64-hex（否则无法引用真实 v3 candidate）。

## Review triage（三通道，Codex）

PR #64 时 Codex 提 1 个 P1：`task.existing_candidate_ids` 漏改 → 已收紧 + 补测试 + inline 回复。

合并后用 `agent/prompts/review-clean-state.md` 模板让 Codex 做整体清洁度审查，又抓出：

- **P1 身份强校验缺失**：schema 接受任意 `normalization_version>=1`（实现只支持 v1），且接受
  "ID 按旧文本生成、text 后被改"的 Candidate。→ `normalization_version` 改 `const:1`；新增
  `validate_candidate_identity()`（text 已归一化 + candidate_id 与内容重算一致），在 importer 构建边界
  与 `candidate_eval` 强制调用，并写入 #54 acceptance（store 的 `put_many` 也必须调）。
- **P1 system-design §6.2 仍是 Candidate v2**：与同文件 §2.7 和代码矛盾 → §6.2 改 v3 + 新增 §6.2a Attestation 示例，
  Eval/Version/Annotation 示例的 candidate ID 占位统一为 `cand_<64 hex>`。
- **P2**：身份测试只证"两次调用相等"未 pin 已知向量 → pin
  `cand_8b41…ca86eb` / `att_04cca1…0f9eaf`（Codex 与 Claude Code 独立核算一致，抓 canonical 口径漂移）；
  `build_attestation(**core)` 可覆盖生成字段 → 拒绝保留字段；legacy 跨 producer 测试补"落同一 store →
  N Candidate + 2N Attestation"；PROJECT_STATUS 残留 v2 语义（`candidate_id_for`/跨执行独立）改为去重语义。

## 验证

`pytest tasks/translation/src -q` 全绿；基线 188 → 206。`check_docs_drift` / `validate_agent_tasks` 通过。
身份已知向量交叉核算一致。

## 教训

- #65 是 completion-only PR（规范禁止），#64 当时也没配 journal。**收尾（task complete + checkpoint）和
  journal 应并入功能 PR**，不再单开 PR；本条已补 journal，后续按此执行。
- 内容寻址改身份会扩散到"所有引用该 ID 的 schema / 代码 / 文档 / 示例"。这次靠 Codex 的整体审查模板才补全
  task schema、§6.2 示例、PROJECT_STATUS 语义这些边角——把该模板沉淀进 `agent/prompts/` 正是为此。
