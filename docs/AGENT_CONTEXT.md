# GenAI Playground - Agent 对话上下文

## 🎯 项目概述

这是一个在 4× RTX 6000 Ada 服务器上部署本地机器翻译服务的项目。项目使用 vLLM + Qwen3-32B-AWQ 技术栈，实现了日语到中文的翻译功能，支持批量翻译和质量检测。

## 🏗️ 项目结构

```
genai-playground/
├── Makefile                    # 主要构建文件
├── README.md                   # 项目入口文档
├── .gitignore                  # Git 忽略文件
├── docs/                       # 项目文档目录
│   ├── journal/                # 按日期组织的项目日志
│   │   ├── README.md           # Journal 索引
│   │   ├── 2024-08-28.md       # 项目启动
│   │   ├── 2024-09-01.md       # 项目成果
│   │   ├── 2025-09-02.md       # 翻译服务与脚本收敛
│   │   ├── 2025-09-03.md       # vLLM 前台可观测+tmux后台
│   │   ├── 2025-09-05.md       # 翻译脚本重构与重复检测
│   │   ├── 2025-09-04.md       # 翻译脚本增强与配置优化
│   │   └── technical-docs.md   # 技术文档补充
│   └── AGENT_CONTEXT.md        # Agent 对话上下文（本文件）
├── .cursor/                    # Cursor 配置目录
│   └── rules/                  # Cursor 规则文件
│       └── organize-progress.mdc # 工作流程规则
├── scripts/                    # 通用脚本目录
│   ├── manage_vllm.sh         # vLLM 服务管理脚本
│   ├── serve_vllm.sh          # vLLM 服务启动脚本
│   ├── check_vllm.py          # vLLM 健康检查脚本
│   └── monitor_translation.sh  # 翻译进度监控脚本
├── tasks/translation/          # 翻译任务目录
│   ├── src/                   # 模块化翻译脚本源码
│   │   ├── core/              # 核心功能模块
│   │   │   ├── translator.py  # 翻译核心逻辑
│   │   │   ├── quality_checker.py # 质量检测
│   │   │   ├── streaming_handler.py # 流式处理
│   │   │   └── pipeline.py    # 翻译流水线
│   │   ├── cli/               # 命令行接口
│   │   └── translate_v3.py    # 主翻译脚本
│   ├── translate              # 便捷调用器
│   ├── data/                  # 数据目录
│   │   ├── input/             # 输入文件
│   │   ├── output/            # 输出文件
│   │   ├── samples/           # 示例文件
│   │   ├── pixiv/             # Pixiv 小说数据
│   │   └── terminology.txt    # 术语对照表
│   ├── docs/                  # 翻译任务文档
│   │   └── repetition-detection.md # 重复检测功能说明
│   └── logs/                  # 翻译任务日志
└── logs/                      # 主项目日志目录
```

## 🚀 快速开始

### 1. 环境配置
```bash
# 激活 conda 环境
conda activate llm

# 设置 CUDA 环境变量
export LD_LIBRARY_PATH=~/.local/lib:$LD_LIBRARY_PATH
export LIBRARY_PATH=~/.local/lib:${LIBRARY_PATH:-}
export CUDA_HOME=/usr/local/cuda-12.4
export PATH=$CUDA_HOME/bin:$PATH

# 设置 HuggingFace 缓存
export HF_HOME=/path/to/your/hf_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
export HUGGINGFACE_HUB_VERBOSITY=debug
export HF_HUB_DISABLE_PROGRESS_BARS=0
```

### 2. 启动服务
```bash
# 前台启动（推荐首次使用）
make vllm-start

# 后台启动
make vllm-start-bg

# 启动 32B 完整模型
make vllm-start-32b

# 调试模式启动
make vllm-start-debug
```

### 3. 测试翻译
```bash
# 基本翻译测试
make vllm-test

# 批量翻译（需要指定输入目录）
make translate-batch INPUT_DIR=tasks/translation/data/pixiv/50235390

# 智能批量翻译（跳过质量良好的文件）
make translate-batch-smart INPUT_DIR=tasks/translation/data/pixiv/50235390
```

## 🔧 关键技术配置

### CUDA 库链接解决方案
```bash
# 创建用户级符号链接
mkdir -p ~/.local/lib
ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so ~/.local/lib/libcuda.so

# 设置环境变量
export LD_LIBRARY_PATH=~/.local/lib:$LD_LIBRARY_PATH
export LIBRARY_PATH=~/.local/lib:${LIBRARY_PATH:-}
export CUDA_HOME=/usr/local/cuda-12.4
```

