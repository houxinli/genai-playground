SHELL := /bin/bash

CONDA_ENV := llm
# 使用无缓冲输出，确保流式内容实时打印
PY := conda run -n $(CONDA_ENV) python -u

# 支持参数透传
export DEBUG ?= 0
export MODE ?= bg
export MODEL ?=
export VLLM_MODEL ?= Qwen/Qwen3-32B-AWQ
export MLX_MODEL ?= deadbydawn101/gemma-4-E2B-Heretic-Uncensored-mlx-4bit
export USER_ID ?=
export CREATOR_ID ?=

.PHONY: vllm vllm-start vllm-stop vllm-status vllm-restart vllm-test vllm-start-32b vllm-start-bg vllm-start-32b-bg vllm-logs vllm-logs-requests vllm-start-debug vllm-start-bg-debug
.PHONY: mlx mlx-start mlx-start-bg mlx-stop mlx-status mlx-restart mlx-test mlx-logs

# 统一入口：根据 MODE=fg/bg 与 MODEL 选择启动方式
vllm:
	@echo "🚀 启动 vLLM 服务（MODE=$(MODE), MODEL=$(if $(MODEL),$(MODEL),$(VLLM_MODEL)), DEBUG=$(DEBUG)）..."
	MODEL=$(if $(MODEL),$(MODEL),$(VLLM_MODEL)) DEBUG=$(DEBUG) MODE=$(MODE) ./scripts/manage_vllm.sh run

# 兼容别名
vllm-start:
	@$(MAKE) vllm MODE=fg MODEL=$(if $(MODEL),$(MODEL),$(VLLM_MODEL)) DEBUG=$(DEBUG)

vllm-start-32b:
	@$(MAKE) vllm MODE=fg MODEL=Qwen/Qwen3-32B DEBUG=$(DEBUG)

vllm-start-bg:
	@$(MAKE) vllm MODE=bg MODEL=$(if $(MODEL),$(MODEL),$(VLLM_MODEL)) DEBUG=$(DEBUG)

vllm-start-32b-bg:
	@$(MAKE) vllm MODE=bg MODEL=Qwen/Qwen3-32B DEBUG=$(DEBUG)

# 便捷 Debug 目标
vllm-start-debug:
	@$(MAKE) vllm-start DEBUG=1

vllm-start-bg-debug:
	@$(MAKE) vllm-start-bg DEBUG=1

vllm-stop:
	@echo "🛑 停止 vLLM 服务..."
	./scripts/manage_vllm.sh stop

vllm-status:
	@echo "📊 查看 vLLM 服务状态..."
	./scripts/manage_vllm.sh status

vllm-restart:
	@echo "🔄 重启 vLLM 服务（MODE=$(MODE), MODEL=$(if $(MODEL),$(MODEL),$(VLLM_MODEL)), DEBUG=$(DEBUG)）..."
	./scripts/manage_vllm.sh stop
	@echo "⏳ 等待服务完全停止..."
	@sleep 3
	MODEL=$(if $(MODEL),$(MODEL),$(VLLM_MODEL)) DEBUG=$(DEBUG) MODE=$(MODE) ./scripts/manage_vllm.sh restart

vllm-test:
	@echo "🧪 测试 vLLM 服务..."
	$(PY) scripts/check_vllm.py

vllm-logs:
	@echo "📝 查看 vLLM 服务日志..."
	./scripts/manage_vllm.sh logs

vllm-logs-requests:
	@echo "📝 查看 vLLM 请求日志..."
	./scripts/manage_vllm.sh logs-requests

mlx:
	@echo "🚀 启动 MLX 服务（MODE=$(MODE), MODEL=$(if $(MODEL),$(MODEL),$(MLX_MODEL))）..."
	MODEL=$(if $(MODEL),$(MODEL),$(MLX_MODEL)) MODE=$(MODE) ./scripts/manage_mlx.sh run

