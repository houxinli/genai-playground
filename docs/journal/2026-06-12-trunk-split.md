# 2026-06-12 主干收敛、harness 落地与首个 dogfood 任务

## 背景

`fix/repair-non-destructive` 实际上是一条机器命名时代遗留的长期混合分支:相对 `origin/main`
积压 21 个未合并提交(translation/sunday-movies/CI/docs),工作区还叠着未提交的
harness、fitness、translation system-design 三块 WIP。harness 协议 review 确认其设计可用,
但自身不落地就无法 dogfood。

## 改动

按 strict split 把积压与 WIP 拆为 6 个独立 PR,全部 rebase 线性合入 main:

| PR | 内容 |
| --- | --- |
| #3 | sunday-movies Frodo API(cherry-pick) |
| #4 | translation 18 提交按原序重放(QA gate、人名 glossary、MLX、非破坏性 repair、文档收敛) |
| #5 | CI workflow + pre-push hook(刻意最后合并:其测试依赖 #3/#4 的代码,先合必红) |
| #6 | agent harness:协议 + schema + validator(7 测试)+ CI gate + GitHub 模板;AGENTS.md 增"默认中文交流" |
| #7 | translation 目标系统设计 + 架构 journal |
| #8 | fitness 子项目首次入库(12 测试) |

关键验证:每步本地测试先行;拆分完成后 `git diff origin/main <原HEAD>` 为空,
21 提交 + 全部 WIP 无损迁移。`fix/repair-non-destructive` 与 `macbook` 删除,仓库收敛到唯一 `main`。

## 决策

- CI 合并顺序让位于代码依赖:tests.yml 引用的测试模块/修复在 #3/#4 中,故 #5 殿后,启用即绿。
- Makefile 按 hunk 拆分(agent 块进 #6、fitness 块进 #8),其余跨切文档整体随 harness PR,
  接受数分钟的悬空链接,换取免 patch 手术。
- 存量内容库盘点(全库清单、QA 基线、坏产物隔离)进入 P0 首位(issue #10),
  排在 Phase 1 legacy import 之前。

## 后续

- 首个 dogfood 任务 `gh-9-agent-bootstrap`(issue #9)已按 AGENT_WORKFLOW §9 bootstrap,
  S1(bootstrap CLI)进行中。
- roadmap 看板尚缺:可选 milestone=Phase 或 GitHub Projects,待定。
