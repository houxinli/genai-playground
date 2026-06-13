# 2026-06-13 开发复盘与系统设计检查点

## 已完成

两天内完成了主干拆分、跨 Codex/Claude Code/Cursor harness、review triage 与测试纠偏，
并沿目标架构落地了：

- 七类业务工件 Schema、fixture/golden 和稳定身份。
- DocumentRevision/Segment source adapter 与 bilingual shadow renderer。
- legacy Candidate 导入。
- translate Task export、Result import 和 Candidate 幂等写入。
- candidate deterministic QA Evaluation。

pytest 当前为 186 个测试全绿。任务状态、checkpoint、PR review 和 CI 已经形成可重复的开发闭环。

## 流程复盘

有效做法：

- 一事一支一 PR，把长期混合分支拆回线性 main。
- task state + checkpoint 让 Codex/Claude Code 可交替继续。
- 合并前 review triage 连续发现真实 bug，包括测试假绿、输入完整性和 stale-result 缺口。
- 先冻结 Schema/fixture/ID，再逐步接 adapter/importer，降低了迁移风险。

暴露的问题：

- 开发速度快于状态文档：PROJECT_STATUS 仍写 149 测试、Agent task/result 未实现。
- 每个 PR 都更新局部 journal，但缺少阶段性 reconcile，导致 roadmap、设计和实现出现语义漂移。
- 任务合并后再补 completion-only commit 会制造主干噪声；完成状态应在原 PR 合并前固化。
- 当前 importer 写入任意 `store_dir`，还没有统一 Artifact Store。
- Issue #50 原计划按 `error_count` 最小选“最佳候选”，会把硬规则误当成语义质量。
- DocumentVersion v1 只有整篇一个 decision，无法解释每个 segment 的选择来源。

## 设计修正

1. 硬规则 QA 只做 gate 和证据，不作为完整质量排名。
2. recommendation 与 version materialization 分离。
3. 自动替换采用 incumbent-preserving 策略：不能证明 challenger 严格改善就保留当前选择。
4. DocumentVersion 升级为 v2，增加逐 segment 的 incumbent、evaluation 和选择理由。
5. Artifact Store 提升为 P1 前置；发布、current ref、repair 和 SQLite 都必须经由它。
6. 下一阶段先完成单文档 vertical slice，再扩展 knowledge、并发和 UI。

## 推荐顺序

1. 修订 #50 并实现保守选择 + DocumentVersion v2 + bilingual render。
2. Artifact Store + cross-artifact validator。
3. #42 zh renderer。
4. 真实单文档端到端 demo。
5. annotation + 非破坏性 repair。
6. API bridge 与完整 harness context/instruction pack。
7. knowledge、SQLite、并发和 UI。

## 流程改进

连续完成 3–5 个同一架构链路 PR，或跨越一个 Phase 边界时，必须做一次
system design / PROJECT_STATUS / GitHub issue reconcile。journal 记录历史，但不能替代阶段状态校准。
task `complete` 表示分支已满足合并条件，merge 状态交给 GitHub，不再为此追加 main-only 收尾提交。