mlx-start:
	@$(MAKE) mlx MODE=fg MODEL=$(if $(MODEL),$(MODEL),$(MLX_MODEL))

mlx-start-bg:
	@$(MAKE) mlx MODE=bg MODEL=$(if $(MODEL),$(MODEL),$(MLX_MODEL))

mlx-stop:
	@echo "🛑 停止 MLX 服务..."
	./scripts/manage_mlx.sh stop

mlx-status:
	@echo "📊 查看 MLX 服务状态..."
	./scripts/manage_mlx.sh status

mlx-restart:
	@echo "🔄 重启 MLX 服务（MODE=$(MODE), MODEL=$(if $(MODEL),$(MODEL),$(MLX_MODEL))）..."
	MODEL=$(if $(MODEL),$(MODEL),$(MLX_MODEL)) MODE=$(MODE) ./scripts/manage_mlx.sh restart

mlx-test:
	@echo "🧪 测试 MLX 服务..."
	$(PY) scripts/check_vllm.py http://127.0.0.1:8080/v1

mlx-logs:
	@echo "📝 查看 MLX 服务日志..."
	./scripts/manage_mlx.sh logs

# 下载任务管理
.PHONY: pixiv-download fanbox-download fanbox-browser-script

pixiv-download:
	@echo "📥 下载 Pixiv 作者小说..."
	@echo "示例: make pixiv-download USER_ID=50235390 ARGS='--limit 20 --offset 0 --rate-limit 1 --retries 5'"
	@if [ -z "$(USER_ID)" ]; then echo "❌ 请设置 USER_ID 参数"; exit 1; fi
	$(PY) tasks/translation/src/scripts/batch_download_v1.py --user-id $(USER_ID) --output-root tasks/translation/data $(ARGS)

fanbox-download:
	@echo "📥 下载 Fanbox 创作者文章（终端版）..."
	@echo "示例: make fanbox-download CREATOR_ID=momizi813 ARGS='--max-posts 20 --sleep 0.5'"
	@if [ -z "$(CREATOR_ID)" ]; then echo "❌ 请设置 CREATOR_ID 参数"; exit 1; fi
	$(PY) tasks/translation/scripts/fanbox_download.py --creator-id $(CREATOR_ID) $(ARGS)

fanbox-browser-script:
	@echo "🌐 Chrome/Edge 控制台脚本:"
	@echo "  - 批量下载: tasks/translation/scripts/fanbox_browser_downloader.js"
	@echo "  - 单篇下载: tasks/translation/scripts/fanbox_browser_snippet.js"
	@echo "用法: 打开已登录 Fanbox 页面 -> F12 Console -> 粘贴脚本 -> 执行对应函数"

# 翻译任务管理
.PHONY: translate translate-bg translate-start translate-start-fg translate-start-bg translate-batch translate-batch-smart translate-batch-bg translate-stop translate-status translate-logs translate-logs-follow translate-attach monitor-translation

# 翻译任务（前台模式）
translate:
	@echo "📝 执行翻译任务（前台模式）..."
	./scripts/manage_translation.sh start-fg $(ARGS)

# 翻译任务（后台模式）
translate-bg:
	@echo "📝 执行翻译任务（后台模式）..."
	./scripts/manage_translation.sh start-bg $(ARGS)

# 批量翻译（前台模式）
translate-batch:
	@echo "📝 批量翻译（前台模式，自动跳过已翻译文件）..."
	@if [ -z "$(INPUT_DIR)" ] && [ -z "$(ARGS)" ]; then \
		echo "❌ 请设置 INPUT_DIR 或 ARGS"; \
		echo "示例1: make translate-batch INPUT_DIR=tasks/translation/data/pixiv/50235390"; \
		echo "示例2: make translate-batch ARGS='tasks/translation/data/pixiv/50235390 --bilingual-simple --stream'"; \
		exit 1; \
	fi
	@if [ -n "$(INPUT_DIR)" ]; then \
		./scripts/manage_translation.sh batch-fg "$(INPUT_DIR)" --bilingual-simple --stream --realtime-log $(ARGS); \
	else \
		./scripts/manage_translation.sh batch-fg $(ARGS); \
	fi

