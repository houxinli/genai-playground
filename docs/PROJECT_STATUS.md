# Project Status

> 当前项目状态、组件健康度和开发计划的真相源。
> 新的 agent / 新的对话优先读这份文档，再进入具体子系统文档。

**最后更新**: 2026-05-01

## Start Here

建议按下面顺序建立上下文：

1. [`../README.md`](../README.md)
2. [`PROJECT_STATUS.md`](PROJECT_STATUS.md)
3. [`AGENT_CONTEXT.md`](AGENT_CONTEXT.md)
4. [`../tasks/translation/README.md`](../tasks/translation/README.md)
5. [`journal/README.md`](journal/README.md)

## Repository Snapshot

- 当前主战场是 `tasks/translation`。
- `tasks/sunday-movies` 仍在仓库内，但当前处于维护模式，不是近期主要开发方向。
- 常用运行环境是 `conda` 的 `llm` 环境。
- 最近一轮工程改进聚焦“下载 -> 翻译 -> 修复/清理 -> 打包”的可靠性，而不是新功能扩张。

## Current Focus

当前目标是把翻译流水线从“能跑完”提升到“可恢复、可验证、可维护”。

2026-04-07 完成的 P0 里程碑：

- 为翻译阶段补上持久化运行状态和输出状态判断。
- 让半成品输出不会再被误判为成品。
- 为打包阶段补上结构化元数据回退，降低 `未知标题` 和标题漂移。
- 为上述改动补回归测试，并清理了阻塞全量测试的旧 QC 断言。

## Component Status

| 组件 | 状态 | 说明 | 主要入口 |
| --- | --- | --- | --- |
| Pixiv 下载 | 可用 | 终端链路可用，数据落到 `tasks/translation/data/pixiv/<USER_ID>/` | `tasks/translation/src/scripts/batch_download_v1.py` |
| Fanbox 下载 | 可用 | 浏览器脚本优先，终端链路依赖登录态 | `tasks/translation/scripts/fanbox_browser_downloader.js` |
| 主翻译流水线 | 可用 | 支持 `*_bilingual/`、`*_zh/` 输出；已支持 partial/failed/running/complete 判定，并可在完成后生成 QA 报告 | `tasks/translation/src/core/pipeline.py` |
| 输出状态持久化 | 新增完成 | 运行状态记录在配置的 `log_dir` 下的 `translation_state.json` | `tasks/translation/src/core/run_state.py` |
| 修复流程 | 可用 | 标准 repair 已支持经由 `src/translate.py --repair-existing` 进入主流水线；修复人名敏感文本时可注入同一份人名规则 | `tasks/translation/src/translate.py` |
| 打包/提取中文 | 可用 | 已补 `.meta.json` / `index.json` 元数据回退 | `tasks/translation/src/scripts/extract_chinese.py` |
| 质量检测 | 可用 | 规则 QC + LLM QC 可工作；新增硬规则 QA gate，可检查双语配对、假名残留、拒绝模板、失败标记和人名坏别名 | `tasks/translation/src/core/qa_gate.py` |
| 人名一致性 | 可用 | 支持人工规则优先、自动预读候选保存、正文 OpenRouter + 本地 vLLM/MLX 抽名的分离运行时 | `tasks/translation/src/core/translator.py` |
| Preset 体系 | 基本可用 | 已新增 OpenRouter 正文翻译 + 本地人名预读 preset；来源拆分仍需继续完善 | `tasks/translation/config/presets.json` |
| 并发调度 | 缺口明显 | 当前仍主要依赖手工并行，没有内建 worker 调度器 | `tasks/translation/src/core/pipeline.py` |
| 测试 | 基线健康 | `unittest discover` 当前为 43 个测试全绿 | `tasks/translation/src/**/*_test.py` |
| Sunday Movies | 维护模式 | 仓库中保留，但当前不作为近期规划重点 | `tasks/sunday-movies/` |

## Recent Engineering Changes

这轮已经落地的关键改动：

