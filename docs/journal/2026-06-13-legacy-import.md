# 2026-06-13 legacy candidate 导入(P0.6)

## 背景

迁移不能丢历史:存量 bilingual/fixed/v2/namefix 需按目录标签导入为 legacy Candidate
(issue #38)。依赖 P0.3 schema、P0.5 adapter/renderer。

## 改动

- `legacy_import.py`:
  - `parse_bilingual_translations`:render_bilingual 的逆——按 revision 反解 front matter 配对
    与正文对,得到逐 segment 译文;错位/截断只恢复对齐部分并记 issues。
  - `build_legacy_candidates`:每个 (目录标签, segment, 译文) 一个 producer.type=legacy 的
    Candidate;candidate_id = sha256(legacy:标签:segment:译文) → 确定性。
  - `write_candidates`:按 candidate_id 幂等写入(已存在跳过)→ 重复导入零新增。
  - `import_directory`:目录级配对导入 + 报告(posts/candidates/written/skipped/missing_source/issues)。
- 6 测试(round-trip 恢复、文本一致、幂等、标签区分、截断容错、目录报告)。

## 验证

pytest 全量 158 绿(基线 152→158)。真实冒烟:fanbox/momizi813_bilingual/10034751
一篇导出 159 candidate、issues=0、幂等重跑 written=0。

## 决策

- 不按目录名猜质量:每个目录标签独立 producer/candidate(_bilingual 与 _v2 即使同 segment
  也是不同 candidate),保留来源;文本等价去重留作后续。
- 隔离目录由调用方据盘点报告跳过(importer 不自行判定)。
- legacy candidate 无 task/result,故 candidate_id 走 legacy 专用派生(非 candidate_id_for)。
