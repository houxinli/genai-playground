# 2026-06-12 存量内容库盘点、QA 基线与坏产物隔离

## 背景

25+ 目录的存量翻译产物散落在 `data/pixiv`、`data/fanbox` 和 data 顶层,没有全库账本:
哪些作品翻完、哪些目录是实验残留、旧译文质量如何,全靠记忆。Phase 1 legacy 导入
需要干净、有账可查的输入(issue #10,P0.1)。

## 改动

- `inventory_content.py`:按作品聚合 源/派生(bilingual/fixed/v2/namefix)/打包 形态与
  完成度(复用 `run_state` 占位/失败标记语义),报告落 `logs/inventory/inventory.json`。
- `qa_baseline.py`:对全部 bilingual 派生目录逐文件跑 `TranslationQAGate`,
  汇总问题类型分布,报告落 `logs/inventory/qa_baseline.json`。
- 隔离 3 个坏产物目录(2 个 `repair_tmp` + 1 个 `broken_bak`)到 `data/quarantine/`,
  manifest 记录原路径/原因/恢复方法;重跑盘点隔离候选清零。
- 修复 CI 缺口:`src/scripts/` 缺 `__init__.py`,`extract_chinese_test` 从未被
  discovery 执行;测试基线 50 → 59。

## 全库基线结论(2026-06-12)

- 11 个源目录(7 pixiv + 4 fanbox),21 个 bilingual 派生目录,731 个译文文件。
- **616/731 文件含 error 级问题**:kana_residue 5016、same_as_source 3853、
  refusal_marker 505、failure_marker 501。
- 注意:same_as_source/kana_residue 含合理假阳性(数字、专名、拟声词),
  基线用于趋势对比和 repair 优先级,不直接等于"待修复清单"。
- 逐条修复不在本任务范围;依赖 P1 candidate/repair 闭环(repair 只生成新 candidate)。

## 后续

- legacy 导入(P0.6)可直接消费 inventory 报告作为输入清单。
- `momizi813_bilingual*` 与 `46788631_bilingual` 是问题密度最高的目录,
  可作为 P1 repair 闭环的第一批试点。
