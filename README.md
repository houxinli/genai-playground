# GenAI Playground - 使用指南

## 📁 项目结构

```
genai-playground/
├── Makefile                       # 主要构建文件
├── README.md                      # 项目说明（本文件）
├── .gitignore                     # Git 忽略文件
├── docs/                          # 项目文档目录
│   ├── README.md                  # 文档导航（Journal 为唯一历史入口）
│   └── JOURNAL.md                 # 技术博客式时间线/历史记录
├── scripts/                       # 通用脚本目录
│   ├── manage_vllm.sh             # vLLM 服务管理脚本
│   ├── serve_vllm.sh              # vLLM 服务启动脚本
│   └── check_vllm.py              # 通过 /v1/models 检查服务健康
├── tasks/translation/             # 翻译任务目录
│   ├── scripts/                   # 翻译相关脚本
│   │   ├── test_translation.py    # 通用翻译脚本（含完整日志落盘）
│   │   └── count_tokens.py        # Token 计数工具（文件/目录）
│   ├── data/                      # 数据目录
│   │   ├── input/                 # 输入文件（已在 .gitignore 忽略）
│   │   ├── output/                # 输出文件（已在 .gitignore 忽略）
│   │   └── samples/               # few-shot 示例
│   └── logs/                      # 翻译任务日志（完整 Prompt/Response）
└── logs/                          # 服务日志目录
```

## 📚 文档导航

### 快速开始
- **[README.md](README.md)** - 项目概述和使用指南（本文件）

### 详细文档
- **[📖 文档导航](docs/README.md)** - 文档索引（Journal/Agent Context）
- **[项目日志（Journal）](docs/JOURNAL.md)** - 技术博客式时间线/历史记录
- **[Agent 对话上下文](docs/AGENT_CONTEXT.md)** - 新会话 Prompt/上下文

### 任务文档
- **[翻译任务](tasks/translation/docs/README.md)** - 翻译功能使用指南

## 🚀 快速开始

### 启动 vLLM 服务

**方法1: 使用 Makefile（推荐）**
```bash
# 前台启动（带日志记录）
make vllm-start

# 后台启动
make vllm-start-bg

# 查看状态
make vllm-status

# 查看日志
make vllm-logs

# 停止服务
make vllm-stop

# 测试翻译
make vllm-test
```

**方法2: 直接使用管理脚本**
```bash
# 前台启动
./scripts/manage_vllm.sh start

# 后台启动
./scripts/manage_vllm.sh start-bg

# 查看状态
./scripts/manage_vllm.sh status

# 查看日志
./scripts/manage_vllm.sh logs

# 停止服务
./scripts/manage_vllm.sh stop

# 测试翻译
./scripts/manage_vllm.sh test
```

## 📝 日志管理

- **时间戳日志**: `logs/vllm-YYYYMMDD-HHMMSS.log`
- **最新日志链接**: `logs/latest.log`
- **查看实时日志**: `./scripts/manage_vllm.sh logs`
- **查看所有日志**: `./scripts/manage_vllm.sh logs-all`
- **清理旧日志**: `./scripts/manage_vllm.sh clean-logs`

## 🔧 环境配置

服务会自动设置以下环境变量：
- `LD_LIBRARY_PATH`: 包含用户 CUDA 库路径
- `LIBRARY_PATH`: 包含用户库路径
- `CUDA_HOME`: CUDA 安装路径
- `PATH`: 包含 CUDA 工具路径

## 🧪 测试翻译

服务启动后，可以运行通用脚本（带自动日志）：
```bash
python tasks/translation/scripts/test_translation.py \
  -i tasks/translation/data/samples/example_2_3_input.txt \
  -o tasks/translation/data/output/example_2_3_zh.txt \
  -m Qwen/Qwen3-32B-AWQ
```

或使用 Makefile 目标：
```bash
make translate
```


