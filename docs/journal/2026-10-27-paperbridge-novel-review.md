# 2026-10-27 译文修订搬到 paperbridge 网页

## 动机

已发布译文里零星的错译（代词、假名残留、重复句）只能在终端里翻 `<sid>.zh.tsv` 改，看不到上下文，
手机上做不了。照 ytmusic 选版的做法，把逐段修订放到 paperbridge `/novels/`。

## 改动

- `src/scripts/paperbridge_novels.py` + `make novels-export` / `make novels-import`。
  - 导出：每篇 current ref 指向的发布版本 → batch JSON（schema v1，与 paperbridge `novels/schemas.py` 对齐），
    每段带 `document_qa` 与假名检查的标记。多 workspace 指向不同版本的篇不导出（与合集构建同一口径）。
  - 导入：逐段修改写回 TSV → 用原始 job 重组 result → `finish_document` 带血缘重新发布。不新增修复入口。
    三道闸门（底稿 = 当前发布译文；TSV 与发布版本逐段一致；当前源 + 实体库重建的 task 与原始 job 同 digest），
    任一不过整篇跳过；finish 未发布时还原 TSV/result；发布后逐段核对，被篇内译名锁改写的段单独报告；
    写入的修改追加到 `results/<sid>.edits.jsonl`（候选 producer 沿用原执行器，这份日志是人工改动的记录）。
  - 标题/系列名/标签把角色标成未成年人的篇不导出，没有开关。
- `provenance_report.load_published` 抽出"读发布版本"的逻辑，溯源报告与导出共用；溯源输出与重构前逐字节一致。

## 验证

- 全套测试 594 → 600（新增 6）。
- 全部 559 个 current ref 都有 TSV + job；按当前源与实体库重建 task，559 篇全部与原始 job 同 digest
  （339 篇不带实体库、220 篇带），重新 finish 不会被隔离。
- TSV 与发布版本逐段比对：555 篇一致；4 篇共 7 段不一致（46788631:20567151 等），这几篇导入会被拒。
- 本地 paperbridge + 真实导出样本：页面浏览、逐段修改、`novels.cli edits` 取回、`make novels-import DRY_RUN=1` 预检通过。

## 后续

- 粒子（53230930）的 13913215、14186514 两篇有多个 workspace 指向不同版本，导出与合集构建都会跳过，需先清理。
- 修改的人工来源目前只在 edits.jsonl 里；要进 attestation 需要 producer 能按段区分，另议。