# 批量翻译（后台模式）
translate-batch-bg:
	@echo "📝 批量翻译（后台模式，自动跳过已翻译文件）..."
	@if [ -z "$(INPUT_DIR)" ] && [ -z "$(ARGS)" ]; then \
		echo "❌ 请设置 INPUT_DIR 或 ARGS"; \
		echo "示例1: make translate-batch-bg INPUT_DIR=tasks/translation/data/pixiv/50235390"; \
		echo "示例2: make translate-batch-bg ARGS='tasks/translation/data/pixiv/50235390 --bilingual-simple --stream'"; \
		exit 1; \
	fi
	@if [ -n "$(INPUT_DIR)" ]; then \
		./scripts/manage_translation.sh batch-bg "$(INPUT_DIR)" --bilingual-simple --stream --realtime-log $(ARGS); \
	else \
		./scripts/manage_translation.sh batch-bg $(ARGS); \
	fi

# 智能批量翻译（兼容旧目标名）
translate-batch-smart:
	@echo "📝 智能批量翻译（兼容目标，等价于 translate-batch）..."
	@$(MAKE) translate-batch INPUT_DIR="$(INPUT_DIR)" ARGS="$(ARGS)"

# 翻译任务（根据MODE参数）
translate-start:
	@echo "📝 启动翻译任务（MODE=$(MODE)）..."
	./scripts/manage_translation.sh start $(ARGS)

# 翻译任务（前台模式）
translate-start-fg:
	@echo "📝 启动翻译任务（前台模式）..."
	./scripts/manage_translation.sh start-fg $(ARGS)

# 翻译任务（后台模式）
translate-start-bg:
	@echo "📝 启动翻译任务（后台模式）..."
	./scripts/manage_translation.sh start-bg $(ARGS)

# 停止翻译任务
translate-stop:
	@echo "🛑 停止翻译任务..."
	./scripts/manage_translation.sh stop

# 查看翻译任务状态
translate-status:
	@echo "📊 查看翻译任务状态..."
	./scripts/manage_translation.sh status

# 查看翻译任务日志
translate-logs:
	@echo "📝 查看翻译任务日志..."
	./scripts/manage_translation.sh logs

# 实时查看翻译任务日志
translate-logs-follow:
	@echo "📝 实时查看翻译任务日志..."
	./scripts/manage_translation.sh logs-follow

# 连接到翻译任务会话
translate-attach:
	@echo "🔗 连接到翻译任务会话..."
	./scripts/manage_translation.sh attach


# 监听翻译进度
monitor-translation:
	@echo "🔍 监听翻译进度..."
	./scripts/monitor_translation.sh


# ============ Agent 任务状态 ============
.PHONY: agent-validate agent-validator-test agent-bootstrap

agent-validate:
	$(PY) scripts/validate_agent_tasks.py

# 文档漂移闸门:基线数字==实际计数、组件路径存在
docs-drift:
	$(PY) scripts/check_docs_drift.py

agent-validator-test:
	$(PY) -m unittest scripts.validate_agent_tasks_test scripts.bootstrap_agent_task_test

# 用法: make agent-bootstrap TASK_ID=gh-12-slug BRANCH=feat/x TITLE="..." OBJECTIVE="..." [ISSUE=12]
agent-bootstrap:
	$(PY) scripts/bootstrap_agent_task.py --task-id "$(TASK_ID)" --branch "$(BRANCH)" \
		--title "$(TITLE)" --objective "$(OBJECTIVE)" $(if $(ISSUE),--issue $(ISSUE))


# ============ 候选导入(新架构) ============
.PHONY: legacy-import import-result export-job translate-bundle seed-entities ingest-user translate-exec translate-user entity-review-import entity-review-list entity-review-approve entity-review-dismiss

