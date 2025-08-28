## 学习与助教设定（vLLM + LLM 实践）

### 角色与目标
- 你：实践者/研究者，目标是在 4× RTX 6000 服务器上系统体验 LLM 推理与微调，并掌握核心工程栈（vLLM、HF 生态、LoRA/QLoRA、分布式/并行概念）。
- 我：助教 + 执行助手。职责：
  - 将操作脚本化、可复现；
  - 每一步解释“做什么/为什么/出错如何排查”；
  - 设计小测与任务，让你循序掌握关键点；
  - 控制变更最小原则，保护环境稳定。

### 授课节奏（建议）
1. vLLM 推理与服务
2. 指令模型的加载与推理对照（transformers vs vLLM）
3. QLoRA 微调最小闭环（小样本）
4. 评估与部署（OpenAI 兼容接口 / 并发 / 流式）
5. 扩展：VLM 与视觉生成/微调（可选）

### 小测·第1组（vLLM 基础）
1. 问：vLLM 相比 transformers.pipeline 推理的主要优势有哪些？适合哪些场景？
2. 问：在多 GPU 上，vLLM 的 `--tensor-parallel-size` 起什么作用？与显存/吞吐的关系？
3. 问：KV Cache 是什么？为何能大幅提升长对话/长上下文推理吞吐？
4. 实操：启动 vLLM（7B 指令模型），用 `scripts/chat_vllm.py` 访问一次，并把返回的 JSON 与文本回答粘贴到本文件末尾。

（请在你作答后，将答案直接写入本文件 “作答区” 部分，并 commit）

### 小测·第1组·作答区
- 1) 你的回答：
- 2) 你的回答：
- 3) 你的回答：
- 4) 调用结果（可粘贴片段，或写明已完成）：

### 里程碑与复盘
- 里程碑A：成功用 vLLM 部署并通过 OpenAI 兼容接口访问，了解并发、流式。
- 里程碑B：完成一次 QLoRA SFT，理解 Adapter 权重合并与推理加载方式。
- 每个里程碑后，写 3-5 行复盘：遇到的问题/解决方法/仍有疑问。

### 知识点补充（vLLM + 模型生态）

#### vLLM 接口能力
- **OpenAI 兼容 API**: `/v1/chat/completions`，支持流式、并发、温度等参数
- **原生 Python**: `vllm.LLM` 类，直接加载模型进行推理
- **命令行**: `vllm.inference` 用于单次推理
- **批处理**: `vllm.batch` 用于批量推理

#### 为什么使用 OpenAI 兼容接口？
- 生态兼容：已有代码/工具无需修改
- 标准化：统一的参数格式和响应结构
- 部署便利：可直接替换 OpenAI 服务

#### 模型排行榜
- **Hugging Face Open LLM Leaderboard**: 开源模型性能对比
- **LMSYS Chatbot Arena**: 聊天机器人对战排名
- **当前最强 7B**: Qwen2.5-7B-Instruct、Llama-3.1-8B-Instruct

#### 硬件要求
- **推理 7B**: 单张 RTX 6000 即可（量化后）
- **训练 7B**: 
  - 全参数：8× A100 80GB+
  - LoRA/QLoRA：1-2张 RTX 6000
- **M1 Pro MacBook**: 可运行量化后的 7B（llama.cpp、MLX、ollama）


