# 2026-06-13 最小 fixture 与 golden 稳定性底座(P0.4)

## 背景

迁移需要回归锚点(issue #36,system-design §20 Phase 0):脱敏最小 fixture、golden
输出、稳定的 revision/segment ID。依赖 P0.3 schema(已落地)。

## 改动

- `src/core/testdata/fixtures/`:合成 SFW 的 Pixiv(700001)/Fanbox(800001)源文件,
  与真实格式同构(YAML front matter + 正文),不含私有语料。
- `src/core/source_identity.py`:从源计算 revision_id(canonical 载荷含 adapter/segmentation
  版本)与 segment_id,构建并校验 document-revision(复用 gh-35 schema);只覆盖身份与最小
  行级 segmentation,源格式适配/renderer 留给 P0.5。
- `src/core/testdata/golden/`:每个 fixture 的 golden document-revision.json 与
  bilingual/zh 渲染快照(后者作为 P0.5 renderer 的目标锚点)。
- 9 个测试:revision_id pin 稳定、build==golden 且 schema 合法、确定性、segment 唯一性、
  源文/算法版本变化改 ID、golden bilingual↔body segment 一致、fixture SFW/离线卫生。

## 决策(已记入 PR)

- fixture/golden 放 `src/core/testdata/`(已跟踪)而非 issue 原写的 `data/test/`——后者被
  `.gitignore` 整目录忽略,无法当跨机器/CI 回归锚点。
- revision_id pin 成测试字面量:身份算法任何变化都会显式失败,符合"算法版本变化必须产生新
  revision"。

## 验证

pytest 全量 140 绿(基线 131→140)。