# revision → job bundle(供执行器消费)。用法: make export-job REVISION=rev.json OUT=job.json STORE=...
# STORE 必传(闭环前置):同步把源 revision 幂等入库,import-result 才解析得到 revision shard。
export-job:
	@test -n "$(STORE)" || { echo "export-job 需要 STORE=<ArtifactStore 根目录>"; exit 2; }
	$(PY) tasks/translation/src/core/task_export.py --revision "$(REVISION)" --out "$(OUT)" --store "$(STORE)" $(if $(CONTEXT),--context "$(CONTEXT)") $(if $(TASK_TYPE),--task-type $(TASK_TYPE))

# 源目录+document → job bundle(一步)。用法: make translate-bundle SOURCE=dir PROVIDER=pixiv DOCUMENT=pixiv:18330282:27466576 OUT=job.json STORE=...
# STORE 必传(闭环前置):同步把源 revision 幂等入库,import-result 才解析得到 revision shard。
translate-bundle:
	@test -n "$(STORE)" || { echo "translate-bundle 需要 STORE=<ArtifactStore 根目录>"; exit 2; }
	$(PY) tasks/translation/src/core/task_export.py --source-dir "$(SOURCE)" --provider "$(PROVIDER)" --document "$(DOCUMENT)" --out "$(OUT)" --store "$(STORE)" $(if $(CONTEXT),--context "$(CONTEXT)") $(if $(ENTITY_STORE),--entity-store "$(ENTITY_STORE)")

# 人工规则 → 实体库播种。用法: make seed-entities ENTITY_STORE=... LEVEL=creator KEY=pixiv:50235390 RULES=rules.txt
seed-entities:
	$(PY) tasks/translation/src/core/entity_store.py --store "$(ENTITY_STORE)" --scope-level "$(LEVEL)" $(if $(KEY),--scope-key "$(KEY)") --rules "$(RULES)" $(if $(STATUS),--status $(STATUS))

# 通用端到端:一个作者 → 实际翻译 → 发布 + 渲染 + 合并整本(executor 可插拔)。
# 用法: make translate-user PROVIDER=pixiv SOURCE=data/pixiv/18330282 STORE=... RENDER=... [EXECUTOR=openrouter] [LIMIT=1] [BILINGUAL=...] [MODEL=x-ai/grok-4.3]
translate-user:
	@test -n "$(PROVIDER)" && test -n "$(SOURCE)" && test -n "$(STORE)" || { echo "translate-user 需要 PROVIDER= SOURCE= STORE="; exit 2; }
	$(PY) tasks/translation/src/core/translate_user.py --provider "$(PROVIDER)" --source-dir "$(SOURCE)" --store "$(STORE)" $(if $(RENDER),--render-dir "$(RENDER)") $(if $(BILINGUAL),--bilingual-dir "$(BILINGUAL)") $(if $(EXECUTOR),--executor "$(EXECUTOR)") $(if $(MODEL),--model "$(MODEL)") $(if $(LIMIT),--limit $(LIMIT))

# OpenRouter Grok 执行器:job bundle → 实际翻译 → result.json(需 OPENROUTER_API_KEY)。
# 用法: make translate-exec BUNDLE=job.json OUT=result.json [MODEL=x-ai/grok-4.3]
translate-exec:
	@test -n "$(BUNDLE)" && test -n "$(OUT)" || { echo "translate-exec 需要 BUNDLE= OUT="; exit 2; }
	$(PY) tasks/translation/src/core/openrouter_executor.py --bundle "$(BUNDLE)" --out "$(OUT)" $(if $(MODEL),--model "$(MODEL)")

