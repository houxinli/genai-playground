SHELL := /bin/bash

CONDA_ENV := llm
# 使用无缓冲输出，确保流式内容实时打印
PY := conda run -n $(CONDA_ENV) python -u

# 支持参数透传
export DEBUG ?= 0
export MODE ?= bg
export MODEL ?= Qwen/Qwen3-32B-AWQ
export USER_ID ?=
export CREATOR_ID ?=

.PHONY: vllm vllm-start vllm-stop vllm-status vllm-restart vllm-test vllm-start-32b vllm-start-bg vllm-start-32b-bg vllm-logs vllm-logs-requests vllm-start-debug vllm-start-bg-debug
.PHONY: mlx mlx-start mlx-start-bg mlx-stop mlx-status mlx-restart mlx-test mlx-logs

# 统一入口：根据 MODE=fg/bg 与 MODEL 选择启动方式
vllm:
	@echo "🚀 启动 vLLM 服务（MODE=$(MODE), MODEL=$(MODEL), DEBUG=$(DEBUG)）..."
	MODEL=$(MODEL) DEBUG=$(DEBUG) MODE=$(MODE) ./scripts/manage_vllm.sh run

# 兼容别名
vllm-start:
	@$(MAKE) vllm MODE=fg MODEL=$(MODEL) DEBUG=$(DEBUG)

vllm-start-32b:
	@$(MAKE) vllm MODE=fg MODEL=Qwen/Qwen3-32B DEBUG=$(DEBUG)

vllm-start-bg:
	@$(MAKE) vllm MODE=bg MODEL=$(MODEL) DEBUG=$(DEBUG)

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
	@echo "🔄 重启 vLLM 服务（MODE=$(MODE), MODEL=$(MODEL), DEBUG=$(DEBUG)）..."
	./scripts/manage_vllm.sh stop
	@echo "⏳ 等待服务完全停止..."
	@sleep 3
	MODEL=$(MODEL) DEBUG=$(DEBUG) MODE=$(MODE) ./scripts/manage_vllm.sh restart

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
	@echo "🚀 启动 MLX 服务（MODE=$(MODE), MODEL=$(MODEL)）..."
	MODEL=$(MODEL) MODE=$(MODE) ./scripts/manage_mlx.sh run

mlx-start:
	@$(MAKE) mlx MODE=fg MODEL=$(MODEL)

mlx-start-bg:
	@$(MAKE) mlx MODE=bg MODEL=$(MODEL)

mlx-stop:
	@echo "🛑 停止 MLX 服务..."
	./scripts/manage_mlx.sh stop

mlx-status:
	@echo "📊 查看 MLX 服务状态..."
	./scripts/manage_mlx.sh status

mlx-restart:
	@echo "🔄 重启 MLX 服务（MODE=$(MODE), MODEL=$(MODEL)）..."
	MODEL=$(MODEL) MODE=$(MODE) ./scripts/manage_mlx.sh restart

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
