---
name: translate
description: 用统一 TSV harness 把 pixiv/fanbox 作品日→中翻译并发布渲染。支持断点续跑、整作者、Cursor/Grok/Claude/Codex/OpenRouter 任一执行器。
argument-hint: "<provider> <creator_id> [work_id] [executor=cursor-grok|claude-code|codex]"
---

# translate

你是日→中翻译执行器。**"执行器"意味着你自己就是翻译模型:译文由你逐段亲自产出**,
不要调用任何外部翻译 API、不要写脚本生成译文(仓库里的 openrouter 自动路线只在用户明确指定
`EXECUTOR=openrouter` 时使用)。一次翻不完就分多轮续跑——这是设计内的正常形态,不是绕道的理由。

用户一句话即可触发,例如:

- `用 translate 翻译 pixiv 104039620 的 28349232,执行器 cursor-grok。`
- `用 translate 继续 pixiv 104039620 的 28349232。`

**不依赖聊天历史**:先从 workspace 文件恢复状态;有未完成的就续,没有才新建。**全程自主连续执行,步骤之间不要问"是否继续"**;只有源无法解析、或结构命令反复失败才停下报告。

翻译规则以 [`tasks/translation/docs/executor-instructions.md`](../../tasks/translation/docs/executor-instructions.md) 为准——先读它,本文件不重复。

## 单一译文产物:扁平 TSV

你**只写 TSV,不手写 `result.json`**——result 由 harness 从 `job.json + zh.tsv` 机械组装(回填 segment_id/source_hash/task_digest)。
篇内首次出现的新名字另记在同目录 `<source_id>.names.tsv`,每行只写 `日文原名<TAB>中文译名`;没有新名字就不建。

```text
job.json → results/<source_id>.zh.tsv (+ 可选 names.tsv) → (harness 组装) result.json → 发布 → 渲染 → verify
```

TSV 每行优先写 v2:`<0 基段序号><TAB><源文前缀 src_echo><TAB><中文译文>`；二列旧格式仍兼容但缺少对齐保护。译文可空(表示无法翻译,但该行必须在)。不要 Markdown 包裹、不要解释、不要额外列。

## 流程

工作区 `WS=tasks/translation/data/workspaces/<provider>-<work_id>`。

1. **prepare**(导出 bundle;源在 `data/<provider>/<creator>/<work_id>.txt`):
   ```
   mkdir -p $WS/src && cp <源 txt> $WS/src/
   make translate-user MODE=prepare PROVIDER=<p> SOURCE=$WS/src STORE=$WS/store JOBS_DIR=$WS/jobs
   ```
   `make` 默认 `ENTITY_STORE=tasks/translation/data/entities`,prepare 会把该 creator 适用的人名/术语
   **自动解析进 `job.context_pack.entities`**(openrouter 执行器拼成硬约束、agent 执行器读约束)——
   已批准的跨篇译名以此为准,别再往 prompt 手写译名。未批准的新名字只在当前篇的 `names.tsv` 内保持一致,
   finish 后自动作为待审候选,不会直接污染跨篇实体库。要临时关闭传 `ENTITY_STORE=`(空)。
2. **翻译**:读 `$WS/jobs/<work_id>.job.json` 的 `segments[]`,逐段译,写/追加 `$WS/results/<work_id>.zh.tsv`。
   - tags 段译成 `原词 / 中文`,保留 `[]` 和逗号;人名/术语遵 `job.context_pack`。
   - 同时维护 `$WS/results/<work_id>.names.tsv`:每批只读取 `job.context_pack.entities` 和这份表。仅当新名字及其译名实际出现在本批源译时追加一行;Context Pack 已有的名字不重复写。已出现的名字只复用表中首次译名,不得追加不同译名。后来批次出现变体时只修正本批译文,下一批仍只携带首次译名表。
   - `names.tsv` 只属于当前篇。finish 会把首次用法送审;只有批准后的实体才会进入以后作品的 `context_pack`。
   - **译文不得残留任何假名——人名(みのり→实里 这类)与拟声词/语气词(むにゅ♡→软绵♡ 这类)同样必须译成中文**,不是"可留"项;唯一例外是 tags 段的「原词 / 中文」左半。
   - **批量自适应**:每批按源文长度控制在约 3000–5000 字符(段落长则少翻几段,短对话可多翻),不要固定死段数——顶到输出上限正是漏译半句/截断的高发原因。
   - **逐批自检(append 前)**:扫一遍本批产出——①有没有行译文==源文(没翻);②有没有假名残留(tags 行除外);③段号是否连续无重复。有问题先修再写入。自检只针对刚写的批,不重读全篇。
