SHELL := /usr/bin/bash

CONDA_ENV := llm
PY := conda run -n $(CONDA_ENV) python

.PHONY: vllm-start vllm-stop vllm-status vllm-test

# vLLM 服务管理
vllm-start:
	@echo "🚀 启动 vLLM 服务..."
	./scripts/manage_vllm.sh start-bg

vllm-stop:
	@echo "🛑 停止 vLLM 服务..."
	./scripts/manage_vllm.sh stop

vllm-status:
	@echo "📊 查看 vLLM 服务状态..."
	./scripts/manage_vllm.sh status

vllm-test:
	@echo "🧪 测试 vLLM 服务..."
	$(PY) scripts/check_vllm.py

# 翻译任务
translate:
	@echo "📝 执行翻译任务..."
	$(PY) tasks/translation/scripts/test_translation.py --input tasks/translation/data/input/input_1.txt --output tasks/translation/data/output/translated.txt --model Qwen/Qwen3-32B-AWQ