- 新增 [`../tasks/translation/src/core/run_state.py`](../tasks/translation/src/core/run_state.py)，持久化 run/file 级状态。
- [`../tasks/translation/src/core/file_handler.py`](../tasks/translation/src/core/file_handler.py) 和 [`../tasks/translation/src/core/pipeline.py`](../tasks/translation/src/core/pipeline.py) 已统一输出路径语义，并识别 `missing/partial/running/failed/complete`。
- 修复流程已并回主入口：`translate.py --repair-existing` 可直接修复已有 bilingual 输出，并写入 `*_bilingual_fixed/`。
- [`../tasks/translation/src/scripts/extract_chinese.py`](../tasks/translation/src/scripts/extract_chinese.py) 已支持从源目录结构化元数据回退标题、ID、时间戳。
- [`../tasks/translation/src/core/quality_checker.py`](../tasks/translation/src/core/quality_checker.py) 修正了 `bilingual` 参数链路，避免运行时 `TypeError`。
- 新增 [`../tasks/translation/src/core/qa_gate.py`](../tasks/translation/src/core/qa_gate.py)，支持 `--qa-report` 跟随翻译/修复生成硬规则报告，也支持 `--qa-only` 检查已有输出。
- 人名预读运行时已可独立配置：本地模型只做人名候选抽取，正文翻译仍可走 OpenRouter。
- [`../tasks/translation/config/presets.json`](../tasks/translation/config/presets.json) 新增 `fanbox_openrouter_local_names` 和 `pixiv_openrouter_local_names`。
- 已补回归测试：
  - [`../tasks/translation/src/core/file_handler_test.py`](../tasks/translation/src/core/file_handler_test.py)
  - [`../tasks/translation/src/core/pipeline_repair_test.py`](../tasks/translation/src/core/pipeline_repair_test.py)
  - [`../tasks/translation/src/core/repairer_test.py`](../tasks/translation/src/core/repairer_test.py)
  - [`../tasks/translation/src/scripts/extract_chinese_test.py`](../tasks/translation/src/scripts/extract_chinese_test.py)
  - [`../tasks/translation/src/core/quality_checker_qc_format_test.py`](../tasks/translation/src/core/quality_checker_qc_format_test.py)
  - [`../tasks/translation/src/core/quality_checker_test.py`](../tasks/translation/src/core/quality_checker_test.py)
  - [`../tasks/translation/src/core/qa_gate_test.py`](../tasks/translation/src/core/qa_gate_test.py)

## Known Gaps

- 还没有内建的文件级并发调度器，批量任务提速仍依赖外部手动拆分。
- metadata 翻译、preset 选择、来源差异目前仍然耦合得不够清晰。
- 打包已经有元数据回退，但还没有完全摆脱对译后 YAML 的依赖。
- QA gate 仍是硬规则第一版，尚未和 repair 形成完整自动闭环。
- 成本、耗时、重试率等运行指标还没形成统一报表。

## Development Plan

### P1: 近期高优先级

1. 做 QA -> repair -> QA 的自动闭环。
   目标：翻译后自动定位问题行，修复后再次验收，最终状态区分 complete / failed_qa / repair_failed。
2. 内建文件级并发调度。
   目标：支持 `--workers N`、限速、失败重试和更稳定的吞吐控制。
3. 做 token-aware batching。
   目标：从“按行数”升级到“按 token 预算和时延目标”分批。
4. 拆分来源相关 preset 和 metadata 流程。
   目标：Pixiv / Fanbox 的 prompt、metadata、quality gate 能按来源配置。

### P2: 质量与可维护性

1. 为术语一致性和标题稳定性建立更系统的回归集。
2. 让打包、修复、状态文件共享同一份元数据真相源。
3. 补运行指标和成本统计。
4. 继续拆薄 `pipeline.py`，把 plan / translate / qa / repair / package 逐步阶段化。

### 文档维护规则

- 只要“当前重点、组件状态、近期计划”发生了实质变化，就更新本文件。
- 只要有值得回溯的阶段性决策或问题处理，就新增一篇 journal 条目并在索引登记。
- `AGENT_CONTEXT.md` 保持偏稳定背景；不要再把短期任务清单长期堆在里面。

## Validation Baseline

当前推荐的基础验证命令：

```bash
conda run -n llm python -m unittest discover -s tasks/translation/src -t . -p "*_test.py"
```

如果只想回归本轮新增的关键测试：

```bash
conda run -n llm python -m unittest tasks.translation.src.core.file_handler_test
conda run -n llm python -m unittest tasks.translation.src.core.pipeline_repair_test
conda run -n llm python -m unittest tasks.translation.src.core.repairer_test
conda run -n llm python -m unittest tasks.translation.src.scripts.extract_chinese_test
conda run -n llm python -m unittest tasks.translation.src.core.quality_checker_test
conda run -n llm python -m unittest tasks.translation.src.core.quality_checker_qc_format_test
```