### vLLM 配置
```bash
# 注意力后端
export VLLM_ATTENTION_BACKEND=XFORMERS

# 显存利用率
export VLLM_WORKER_GPU_MEM_FRACTION=0.90

# 允许长序列
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1

# 日志配置
export VLLM_LOGGING_LEVEL=INFO
export VLLM_LOGGING_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

### 服务配置
- **默认模型**: Qwen/Qwen3-32B-AWQ
- **完整模型**: Qwen/Qwen3-32B
- **端口**: 8000
- **AWQ 最大长度**: 40960
- **32B 最大长度**: 32768
- **TP 大小**: AWQ=2, 32B=4
- **显存利用率**: 90%

## 🚨 常见问题及解决方案

### 1. CUDA 库链接错误
```
/usr/bin/ld: cannot find -lcuda: No such file or directory
```
**解决**: 创建符号链接并设置环境变量（见上方配置）

### 2. 服务状态误判
```
manage_vllm.sh status 显示未运行但实际运行中
```
**解决**: 使用 `python scripts/check_vllm.py` 进行权威检查

### 3. 模型 404 错误
```
404 The model Qwen/Qwen3-32B does not exist
```
**解决**: 确保服务端和客户端模型名一致，使用 `-m` 参数显式指定

### 4. 输出内容不合规
```
译文输出夹带原文与 <think> 思考内容
```
**解决**: 使用通用翻译脚本，输出仅保留译文，完整内容写入日志

### 5. 32B 显存不足
```
CUDA OOM: out of memory
```
**解决**: 使用 32B-AWQ 量化版本，或调整 TP_SIZE 和显存利用率

### 6. 后台运行无进度条
```
tqdm 进度条不显示
```
**解决**: 使用前台模式 `make vllm-start` 或 tmux 后台模式 `make vllm-start-bg`

## 📊 项目成果

### 成功功能
- ✅ 本地机器翻译服务（日语→中文）
- ✅ 完整的服务管理系统（前台/后台模式）
- ✅ 批量翻译功能（Pixiv 小说）
- ✅ 翻译质量检测和自动重试
- ✅ 双语对照输出模式
- ✅ 流式输出和实时日志
- ✅ 时间戳日志系统
- ✅ 问题解决记录

### 测试结果
- ✅ `こんにちは、世界。` → `你好，世界。`
- ✅ `今日は良い天気ですね。` → `今天天气真好。`
- ✅ `私は日本語を勉強しています。` → `我正在学习日语。`
- ✅ 长文本翻译（1000+字符）
- ✅ 专业术语翻译
- ✅ 语序处理优化

## 🎯 当前任务状态

### 已完成
- [x] 环境配置和问题解决
- [x] vLLM 服务部署（AWQ + 32B）
- [x] 翻译功能测试
- [x] 批量翻译脚本开发
- [x] 翻译质量检测机制
- [x] 前台/后台运行模式
- [x] 项目文档整理（Journal 结构）

### 进行中
- [ ] 批量翻译剩余文章（约67篇）
- [ ] 翻译质量评估机制
- [ ] 性能调优

### 待办
- [ ] 评估 Sakura-13B-Galgame 模型
- [ ] 提供完整 32B 下载命令
- [ ] example_1 使用 32B-AWQ 完整测试

## 🔗 相关文档

- **[Journal 索引](docs/journal/README.md)** - 按日期组织的项目日志
- **[2025-09-04 翻译脚本增强](docs/journal/2025-09-04.md)** - 最新功能更新
- **[2025-09-03 vLLM 可观测性](docs/journal/2025-09-03.md)** - 前台/后台运行方案
- **[2025-09-02 服务收敛](docs/journal/2025-09-02.md)** - 关键问题解决
- **[技术文档](docs/journal/technical-docs.md)** - 详细技术配置
- **[项目成果](docs/journal/2024-09-01.md)** - 项目成果总结

## 💡 给新 Agent 的建议

1. **优先查看 Journal**: 项目采用按日期组织的 Journal 结构，先查看相关日期的记录
2. **使用管理脚本**: 项目提供了便捷的 Makefile 和管理脚本，避免直接操作
3. **检查环境变量**: CUDA 环境配置是关键，确保环境变量正确设置
4. **查看日志**: 使用时间戳日志系统，便于调试和问题追踪
5. **用户级解决方案**: 优先使用用户级解决方案，避免影响其他用户
6. **模型选择**: 默认使用 AWQ 模型，32B 完整模型仅用于离线评估
7. **前台 vs 后台**: 首次启动使用前台模式观察进度，稳定后使用后台模式
8. **翻译质量**: 使用质量检测机制，自动重试失败的翻译

## 🔧 常用命令

### 服务管理
```bash
make vllm-start          # 前台启动 AWQ
make vllm-start-32b      # 前台启动 32B
make vllm-start-bg       # 后台启动 AWQ
make vllm-start-bg-debug # 后台调试启动
make vllm-stop           # 停止服务
make vllm-restart        # 重启服务
make vllm-status         # 查看状态
make vllm-logs           # 查看日志
```

### 翻译任务
```bash
make translate-batch INPUT_DIR=path/to/input
make translate-batch-smart INPUT_DIR=path/to/input
python tasks/translation/scripts/test_translation.py --input input.txt --output output.txt
```

### 监控和调试
```bash
python scripts/check_vllm.py
tmux attach -t vllm
gpustat
nvidia-smi
```

## 📋 工作流程规则

当用户说"整理进展"时，请按照 `.cursor/rules/organize-progress.mdc` 中的详细流程执行：

1. **检查当前状态** - 查看 git 状态和变更
2. **分析变更内容** - 识别主要变更类别
3. **更新项目日志** - 在 `docs/journal/` 下创建/更新日志
4. **更新相关文档** - 更新 AGENT_CONTEXT.md 等
5. **清理敏感信息** - 移除机器路径、用户名等
6. **准备 commit message** - 按模板格式准备
7. **执行提交** - 完成 git commit

详细规则请参考：`.cursor/rules/organize-progress.mdc`

---

**项目状态**: ✅ 运行中  
**最后更新**: 2025-09-05