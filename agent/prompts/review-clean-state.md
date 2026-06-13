# 审查模板：变更后清洁度 / 一致性审查

可复用的 **只读** 审查 prompt，用于让另一个 agent（Codex / Claude Code / Cursor）在一个架构/schema/
契约类改动合并后，确认仓库 **干净、完整、无遗漏、自洽**，并给出"能否进入下一个任务"的结论。

## 何时用

- 刚合并一个会扩散到多处的改动（身份/schema 升级、契约变更、数据模型迁移、大范围重命名）。
- 跨越 Phase 边界或连续合并多个同链路 PR 后做 reconcile。
- 交接前想要一个独立视角确认没有"看似完成其实漏改"的地方。

## 怎么用

1. 复制下面「通用模板」，把 `{{…}}` 占位符替换为本次实际值。
2. 粘给 Codex（PR 评论 `@codex review` 或对话）或另一个 agent，要求 **只审查、不改文件**。
3. 把结论按 P0/P1/P2 带回，逐条 triage（fixed / answered / filed as follow-up）。

> 规范要求：审查口径与"设计跟代码走""测试基线唯一来源在 AGENTS.md §2"一致；见
> [`../../AGENTS.md`](../../AGENTS.md) 与 [`../../docs/AGENT_WORKFLOW.md`](../../docs/AGENT_WORKFLOW.md)。

---

## 通用模板

```
请审查本仓库当前 {{分支，通常 main}} 的状态，重点确认刚合并的 {{变更主题}}（{{相关 issue / PR}}）
是否干净、完整、无遗漏。只做审查，不要修改任何文件；最后按严重度（P0/P1/P2）汇总发现，
并明确给出"可以进入下一个任务 {{下一个 issue}} / 还需先修哪些点"的结论。

先按 AGENTS.md §12 建立上下文：读 AGENTS.md、docs/PROJECT_STATUS.md、
{{相关设计文档与章节}}、{{相关 issue 的设计评论}}。
确认当前在 {{分支}}、工作树干净、CI 绿、测试基线 = {{基线数}}。

请逐项核查（找"已漂移/遗漏/不自洽"的具体位置，给 文件:行，不要泛泛而谈）：

1. 核心不变量是否真正自洽
   - {{本次改动的核心契约/身份/算法，逐条写清期望}}。
   - 实现与 schema、与设计文档描述是否完全一致；确定性输入口径是否统一
     （序列化 sort_keys / 编码 / 分隔符 / 字段顺序），有没有遗漏字段导致结果不稳定。

2. 语义是否落到实处
   - {{本次改动期望产生的行为，如去重/幂等/迁移,逐条写清}}。
   - 改造后是否残留旧模型假设（旧字段、旧函数、旧 id 格式）、计数/幂等不一致。

3. 全仓一致性（最容易遗漏）
   - 搜索是否还有任何地方仍用旧 schema/旧格式/旧字段（给出要 grep 的具体符号与模式）。
   - 所有引用该契约的 schema / 代码 / CLI / 文档是否都已同步（列出应覆盖的清单，逐个确认）。

4. 文档与基线
   - AGENTS.md §2 基线数字、PROJECT_STATUS、相关设计文档是否与代码现状一致；
     docs-drift 闸门是否真能抓到本次相关漂移。

5. 测试是否覆盖关键不变量
   - 是否有测试钉住每条核心不变量与新行为；有没有"看似通过其实没断言到关键点"的弱测试。

6. 卫生
   - 工作树是否干净、有无未提交/无关改动；agent/tasks/{{task-id}}/state.json 与
     checkpoints.jsonl 是否与分支一致、status 正确、next_task 指向 {{下一个 issue}}。

输出格式：先给一句总体结论（干净可推进 / 有阻塞项），再按 P0/P1/P2 列发现，
每条给 文件:行 与具体修复建议；没有问题的检查项也明确说"已确认无问题"。
```

---

## 实例：#52 Candidate v3 + Attestation（2026-06-13，可直接复制）

```
请审查本仓库当前 main 的状态，重点确认刚合并的 #52（Candidate v3 + Attestation，PR #64/#65）
是否干净、完整、无遗漏。只做审查，不要修改任何文件；最后按严重度（P0/P1/P2）汇总发现，
并明确给出"可以进入下一个任务 #54 / 还需先修哪些点"的结论。

先按 AGENTS.md §12 建立上下文：读 AGENTS.md、docs/PROJECT_STATUS.md、
tasks/translation/docs/system-design.md §2.7、GitHub issue #52 的 round 1-2 评论。
确认当前在 main、工作树干净、CI 绿、测试基线 = 199。

请逐项核查下面这些，找"已经漂移/遗漏/不自洽"的地方，而不是泛泛而谈：

1. 内容寻址身份是否真正自洽
   - candidate_id = cand_ + sha256(canonical{identity_version, revision_id, segment_id,
     source_hash, normalization_version, normalized_text})，完整 64-hex。
   - 检查 artifact_schemas.candidate_id_v3 / normalize_text / attestation_id_for / build_attestation
     的实现是否与 schema、与 system-design §2.7 描述完全一致；canonical 序列化口径是否统一
     （sort_keys/ensure_ascii=False/分隔符），有没有 hash 输入顺序或字段遗漏导致 id 不稳定。
   - normalization_version=1 是否真的 display-preserving：只做 NFC + 去尾随空白，
     不折叠内部空白、不改标点/引号；"Candidate.text == 可直接渲染译文"这条是否成立
     （特别是 renderer 现在读哪份文本，会不会和归一化后文本不一致）。

2. 去重语义是否落到实处
   - 同译文跨 producer → 一个 Candidate + 多条 Attestation；同 Result/同 legacy 重放
     → candidate 与 attestation 都零新增（确定性）。
   - legacy_import / result_import 改造后是否还有残留的 v2 假设（producer/provenance/purpose/
     parent_candidate_id/created_at 写进 candidate）、旧 candidate_id_for / legacy_candidate_id
     残留、或写盘时 candidate 与 attestation 计数/幂等不一致。

3. 全仓一致性（最容易遗漏的点）
   - 搜索是否还有任何地方仍用旧 candidate schema v2、旧 id 模式 ^cand_[0-9A-Za-z]{8,40}$、
     或代码里仍按 v2 字段读取 candidate（grep candidate["producer"/"provenance"/"purpose"]）。
   - 所有引用 candidate_id 的 schema 是否都已收紧到 64-hex：candidate / attestation /
     evaluation / document-version / annotation / task.existing_candidate_ids。有没有漏的工件
     或 CLI/契约仍接受旧格式。

4. 文档与基线
   - AGENTS.md §2 基线数字、docs/PROJECT_STATUS.md、system-design §2.7 是否与代码现状一致；
     check_docs_drift 是否真的能抓到这次改动相关的漂移。

5. 测试是否覆盖关键不变量
   - 是否有测试钉住：id 64-hex 稳定性、归一化 display-preserving、attestation 确定性派生、
     跨 producer 去重（1 candidate + N attestation）、legacy 与 result 两条 importer 的迁移与幂等。
   - 有没有"看似通过其实没断言到关键点"的弱测试。

6. 卫生
   - 工作树是否干净、有没有未提交/无关改动；agent/tasks/gh-52-candidate-attestation/
     state.json 与 checkpoints.jsonl 是否与分支一致、status=complete、next_task 指向 #54。

输出格式：先给一句总体结论（干净可推进 / 有阻塞项），再按 P0/P1/P2 列发现，
每条给出 文件:行 与具体修复建议；没有问题的检查项也明确说"已确认无问题"。
```
