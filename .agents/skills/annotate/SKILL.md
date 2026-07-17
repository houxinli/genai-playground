---
name: annotate
description: 给已翻译发布的作品产出「陪读版」:日文原文里对 N3+ 生词/语法加括号注解(读音+词义+语法)。独立 pass,不重新翻译,支持存量文章。
argument-hint: "<provider> <creator_id> <work_id> [level=N3]"
---

# annotate(陪读)

你是日语精读老师。任务:把一篇**已翻译发布**的作品做成「陪读版」——在日文原文行内,对超出读者水平的词和语法加括号注解。**不重新翻译**,中文译文行原样保留。

触发示例:
- `用 annotate 给 fanbox momizi813 的 11602314 做陪读版。`
- `用 annotate 处理 pixiv 104039620 的 26594168,级别 N2。`

## 输入 / 输出

- 输入:`$WS/rendered/<work_id>.bilingual.txt`(WS = `tasks/translation/data/workspaces/<provider>-<creator_id>` 或 per-work 目录,哪个有 rendered 用哪个)
- 输出:`$WS/rendered/<work_id>.study.txt` —— 与 bilingual **逐行同构**(行数、行序完全一致),唯一区别是**日文源行加了注解**。

## 注解规则

默认读者水平 **N3**(可由用户指定 N2/N4):

1. **只注日文源行**。中文译文行、front-matter(`---` 之间)、空行**一字不改**。
2. **只注 N3+(超出读者水平)的内容**;N5/N4 常见词、简单外来语(パッケージ等)不注,避免满屏括号。
3. 注解格式(读音、词义、语法合在一个括号里,不拆):
   - 生词:`漢字(かんじ・词义)` —— 如 `姿(すがた・身姿)`
   - 语法/句型:紧跟在该结构后 `(句型:简短解释)` —— 如 `なんかいられない(〜てはいられない:顾不上、没法一直…)`
   - 词+活用叠加时合并:`恥ずかしがって(恥ずかしい+〜がる:表现他人情绪;て形)`
4. **同一个词篇内只注第一次**;再出现不注(读者已见过)。
5. **人名**:读音/译名以 `tasks/translation/data/entities/` 实体库(creator scope)为准;库里没有的按上下文注读音即可。
6. 拟声词/语气词(むにゅ、ちゅぱ等)**不注**——它们无固定意义,注了也没用。
7. 注解**简短**:词义 2-6 字,语法解释一句话内。陪读不是词典,是"扫读障碍"。

### 示例

原文行:
```
パッケージに映るのは、恥ずかしがってなんかいられない彼女の姿だった。
```
陪读行:
```
パッケージに映(うつ・映照)るのは、恥ずかしがって(恥ずかしい+〜がる:表现他人情绪;て形)なんかいられない(〜てはいられない:顾不上、没法一直…)彼女の姿(すがた・身姿)だった。
```

## 流程

1. 读 `$WS/rendered/<work_id>.bilingual.txt`。
2. 逐行处理:日文源行(含假名的行,且不在 front-matter 内)按上述规则加注解;其它行原样。约 40-60 行一批,批间自检:①行数没变 ②译文行没被改 ③注解括号配对。
3. 写出 `$WS/rendered/<work_id>.study.txt`。
4. **核验**(必做,回贴结果):
   ```bash
   python3 - <<'EOF'
   import sys, re
   src = open('$WS/rendered/<work_id>.bilingual.txt', encoding='utf-8').read().split('\n')
   out = open('$WS/rendered/<work_id>.study.txt', encoding='utf-8').read().split('\n')
   assert len(src) == len(out), f"行数变了: {len(src)} -> {len(out)}"
   kana = re.compile(r'[぀-ゟ゠-ヿ]')
   changed_zh = [i for i, (a, b) in enumerate(zip(src, out)) if a != b and not kana.search(a)]
   assert not changed_zh, f"非日文行被改: 行 {changed_zh[:5]}"
   n_annotated = sum(1 for a, b in zip(src, out) if a != b)
   print(f"OK: {len(src)} 行, {n_annotated} 行加了注解")
   EOF
   ```
5. 回贴:核验输出 + 注解了多少行 + 3 个注解样例。

## 边界

- 一次一篇,整篇做完再做下一篇(篇间可并行,篇内单写者)。
- 遇到无法判断的读音(生僻人名/作者生造词),按最常见读法注并在回贴里列出存疑项。
- **不要动** bilingual/zh 原文件、不要动 store/results,陪读是纯附加产物。
