# 2026-06-12 Codex review follow-ups 批次(#15–#21)

## 背景

复盘发现 9 个已合并 PR 的 21 条 Codex review 意见从未被读取。triage 后开 8 个
agent-ready issue(#14–#21),按 #15→#14→#16→#17→#18→#19→#20→#21 顺序逐个执行。
#15/#14/#16/#17 走完整 task state 生命周期,#18–#21 按 one-off 处理。

## 各 PR 与要点

| Issue | PR | 内容 |
| --- | --- | --- |
| #15 | #22 | CI 改 pytest 统跑(基线 59→110),补 sunday 3 套;暴露并修复 builder_test 过时断言与 amc.py 嵌套 span 真 bug |
| #14 | #23 | validator 完成性三规则 + bootstrap 默认 required_commands + §9/PR 模板加入 review triage |
| #16 | #24 | qa_gate 对齐报 missing_pair,截断不再漏检 |
| #17 | #25 | 盘点/基线脚本三修正;打包文件按章拆分;基线 v2.1=1048 单元/894 error,missing_pair=0 |
| #18 | #26 | MLX 启动改 BSD script(1),实测启动/停止 |
| #19 | #27 | 评分缓存键含年份;标题噪声清洗尾部锚定 |
| #20 | #28 | fitness 跨年日期推断两处 + 空日志 CLI |
| #21 | #30 | 设计文档:candidate 幂等键含 result_digest、current ref 真 CAS、§6.2 schema 同步 |
| — | #29 | 清理 (review: PR #N) 溯源注释(AGENTS.md §3) |

## 新流程的实效

review triage(合并前必读必处置)在本批次首跑即连续生效:Codex 在 #22/#23/#24/#25/#28/#30
的**修复本身**中又发现 7 条有效意见(含 2 条 P1),全部修复+回复后才合并。
"review 未读即合并"的旧模式已被流程与 PR 模板勾选项双重堵死。

## 教训

- 被跳过的测试会腐烂:amc_test/builder_test 的失败在首次真正运行时才暴露。
- 自动 review 对"修复的修复"同样有效,值得把等待 review 作为合并前的固定步骤。
