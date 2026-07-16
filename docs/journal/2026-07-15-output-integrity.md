# 2026-07-15 执行器结构污染与作者合集新鲜度闸门

## 动机

momizi813 最新批次虽然已经写入 current ref 并完成逐篇渲染，但抽样复核发现执行器把邻段与
`[tags]` 标记混入单个 candidate。旧 document QA 只检查重复块，无法阻断这种单段多行污染；同时旧作者
合集不会记录所依据的 current version，新增文章后仍可能把少章节的旧 EPUB 当成最新成品。

## 改动

- `document_qa` 新增 `multiline_translation` 与 `context_marker_leak` error，阻断违反扁平 TSV 契约的结果。
- OpenRouter 在组装 Result 前复用同一输出形状检查，不把明显污染候选写入 store。
- `author_collection` 构建前要求每个 current ref 同时具备 zh/bilingual rendered，缺任一输入即失败。
- 合集先在临时目录构建并自校验，成功后才替换旧目录。
- 新增 `collection_manifest.json`，记录 source/version、逐篇 rendered、章节数和整本输出 digest。
- 新增 `make author-collection-verify`，检测新增/删除 ref、current version、重渲染与成品漂移。

## 验证

- 定向测试覆盖多行/marker 污染、缺 rendered 保留旧合集、新 ref、重渲染和成品修改。
- 全量 `pytest tasks/translation/src -q`：445 项通过。
- `make docs-drift`、`make agent-validate`、`git diff --check` 通过。
- 现有 momizi813 旧合集因没有 manifest 按预期验证失败，不再被误判为最新成品。

## 后续

- 新批次只有在结构污染段经内容执行器复核并重新发布后，才可重建完整作者合集。
- 旧合集首次迁移需重建一次以生成 manifest；之后交付前统一运行 `author-collection-verify`。
