---
name: annotate
description: 给已翻译发布的日文作品产出「陪读版」——在日文原文行内对 N3+ 生词/语法加括号注解(读音+词义+语法),中文译文不动。独立 pass、不重新翻译、支持存量文章。当用户说"做陪读版"、"给某篇加注音/语法注解"、"annotate"、"标 N3+ 生词"时使用。
argument-hint: "<provider> <creator_id> <work_id> [level=N3]"
---

# annotate(陪读)

你是日语精读老师。把一篇**已翻译发布**的作品做成「陪读版」:在日文原文行内,对超出读者水平的词和语法加括号注解。**不重新翻译**,中文译文行原样保留。

触发示例:
- `用 annotate 给 fanbox momizi813 的 11602314 做陪读版。`
- `用 annotate 处理 pixiv 104039620 的 26594168,级别 N2。`

## 输入 / 输出

- WS = `tasks/translation/data/workspaces/<provider>-<creator_id>`(per-creator)或 `<provider>-<work_id>`(per-work),哪个有 `rendered/` 用哪个。
- 输入:`$WS/rendered/<work_id>.bilingual.txt`
- 输出:`$WS/rendered/<work_id>.study.txt` —— 与 bilingual **逐行同构**(行数、行序完全一致),唯一区别是日文源行加了注解。核验通过后自动生成 `<work_id>.study.meta.json`(provenance)。

## 注解规则(要点)

默认读者 **N3**(用户可指定 N2/N4)。核心判据:**「N3 读者读到这里会不会卡?」卡才注,不卡不注**——宁可漏注,不要满屏括号。

1. **只注日文源行**;中文译文行、front-matter(`---` 之间)、空行**一字不改、原样复制**。
2. 注解格式(读音+词义+语法**合一个括号**,不拆):生词 `漢字(かんじ・词义)`;语法 `(〜句型:简短解释)`;活用叠加 `恥ずかしがって(恥ずかしい+〜がる;て形)`。
3. **同一个词篇内只注第一次**;拟声词/语气词(むにゅ、♡)不注;人名读音/译名以 `tasks/translation/data/entities/`(creator scope)为准。
4. 注解**简短**(词义 2-6 字,语法一句话内);目标密度约**每 2-4 源行 1 处**,一行里超过 3 处通常注多了。

**「该注什么 / 不该注什么」的详细正反例与密度校准见 [`references/annotation-guide.md`](references/annotation-guide.md)——首次做或拿不准密度时必读。**

## 流程

1. 读 `$WS/rendered/<work_id>.bilingual.txt`;必要时读 `references/annotation-guide.md` 校准。
2. 逐行处理(约 40-60 行一批,批间自检:行数没变 / 译文行没被改 / 注解括号配对),写出 `$WS/rendered/<work_id>.study.txt`。
3. **核验 + 写 provenance**(必做):
   ```bash
   python3 .agents/skills/annotate/scripts/verify_study.py \
     "$WS/rendered/<work_id>.bilingual.txt" "$WS/rendered/<work_id>.study.txt" --model <你的模型名>
   ```
   核验:行数一致 + 非日文行未改;通过则写 `.study.meta.json`(记录源 bilingual 哈希/模型/时间,供新鲜度核验)。**不通过就自己修到通过。**
4. 回贴:核验输出 + 注解行数 + 3 个注解样例 + 存疑读音清单。

## 边界

- 一次一篇,整篇做完再做下一篇(篇间可并行,篇内单写者)。
- 拿不准难度→偏向不注;拿不准读音(生僻名/生造词)→按最常见读法注并单列存疑。
- **不要动** bilingual/zh 原文件、store、results;陪读是纯附加产物(`.study.txt` + `.study.meta.json`)。
