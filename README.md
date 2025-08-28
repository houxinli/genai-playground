## 本仓库说明

本仓库用于在 4× RTX 6000 Ada 的服务器上体验当前主流大模型/视觉模型的部署、推理与微调流程。配套提供可复现的脚本、Makefile 目标与运行记录（见 `RUNBOOK.md`）。

### 快速开始

- 预置假设：已安装 conda，已通过 `conda create -n llm python=3.10` 创建环境，并安装 PyTorch cu124 与常用依赖。
- 常用命令：

```bash
make test-gpu           # 检测 GPU 与 PyTorch CUDA
make deps-llm           # 安装/更新 LLM 常用依赖
make vllm               # 安装 vLLM（与当前 PyTorch 匹配）
make serve-vllm         # 启动 vLLM OpenAI 兼容服务
make chat-vllm          # 调用本地 vLLM 服务进行对话
```

更多细节与逐步路线请见 `RUNBOOK.md`。


