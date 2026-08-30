# 翻译覆盖率报告与内容拦截的按段处理

## 背景

两件事在同一批工作里撞到一起，根子都是**"看不见"**：

1. `provenance_report` 从 store 出发，只回答"这篇是谁翻的"。它天然看不见从没进过流水线的篇——
   `pixiv:9425701:18137868` 因此漏了几个月（下载器 YAML 转义 bug 让它连 prepare 都进不去），
   而所有报表都没有源那一侧的对照，于是"少了一篇"永远没人发现。
2. cursor-agent CLI 把"内容被模型提供方拦截"报成 `ActionRequiredError`，与额度耗尽同名。
   仓库把整个 `ActionRequiredError` 放进不可重试清单，于是 `momizi813:12240198` 在
   340/494 段处被单段拦截，整篇作废——已译的 340 段只是靠断点侥幸留住，日志里只打了
   `{"errors": 1}`，错因埋在会被下一次运行覆盖的 `translate_manifest.json` 里。

## 改动

- `src/scripts/coverage_report.py`（新）+ `make coverage`：以
  `data/<provider>/<creator>/<id>.txt` 为分母、任一 workspace 的 current ref 为分子，
  并对未发布的篇跑一次 front matter 解析，把"下载就坏了"和"只是还没翻"分开。
- `openrouter_executor.ContentBlocked`：拒绝的是**这一条 prompt**，交给 `_translate_segment`
  的退档阶梯换档位；第三档拿掉 `[上文]` 后 prompt 显著变短，实测就能过。每一档都被拒才
  按 executor-instructions「宁可空，不要假」留空该段并记 `segment_quality` finding。
- `cursor_agent._CONTENT_BLOCK_MARKERS` 先于 `_FATAL_MARKERS` 判定。
- `provenance_report`：`attestation.created_at` 本就是该候选的翻译时刻，原来只做分组标题
  且标成"发布于"有歧义；改成每行一列「翻译时间」（日期 + 时分）。
- `scripts/fanbox_download.yaml_escape`：补上与 `batch_download_v1` 相同的加引号逻辑。
  两个下载器各写一份 YAML 拼装，pixiv 侧修过的 bug 在 fanbox 侧原样留着。

## 验证

- 全量扫描：545 篇已下载 / 20 篇未发布译文，全部 front matter 可解析（没有第二个 18137868）。
- `momizi813` 6 篇新作端到端跑完（cursor-agent / cursor-grok-4.5-high 逐段），
  字数比 0.74–0.82；12240198 带着修复从断点续跑，494 段全部通过。
- `make author-collection CREATOR=momizi813` → 143 篇，`verify → ok: true, errors: []`。
- `conda run -n llm python -m pytest tasks/translation/src -q`（583 passed）
- `make docs-drift`

## 教训

- **只有正向报表就等于没有对账。** 从 store 出发的报表天然只能列出"已经在里面的东西"，
  漏网的那类问题必须靠源与产物两侧的差集来发现，而不是靠人偶然想起来数一下。
- **错误分类比错误处理更容易出错。** `ActionRequiredError` 同时表示账号级和请求级两种故障，
  按名字归类就把"换个说法就能过"的错当成了"重试毫无意义"。分类的依据应当是**故障作用域**
  （这条 prompt / 这个账号），不是错误名。
- **失败摘要要能自解释。** `{"errors": 1}` 不带任何错因、且详情写在会被下次运行覆盖的
  manifest 里，等于把排障成本推给下一个人。

## 关联

- 分支 `fix/overtranslation-and-markers`