# 端到端批量编排:用户现有 source+bilingual → 新架构 → 发布 + 渲染。
# 用法: make ingest-user PROVIDER=pixiv SOURCE=data/pixiv/53230930 BILINGUAL=data/pixiv/53230930_bilingual STORE=... RENDER=...
ingest-user:
	@test -n "$(PROVIDER)" && test -n "$(SOURCE)" && test -n "$(BILINGUAL)" && test -n "$(STORE)" || { echo "ingest-user 需要 PROVIDER= SOURCE= BILINGUAL= STORE="; exit 2; }
	$(PY) tasks/translation/src/core/pipeline_ingest.py --provider "$(PROVIDER)" --source-dir "$(SOURCE)" --bilingual-dir "$(BILINGUAL)" --store "$(STORE)" $(if $(RENDER),--render-dir "$(RENDER)")

# Entity Linking review 队列(#83 P1b-2)。抽取(外部)产 PROPOSALS JSON → 链接入队 → 人工裁决。
# 导入: make entity-review-import PROPOSALS=p.json ENTITY_STORE=... QUEUE=... DOCUMENT=pixiv:50235390:12430834
entity-review-import:
	$(PY) tasks/translation/src/core/entity_review.py import --proposals "$(PROPOSALS)" --entity-store "$(ENTITY_STORE)" --queue "$(QUEUE)" --document "$(DOCUMENT)" $(if $(THRESHOLD),--threshold $(THRESHOLD))
# 列待裁决: make entity-review-list QUEUE=...
entity-review-list:
	$(PY) tasks/translation/src/core/entity_review.py list --queue "$(QUEUE)"
# 裁决: make entity-review-approve REVIEW_ID=... ENTITY_STORE=... QUEUE=... DOCUMENT=... BY=houxinli [LOCKED=1]
entity-review-approve:
	$(PY) tasks/translation/src/core/entity_review.py approve --review-id "$(REVIEW_ID)" --entity-store "$(ENTITY_STORE)" --queue "$(QUEUE)" --document "$(DOCUMENT)" --by "$(BY)" $(if $(LOCKED),--locked)
entity-review-dismiss:
	$(PY) tasks/translation/src/core/entity_review.py dismiss --review-id "$(REVIEW_ID)" --entity-store "$(ENTITY_STORE)" --queue "$(QUEUE)" --document "$(DOCUMENT)" --by "$(BY)"

# 存量 bilingual → legacy candidate。用法: make legacy-import PROVIDER=fanbox SOURCE=... BILINGUAL=... LABEL=... STORE=...
legacy-import:
	$(PY) tasks/translation/src/core/legacy_import.py --provider "$(PROVIDER)" \
		--source "$(SOURCE)" --bilingual "$(BILINGUAL)" --label "$(LABEL)" --store "$(STORE)"

# Task+Result → candidate。用法: make import-result TASK=task.json RESULT=result.json STORE=...
import-result:
	$(PY) tasks/translation/src/core/result_import.py --task "$(TASK)" --result "$(RESULT)" --store "$(STORE)"


# ============ 健身记录 (tasks/fitness) ============
FITNESS_PY := conda run -n $(CONDA_ENV) python tasks/fitness/src/cli.py
export EXERCISE ?=

.PHONY: fitness-parse fitness-exercises fitness-progress fitness-chart fitness-charts

# 解析自由文本日志 -> data/derived/sets.csv（含无法解析行的样例）
fitness-parse:
	$(FITNESS_PY) parse --show-issues 10

# 列出归一化后的动作及训练次数
fitness-exercises:
	$(FITNESS_PY) exercises

# 单个动作的力量进展（文本表）：make fitness-progress EXERCISE=坐姿杠铃推举
fitness-progress:
	$(FITNESS_PY) progress "$(EXERCISE)"

# 单个动作的进展曲线 SVG：make fitness-chart EXERCISE=bench_press
fitness-chart:
	$(FITNESS_PY) chart "$(EXERCISE)"

# 为所有动作（>=6 次）生成进展曲线 SVG 到 data/derived/charts/
fitness-charts:
	$(FITNESS_PY) chart-all --min-sessions 6
