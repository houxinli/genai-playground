# GenAI Playground - Agent 对话上下文

## 🎯 项目概述

这是一个在 4× RTX 6000 Ada 服务器上部署本地机器翻译服务的项目。项目使用 vLLM + Qwen3-4B 技术栈，实现了日语到中文的翻译功能。

## 🏗️ 项目结构

```
genai-playground/
├── Makefile                    # 主要构建文件
├── README.md                   # 项目入口文档
├── .gitignore                  # Git 忽略文件
├── docs/                       # 项目文档目录
│   ├── SETUP_GUIDE.md         # 完整的环境配置和问题解决指南
│   ├── LEARNING.md            # 技术知识点和学习笔记
│   └── PROJECT_SUMMARY.md     # 项目总结和未来规划
├── scripts/                    # 通用脚本目录
│   ├── manage_vllm.sh         # vLLM 服务管理脚本
│   ├── serve_vllm.sh          # vLLM 服务启动脚本
│   └── ...                    # 其他通用脚本
├── tasks/translation/          # 翻译任务目录
│   ├── scripts/               # 翻译相关脚本
│   ├── docs/                  # 翻译任务文档
│   ├── data/                  # 数据目录
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
```

### 2. 启动服务
```bash
# 使用管理脚本启动
make vllm-start

# 或直接启动
./scripts/manage_vllm.sh start
```

### 3. 测试翻译
```bash
# 测试翻译功能
make vllm-test
```

## 🔧 关键技术配置

### CUDA 库链接解决方案
```bash
# 创建用户级符号链接
ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 ~/.local/lib/libcuda.so

# 设置环境变量
export LD_LIBRARY_PATH=~/.local/lib:$LD_LIBRARY_PATH
export LIBRARY_PATH=~/.local/lib:${LIBRARY_PATH:-}
```

### vLLM 配置
```bash
# 注意力后端
export VLLM_ATTENTION_BACKEND=XFORMERS

# 显存利用率
export VLLM_WORKER_GPU_MEM_FRACTION=0.90

# 允许长序列
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
```

### 服务配置
- **模型**: Qwen/Qwen3-4B-Thinking-2507-FP8
- **端口**: 8000
- **最大长度**: 40960
- **显存利用率**: 90%

## 🚨 常见问题及解决方案

### 1. CUDA 库链接错误
```
/usr/bin/ld: cannot find -lcuda: No such file or directory
```
**解决**: 创建符号链接并设置环境变量（见上方配置）

### 2. 注意力后端错误
```
VLLM_ATTENTION_BACKEND=FLASHINFER is not supported
```
**解决**: 使用 `XFORMERS` 后端

### 3. 环境变量未定义
```
LIBRARY_PATH: unbound variable
```
**解决**: 使用 `${VAR:-}` 语法处理未定义变量

## 📊 项目成果

### 成功功能
- ✅ 本地机器翻译服务（日语→中文）
- ✅ 完整的服务管理系统
- ✅ 时间戳日志系统
- ✅ 问题解决记录

### 测试结果
- ✅ `こんにちは、世界。` → `你好，世界。`
- ✅ `今日は良い天気ですね。` → `今天天气真好。`
- ✅ `私は日本語を勉強しています。` → `我正在学习日语。`

## 🎯 当前任务状态

### 已完成
- [x] 环境配置和问题解决
- [x] vLLM 服务部署
- [x] 翻译功能测试
- [x] 项目文档整理

### 进行中
- [ ] 翻译任务优化
- [ ] 批量翻译功能
- [ ] 性能调优

## 🔗 相关文档

- **[详细配置指南](docs/SETUP_GUIDE.md)** - 完整的环境配置和问题解决
- **[学习记录](docs/LEARNING.md)** - 技术知识点和学习笔记
- **[项目总结](docs/PROJECT_SUMMARY.md)** - 项目成果和未来规划
- **[翻译任务](tasks/translation/docs/README.md)** - 翻译功能使用指南

## 💡 给新 Agent 的建议

1. **优先查看文档**: 项目有完善的文档体系，先阅读相关文档
2. **使用管理脚本**: 项目提供了便捷的管理脚本，避免直接操作
3. **检查环境变量**: CUDA 环境配置是关键，确保环境变量正确设置
4. **查看日志**: 使用时间戳日志系统，便于调试和问题追踪
5. **用户级解决方案**: 优先使用用户级解决方案，避免影响其他用户

---

**项目状态**: ✅ 运行中  
**最后更新**: 2024-09-01  
**维护者**: lujiang