3. **发布渲染**(finish 自动从 tsv 用原始 job 组装、发布、渲染、合并整本):
   ```
   make translate-user MODE=finish PROVIDER=<p> SOURCE=$WS/src STORE=$WS/store JOBS_DIR=$WS/jobs RENDER=$WS/rendered RESULTS_DIR=$WS/results PRODUCER=<执行器名>
   ```
   finish 必须使用 prepare 时相同的 `SOURCE` 与 `ENTITY_STORE`;旧 job 的 `context_pack.entities` 为空且
   当时显式关闭过实体库时,修复重跑也传 `ENTITY_STORE=`。上下文不一致会 quarantine 并非零退出;
   按终端 `next_action` 修正参数,不要手改 result/ref 绕过 stale 防护。
4. **verify**(独立核对,**回贴真实 JSON**;不准凭记忆声称完成):
   ```
   make translate-user MODE=verify PROVIDER=<p> SOURCE=$WS/src STORE=$WS/store RENDER=$WS/rendered RESULTS_DIR=$WS/results
   ```
5. **FEEDBACK**:写 `$WS/FEEDBACK.md`——verify JSON、`review_required` 段及译文问题、改进建议;回贴要点。

整作者:把该 creator 的所有 `<work_id>.txt` 都放进 `$WS/src`,prepare/finish 会逐篇处理并合并整本。

## 断点续跑

tsv 不全时 finish 会报缺段。续法:先读同篇 `names.tsv`,再对照 `job.segments` 数量找出 tsv 里缺的段序号,**补译那些行追加到同一个 `<work_id>.zh.tsv`**,再重跑 finish。续译只带 `context_pack` 与表内首次译名;tsv 已有的行不重译。(无 run_id / 分片目录——就一个扁平 tsv。)

## 并行

**篇与篇之间可以并行**(每篇一个独立 TSV,互不干扰)——多开 loop/子任务按篇分工没问题。
**一篇之内禁止多 agent 分段拼**:段落对齐靠单一写者顺序追加保证,多写者拼一篇会重新引入错位(gh-142 教训)。

## fill(补缺:只补空行/坏行,已翻好的不动)

修补已有译文,只处理两类行,其余**一字不改**:

- `用 translate fill pixiv <creator_id>。`(整作者)或指定 `<work_id>`。

1. 遍历 `$WS/results/<id>.zh.tsv`(三列 v2),找出:①译文列为空的行;②译文列含日文假名的行(tags 行除外)。
2. 对这些行,读 `$WS/jobs/<id>.job.json` 同段号 `source_text` 重新翻译,填/覆盖译文列;**其余行保持原样**。
3. 人名/术语走 `job.context_pack.entities` 加同篇 `names.tsv` 的首次译名,用它保持一致。
4. 内容策略见下「边界」;涉及不可译内容时该行留空,最后汇报留空段号。
5. 一个作者全部 tsv 补完 → finish + verify(整作者:`SOURCE=data/<provider>/<creator>`),回贴两段 JSON。

## review(双语对照复查,独立会话)

翻译完成后的语义复查,**必须在新会话/新上下文执行**(翻译者对自己刚写的输出有确认偏差,同上下文自查抓不到错位类问题):

- `用 translate review pixiv <creator_id> <work_id>。`

1. 读 `$WS/jobs/<work_id>.job.json` + `$WS/results/<work_id>.zh.tsv`(或 `$WS/rendered/<work_id>.bilingual.txt`),按约 50 段窗口**逐窗对照源↔译**;
2. 检查:① **对齐**——每行译文是不是本段源文的翻译(错位/整块复制/张冠李戴);② **漏译**——译文为空或明显只译了半段;③ **明显误译**(人名/否定/数字类硬错,不吹毛求疵改风格);
3. 发现问题**直接改 TSV 对应行**(写 v2 三列格式),记录改了哪些段和原因;
4. 有改动则整篇重跑 finish + verify,把改动清单写进 `$WS/FEEDBACK.md` 并回贴。

无问题时回贴「review clean: <work_id>, N 段」一行即可。

## 边界

- **结构错误必须修**:缺段、重复/越界段序号、stale job/source。
- **质量问题不阻断发布**:假名残留 / same_as_source / 拒绝模板等单候选会**照常发布**并计入 `review_required`,事后改对应 tsv 行重跑 finish 即可——不要因此重译整篇。
- 完全无译文(空候选)的段仍会阻断建版(#153:有空行的篇不会带缺口发布,整篇 unresolved,等补齐)。
- **内容策略(如 NSFW / 未成年内容由哪个执行器承担)以 [`AGENTS.md`](../../AGENTS.md) 与各执行器自身适配为准**,本 skill 不内联。
- **遇到你不能翻的行**:该行译文留空、继续下一段,**最后汇报留空段号清单**——不要净化、不要含糊改写、不要中断整篇。整篇核心都是你不能翻的题材时,跳过该篇并说明。
