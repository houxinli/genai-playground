SHELL := /usr/bin/bash

CONDA_ENV := llm
PY := conda run -n $(CONDA_ENV) python
PIP := conda run -n $(CONDA_ENV) python -m pip

.PHONY: test-gpu deps-llm vllm serve-vllm chat-vllm safe-test-gpu safe-show-vllm safe-report-sizes env-setup env-export

# 环境管理
env-setup:
	@echo "🚀 设置 vLLM 运行环境..."
	source scripts/env_setup.sh

env-export:
	@echo "📦 导出环境配置..."
	conda env export -n $(CONDA_ENV) > environment-llm.yml
	$(PIP) freeze > requirements-llm.txt
	@echo "✅ 环境配置已导出到 environment-llm.yml 和 requirements-llm.txt"

# 现有命令
test-gpu:
	$(PY) scripts/test_gpu.py

safe-test-gpu:
	./scripts/run_safe.sh $(PY) scripts/test_gpu.py

safe-show-vllm:
	./scripts/run_safe.sh $(PY) -m pip show vllm

safe-report-sizes:
	./scripts/run_safe.sh $(PY) scripts/report_sizes.py

deps-llm:
	$(PIP) install -U pip wheel setuptools
	$(PIP) install -U torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
	$(PIP) install -U transformers accelerate datasets peft sentencepiece tiktoken evaluate bitsandbytes

vllm:
	# 说明：默认不装依赖(--no-deps)，以避免 vLLM 强制升级/替换已装的 PyTorch 2.6.0+cu124。
	# 策略：先尝试主线版本范围，失败时再回退到兼容 Torch 2.6 的版本。
	$(PIP) install -U "vllm>=0.9.0,<0.11.0" --no-deps || \
	$(PIP) install -U vllm==0.6.2 --no-deps

serve-vllm:
	@echo "🚀 启动 vLLM 服务..."
	@echo "💡 提示：首次运行前请先执行 'make env-setup'"
	./scripts/serve_vllm.sh

chat-vllm:
	$(PY) scripts/chat_vllm.py


