## 路线图（LLM + 视觉）

1. 环境与依赖
   - 创建 `llm` conda 环境（Python 3.10）。
   - 安装 PyTorch cu124、transformers/accelerate/datasets/peft/bitsandbytes。
   - 安装 vLLM（与已装 PyTorch 匹配）。
2. 文本模型
   - vLLM 部署主流 7B 指令模型（如 `Qwen2.5-7B-Instruct` 或 `Llama-3.1-8B-Instruct`）。
   - OpenAI 兼容推理服务联调（流式/并发）。
   - QLoRA 微调最小复现场景（少量样本），评估 SFT 效果。
3. 视觉模型
   - 安装 diffusers 与 SDXL/Flux 推理依赖。
   - 跑通单图/多卡推理（fp16/bf16，xFormers/Flash-Attn 可选）。
   - LoRA 微调一个小场景（风格/角色）。
4. VLM（可选）
   - LLaVA/InternVL 任一模型推理与最小训练样例。

## 命令速查

```bash
# 0) 检测 GPU / PyTorch
make test-gpu

# 1) 安装/更新 LLM 依赖
make deps-llm

# 2) 安装 vLLM
make vllm

# 3) 运行 vLLM 服务 + 调用
make serve-vllm
make chat-vllm
```

## 运行记录（节选）

- 驱动/CUDA: `NVIDIA-SMI 570.124.06`, CUDA runtime 12.8；PyTorch 2.6.0+cu124 已安装。
- GPU: 4× RTX 6000 Ada, 49GB 显存。


