# Fitness Log — 健身记录解析与进展追踪

把你在 Apple Notes 里随手记的一长条训练日志，解析成结构化数据，并画出**每个动作的力量进展曲线**。

设计原则：**记录端零摩擦**。你照旧用自由文本随手敲，解析器负责把它整理成数据；动作改名、错别字、新旧两种写法都由 [`config/exercises.json`](config/exercises.json) 这张可编辑的词表收敛。所有产物是纯文本（CSV）和纯 SVG，不依赖 matplotlib/pandas，以后想搬到 Notion 或别的 app 直接拿 CSV 走。

## 快速开始

```bash
conda activate llm   # 仅用标准库，但沿用仓库环境

# 解析 data/workout_log.md -> data/derived/sets.csv
make fitness-parse

# 看看都识别出了哪些动作、各练了多少次
make fitness-exercises

# 某个动作的力量进展（文本表，支持中文名/英文别名/canonical slug）
make fitness-progress EXERCISE=坐姿杠铃推举
make fitness-progress EXERCISE=bench_press

# 进展曲线 SVG（用 Preview/浏览器打开）
make fitness-chart  EXERCISE=辅助引体
make fitness-charts            # 所有 >=6 次的动作各出一张，写到 data/derived/charts/
```

底层 CLI（更多参数）：`python tasks/fitness/src/cli.py --help`。
`--today YYYY-MM-DD` 可固定"今天"，让跨年的日期推断可复现。

## 怎么记录（保持可解析）

继续把每次训练写成：一行日期+分化，下面每个动作一行。两种写法都能解析，**推荐用现代写法**：

```
5.19 push                                  # 日期 月.日（无需年份，解析器按倒序推断）+ 分化 push/pull/leg
坐姿杠铃推举 60deg 上F下8 85lbs 12 rpe8 95lbs 6 rpe8 4 rpe9
bench press 95lbs 12 rpe8 12 rpe9 12 rpe8
```

一行 = `动作名 [器械设置] 重量lbs 次数 rpeN 次数 rpeN ...`：

- **重量**带单位 `lbs`/`kg`；不写单位会按上一组延续，所以换重量时记得写新的 `NNlbs`。
- **次数 rpeN** 成对出现；省略 rpe 也行（`25lbs 10 10` = 两组各 10 次）。
- **器械设置**（`60deg`、`上F下8`、`上9下6`）放在重量前，会被单独存到 `setup` 列，不影响数据。
- **括号**里写状态/技巧（`（grip issue）`、`（拿放）`），存到 `note` 列。

旧写法 `动作 重量 组数 次数`（如 `辅助引体 40 4 12` = 40lbs 助力、4 组 ×12）也兼容，主要为了吃历史数据；新记录建议统一用现代写法，曲线更准。

## 力量进展怎么算

每个动作每次训练取一个"最佳"数字，含义随**加载方式**（在词表里按 `weight_type` 标注）变化：

| weight_type | 例子 | 进展指标 | 方向 |
| --- | --- | --- | --- |
| `loaded` | 卧推、RDL、肩推 | 该次最佳估算 1RM（Epley：`重量 × (1 + 次数/30)`） | 越高越强 |
| `assisted` | 辅助引体、辅助臂屈伸 | 该次**最低**助力重量 | 越低越强（曲线已翻转成"向上=进步"） |
| `bodyweight` | 俯卧撑、TRX、平板 | 单组最多次数 | 越多越强 |

混用单位会污染曲线（2024 年卧推记 `bar+N`，2025 年记 `lbs`），所以同一动作只取**出现最多的单位**那一档来画。

## 目录结构

```
tasks/fitness/
├── README.md
├── config/exercises.json     # 动作别名 -> canonical + 部位 + weight_type（手动维护）
├── data/
│   ├── workout_log.md        # 原始自由文本日志（真相源，建议提交）
│   └── derived/              # 解析产物 sets.csv + charts/*.svg（git-ignored）
├── src/
│   ├── model.py              # SetRecord 数据模型 + Epley 1RM
│   ├── parser.py             # 自由文本 -> SetRecord（跨年日期、新旧记法、无法解析行打 flag）
│   ├── normalize.py          # 按词表归一化动作名
│   ├── report.py             # 进展计算 + CSV 导出 + 纯 SVG 画图
│   └── cli.py                # parse / exercises / progress / chart / chart-all
└── tests/parser_test.py      # unittest，覆盖新旧记法、跨年、归一化等
```

## 维护词表

新动作或没归类的写法会在 `make fitness-exercises` 里标 `(unmapped)`。把它的写法加进 `config/exercises.json` 的 `aliases`（指向一个 canonical slug），需要时在 `exercises` 里补 `{name, muscle, weight_type}`。匹配大小写不敏感、空格折叠，所以 `Push Up` / `push up` 只需写一条。

## 已知限制（诚实记录）

- 2024 年的 `bar+N` 杠铃记法只抓到 `N`（单位记为 `bar`），和 lbs 不可比，按单位分档已规避。
- 极少数多重量混写、纯热身行、康复/灵活性条目无法解析，会进 issues 列表（`make fitness-parse` 末尾 `issues:` 计数，`--show-issues N` 看样例）。当前约 100 行/2600+ 组，主要是 mobility 与笔记。
- 估算 1RM 用 Epley 公式，高次数（>12）时只是趋势参考，不是真 1RM。

## 测试

```bash
conda run -n llm python -m unittest discover -s tasks/fitness/tests -t . -p "*_test.py"
```

## 下一步想法

- 训练量（volume）与各部位频率统计、PPL 平衡度。
- PR 检测与提醒。
- 饮食记录子模块（当前只做了健身）。
- 把 `sets.csv` 导入 Notion database，或反过来从 Notion 导出再喂解析器。
