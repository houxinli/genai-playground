---
name: annotate
description: 给已翻译发布的日文作品产出「陪读版」——对日文原文的 N3+ 生词/语法加括号注解(读音+词义+语法合一),经流水线建注解版本并渲染 study。当用户说"做陪读版"、"加注音/语法注解"、"annotate"时使用。
argument-hint: "<provider> <creator_id> <work_id> [level=N3]"
---

# annotate(陪读)

你是日语精读老师 + 流水线执行器。任务:对一篇作品的**日文原文**加学习注解,走与翻译同构的流水线(#174):prepare 出注解 job → 你写注解 TSV → finish 建注解版本(独立 channel,不动译文)→ 渲染 `study.txt`(注解原文 + 当前译文交织)。

触发示例:
- `用 annotate 给 pixiv 104039620 的 27417304 做陪读版。`
- `用 annotate 处理 fanbox momizi813 的 11602314,级别 N2。`

## 流程

工作区 `WS=tasks/translation/data/workspaces/<provider>-<creator_id>`(或 per-work `<provider>-<work_id>`,哪个有 store 用哪个);源文件在 `data/<provider>/<creator_id>/<work_id>.txt`,放进 `$WS/src/`(或临时 SOURCE 目录只含本篇)。

1. **prepare**(导出注解 job,只含 body 段):
   ```
   make translate-user MODE=prepare TASK_TYPE=annotate PROVIDER=<p> SOURCE=$WS/src STORE=$WS/store JOBS_DIR=$WS/jobs
   ```
2. **注解**:读 `$WS/jobs/<work_id>.annotate.job.json` 的 `segments[]`,逐段产出**注解后的源文行**,写 `$WS/results/<work_id>.annotate.<你的模型名>.tsv`(v2 三列:`段号<TAB>src_echo<TAB>注解行`)。
   - **硬规则(评估会机械校验,违者该段作废)**:注解只能**插入括号段**,不得增删改原文任何字符——剥掉全部 `(…)` 后必须逐字等于源文;单行、无 TAB;**没有注解的段原样抄源文**(每段必须有行)。
   - 注什么/怎么注见下「注解规则」;约 40-60 段一批,批间自检(骨架/括号配对/段号连续)。
3. **finish**(评估→择优→注解版本→publish 独立 channel→渲染 study):
   ```
   make translate-user MODE=finish TASK_TYPE=annotate PROVIDER=<p> SOURCE=$WS/src STORE=$WS/store JOBS_DIR=$WS/jobs RESULTS_DIR=$WS/results RENDER=$WS/rendered [PRODUCER_PRIORITY=模型a,模型b]
   ```
   回贴 finish 的 JSON。`published:1` 才算完成;`unresolved` 表示有段注解违反硬规则,修 TSV 重跑。
4. 产物:`$WS/rendered/<work_id>.study.txt`(注解原文+当前译文)。多模型对比:各写各的 `<work_id>.annotate.<producer>.tsv`,一次 finish 按 `PRODUCER_PRIORITY` 逐段择优。

## 注解规则(要点)

读者是**日语学习者**:N4 已过、**正在学 N3、目标年底考 N3**(用户可指定 N2)。核心判据:**「读者可能不认识、或读音/用法拿不准」就注**——注 N3 及以上,N4 词也倾向注;拿不准→注(漏注比多注差)。

- 格式(读音+词义+语法**合一个括号**):生词 `漢字(かんじ・词义)`;语法 `(〜句型:简短解释)`;活用叠加 `恥ずかしがって(恥ずかしい+〜がる;て形)`。
- **同词篇内只注第一次**;拟声词/感叹词/符号不注;人名以 `tasks/translation/data/entities/`(creator scope)为准。
- 注解**简短**(词义 2-6 字,语法一句话内);密度由词的难度决定,不按行数。
- 详细正反例见 [`references/annotation-guide.md`](references/annotation-guide.md)——首次做必读。

## 边界

- 一次一篇;篇间可并行,篇内单写者。
- 拿不准难度→偏向注;拿不准读音(生僻名/生造词)→按最常见读法注并单列存疑。
- **不要动**翻译产物(zh.tsv/result.json/bilingual)——注解走独立 channel(refs-annotate),翻译更新只需重跑 finish 重渲染 study,注解版本不失效。
