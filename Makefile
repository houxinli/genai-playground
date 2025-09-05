SHELL := /usr/bin/bash

CONDA_ENV := llm
# 使用无缓冲输出，确保流式内容实时打印
PY := conda run -n $(CONDA_ENV) python -u

# 支持参数透传
export DEBUG ?= 0
export MODE ?= bg
export MODEL ?= Qwen/Qwen3-32B-AWQ

.PHONY: vllm vllm-start vllm-stop vllm-status vllm-restart vllm-test vllm-start-32b vllm-start-bg vllm-start-32b-bg vllm-logs vllm-logs-requests vllm-start-debug vllm-start-bg-debug

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

# 翻译任务
translate:
	@echo "📝 执行翻译任务..."
	$(PY) tasks/translation/scripts/test_translation.py --input tasks/translation/data/input/input_1.txt --output tasks/translation/data/output/translated.txt --model Qwen/Qwen3-32B-AWQ

# 监听翻译进度
monitor-translation:
	@echo "🔍 监听翻译进度..."
	./scripts/monitor_translation.sh

# 批量翻译（带实时日志和质量检测）
translate-batch:
	@echo "📝 开始批量翻译..."
	@echo "请指定输入目录，例如：make translate-batch INPUT_DIR=tasks/translation/data/pixiv/50235390"
	@if [ -z "$(INPUT_DIR)" ]; then echo "❌ 请设置 INPUT_DIR 参数"; exit 1; fi
	PYTHONUNBUFFERED=1 stdbuf -oL -eL $(PY) tasks/translation/scripts/translate_pixiv_v1.py $(INPUT_DIR) --model Qwen/Qwen3-32B --max-context-length 32768 --mode full --temperature 0.0 --frequency-penalty 0.0 --presence-penalty 0.0 --retries 1 --retry-wait 1.0 --fallback-on-context --terminology-file tasks/translation/data/terminology.txt --sample-file tasks/translation/data/samples/sample_bilingual.txt --preface-file tasks/translation/data/preface_bilingual.txt --log-dir tasks/translation/logs --bilingual --stream --realtime-log --overwrite

# 批量翻译（带质量检测，跳过已翻译良好的文件）
translate-batch-smart:
	@echo "📝 开始智能批量翻译（跳过质量良好的文件）..."
	@echo "请指定输入目录，例如：make translate-batch-smart INPUT_DIR=tasks/translation/data/pixiv/50235390"
	@if [ -z "$(INPUT_DIR)" ]; then echo "❌ 请设置 INPUT_DIR 参数"; exit 1; fi
	PYTHONUNBUFFERED=1 stdbuf -oL -eL $(PY) tasks/translation/scripts/translate_pixiv_v1.py $(INPUT_DIR) --model Qwen/Qwen3-32B --max-context-length 32768 --mode full --temperature 0.0 --frequency-penalty 0.0 --presence-penalty 0.0 --retries 1 --retry-wait 1.0 --fallback-on-context --terminology-file tasks/translation/data/terminology.txt --sample-file tasks/translation/data/samples/sample_bilingual.txt --preface-file tasks/translation/data/preface_bilingual.txt --log-dir tasks/translation/logs --bilingual --stream --realtime-log
