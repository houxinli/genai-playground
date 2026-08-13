# 执行器内联复检与自动路线产物对齐

## 背景

把 API 路线的模型从 `x-ai/grok-4.3` 换成 `deepseek/deepseek-chat` 跑 `pixiv:104039620:27417304`，
产出两类污染并且直接发布了：

1. 约半数 body 段把 prompt 里的 `[上文]` 邻句一起译进本段（段 i 的译文 = 译(上一段) + 译(本段)）。
2. 3 段把 `T<TAB>译文` 与 `E<TAB>名<TAB>译名` 挤在同一物理行，整条协议被当成正文发布。

两类都绕过了既有防线：整段并不相同，`duplicate_translation` / `block_paste` 漏检；
`[上文]` 标记本身没漏出来，`context_marker_leak` 也不触发。第 2 类还被"把折行并回译文"的
宽容解析放大——第二条 T 记录不是折行，却被原样粘进了上一条的译文。

修复过程一开始全靠会话里的临时脚本（从 store 反推 candidate、重译、手工组装 result 重发），
这本身暴露了第二个问题：自动路线不落任何可改产物。

## 改动

- `parse_executor_response`：折行合并遇到第二条 `T` 记录即中断；译文残留 TAB 判协议漂移。
- `_SYSTEM_BASE` 明确"只翻译 `[翻译这一段]`，不要翻译/复述邻句"——此前这条只写在
  `executor-instructions.md`，没进 system prompt。
- `translate_bundle` 逐段内联复检（协议残留 / 超长 / 邻段窜入），不过就退档重试：
  原样重问 → 追加"只译本段" → **拿掉 `[上文]`**。结构错仍中断整篇，质量错照常发布并记
  `segment_quality` finding。
- `document_qa` 新增 `neighbor_overlap`（warning，对所有执行器生效）。双阈值：执行器内联 0.35
  （误判只多一次 API 调用）、finish 上报 0.55（要给人看，必须窄）。
- `translate_user(results_dir=, jobs_dir=)`：自动路线落与 agent 路线同款的 `<sid>.zh.tsv`
  和本次 prepare 的原始 job，两条路线的修复路径统一为
  `改 tsv → MODE=finish RESULTS_DIR=... JOBS_DIR=...`。
- `author_collection` 支持 `study`(陪读) variant，manifest 记 `variants`、verify 以 manifest 为准。

## 验证

- 回放 27417304 的原始产物：内联复检拦下 81/213 段、finish QA 报 39 段；
  修好的版本分别降到 4 段和 1 段（承接省略句与连续拟声词，已知误报）。
- 换 `pixiv:104039620:28349232` 用同一模型端到端重跑：219 段，
  空 0 / 假名 0 / 协议残留 0 / 邻段窜入 0，全程无临时脚本。
- 只落 tsv 不落 job 时改 tsv 重跑 finish 复现 `task_digest mismatch` quarantine，
  补 job 后 round-trip 通过（已加测试）。
- `conda run -n llm python -m pytest tasks/translation/src -q`（491 passed）
- `make docs-drift`
- `make author-collection-verify CREATOR=104039620` → `ok: true`

## 教训

- **容忍属于解析层，检测属于执行层。** 为了适配小模型而放宽解析，会把语义污染一起放行；
  该在生成时检测重试的事，不要靠解析宽容来兜。
- **顺序执行的循环里就有跨段视角。** `translate_bundle` 手里就有上一段译文，事后才做的
  邻段重复检测完全可以内联——同一个判据放在执行器里成本是一次重试，放到 finish 就是整篇返工。
- **中间产物必须成对。** TSV 没有配套 job 是修不了的。

## 关联

- Campaign #185
