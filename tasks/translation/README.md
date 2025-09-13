# 翻译任务 (Translation Task)

## 目录结构

```
tasks/translation/
├── translate                   # 可执行包装器（调用 src/translate.py）
├── src/                        # 翻译系统源码
│   ├── translate.py           # 主入口（模块化）
│   ├── core/                  # 核心翻译模块
│   └── cli/                   # 命令行接口
├── scripts/                    # 辅助脚本
│   ├── cleanup_bad_outputs.py # 清理异常双语输出
│   └── README.md              # 脚本说明
├── docs/                       # 翻译任务文档
│   └── README.md              # 详细使用指南
├── data/                       # 数据目录
│   ├── debug/                 # 调试文件
│   ├── samples/               # 示例文件
│   ├── test/                  # 测试数据
│   └── terminology.txt        # 术语对照表
└── logs/                       # 日志目录
```

## 使用方法

### 1. 启动翻译服务

```bash
# 使用主项目的管理脚本
make vllm-start

# 后台启动
make vllm-start-bg

# 启动 32B 完整模型
make vllm-start-32b

# 调试模式启动
make vllm-start-debug
```

### 2. 测试翻译功能

```bash
# 基本翻译测试
make vllm-test

# 批量翻译（需要指定输入目录）
make translate-batch INPUT_DIR=tasks/translation/data/pixiv/50235390

# 智能批量翻译（跳过质量良好的文件）
make translate-batch-smart INPUT_DIR=tasks/translation/data/pixiv/50235390
```

### 3. 翻译模式

#### 前台模式（实时查看进度）
```bash
# 前台运行，实时显示翻译进度
./translate input1.txt --bilingual-simple --stream

# 或使用管理脚本
make translate-start-fg ARGS="input1.txt --bilingual-simple --stream"
```

#### 后台模式（SSH断开不影响）
```bash
# 后台运行，SSH断开后任务继续
make translate-start-bg ARGS="input1.txt --bilingual-simple --stream"

# 或直接使用管理脚本
./scripts/manage_translation.sh start-bg input1.txt --bilingual-simple --stream
```

#### 后台模式使用技巧
```bash
# 1. 启动后台翻译任务
make translate-start-bg ARGS="tasks/translation/data/pixiv/50235390/25341719.txt --bilingual-simple --stream"

# 2. 查看任务状态
make translate-status

# 3. 实时查看翻译进度
make translate-attach
# 或
tmux attach -t translation

# 4. 退出tmux会话（任务继续运行）
# 按 Ctrl-b d

# 5. 实时查看日志
make translate-logs-follow

# 6. 停止翻译任务
make translate-stop
```

#### 进度监控
```bash
# 查看翻译状态和进度
./scripts/monitor_translation.sh status

# 实时监控翻译进度
./scripts/monitor_translation.sh monitor

# 查看翻译统计信息
./scripts/monitor_translation.sh stats
```

#### 简化双语模式 (bilingual_simple)
简化双语模式是专门为长文本翻译优化的模式，具有以下特点：

- **确定性参数**: 使用 temperature=0.0, top_p=1.0 确保输出稳定
- **小批量处理**: 默认每批处理 50 行，避免上下文溢出
- **代码拼接**: 使用代码逻辑拼接翻译结果，提高效率
- **上下文保持**: 每批翻译包含前后 3 行上下文，保持连贯性
- **重复检测**: 内置重复检测机制，避免重复翻译

```bash
# 使用简化双语模式
./translate input.txt --bilingual-simple --stream

# 自定义批处理大小
./translate input.txt --bilingual-simple --line-batch-size-lines 30 --stream

# 自定义上下文行数
./translate input.txt --bilingual-simple --context-lines 5 --stream
```

## 模型选择

- **Qwen3-14B**: 平衡性能和资源，推荐用于日常翻译
- **Qwen3-30B-A3B-Instruct-2507**: 更大模型，翻译质量更高，需要更多显存
- **Qwen3-4B**: 较小模型，适合快速测试

## 翻译风格

- 保持原文的直白露骨程度
- 保持对话格式和段落结构
- 准确翻译专业术语
- 保留表情符号和语气词

## 高级功能

### 质量检测
系统内置质量检测功能，可以自动检测翻译质量：

```bash
# 启用质量检测
./translate input.txt --bilingual-simple --stream

# 禁用LLM质量检测（仅使用规则检测）
./translate input.txt --bilingual-simple --no-llm-check --stream

# 启用严格重复检测
./translate input.txt --bilingual-simple --strict-repetition-check --stream
```

### 增强模式 (Enhanced Mode)
增强模式是一个专门用于提升已有双语翻译质量的功能。它通过QC检测识别质量不佳的翻译行，然后使用LLM重新翻译这些行，从而提升整体翻译质量。

#### 功能特性

1. **QC检测**
   - 使用LLM对每行翻译进行质量评估
   - 给出0-1之间的质量分数
   - 可配置质量阈值（默认0.7）
   - 低于阈值的行将被标记为需要重新翻译

2. **重新翻译**
   - 对质量不佳的行进行重新翻译
   - 提供上下文信息保持翻译风格一致
   - 支持可配置的重试次数（默认2次）
   - 自动提取纯净的翻译结果

3. **文件更新**
   - 保留原始YAML元数据
   - 更新翻译质量不佳的行
   - 保持双语对照格式
   - 支持增量更新

#### 使用方法

**基本用法：**
```bash
python -m src.translate <双语文件路径> --enhanced-mode --stream
```

**配置参数：**
- `--enhanced-qc-threshold`: QC质量阈值（0-1，默认0.7）
- `--enhanced-retry-limit`: 最大重试次数（默认2）
- `--enhanced-context-lines`: 上下文行数（默认5）

**示例：**
```bash
# 使用默认设置
python -m src.translate data/bilingual_file.txt --enhanced-mode --stream

# 自定义质量阈值
python -m src.translate data/bilingual_file.txt --enhanced-mode --stream --enhanced-qc-threshold 0.8

# 自定义重试次数和上下文
python -m src.translate data/bilingual_file.txt --enhanced-mode --stream --enhanced-retry-limit 3 --enhanced-context-lines 7
```

#### 工作流程

1. **文件解析**: 解析双语文件，提取原文和译文对
2. **QC检测**: 逐行评估翻译质量
3. **重新翻译**: 对质量不佳的行进行重新翻译
4. **文件更新**: 更新双语文件，保留YAML元数据

#### 注意事项

1. **文件格式**: 输入文件必须是双语对照格式（原文+译文交替）
2. **YAML支持**: 支持YAML前置元数据
3. **质量阈值**: 建议根据实际需求调整质量阈值
4. **上下文**: 更多的上下文行数可能提供更好的翻译一致性

#### 技术实现

- **EnhancedModeHandler**: 核心处理类
- **QCResult**: QC检测结果数据结构
- **StreamingHandler**: LLM调用处理
- **文件解析**: 支持多种双语文件格式
- **结果提取**: 自动提取纯净的翻译结果

### 分块翻译
对于超长文本，支持分块翻译：

```bash
# 字符级分块
./translate input.txt --mode chunked --chunk-size-chars 15000 --stream

# 行级分块
./translate input.txt --mode chunked --line-chunk-size-lines 100 --stream
```

### 重试机制
内置重试机制，提高翻译成功率：

```bash
# 自定义重试次数和等待时间
./translate input.txt --retries 5 --retry-wait 3.0 --stream

# 上下文溢出时自动降级为分块
./translate input.txt --fallback-on-context --stream
```

## 注意事项

1. 确保 vLLM 服务在 8000 端口运行
2. 四张 RTX 6000 显卡将用于并行推理
3. 翻译结果会保存在 `data/output/` 目录
4. 日志文件保存在 `logs/` 目录
5. 输入输出文件会被git忽略，避免提交版权内容
6. 简化双语模式特别适合长文本翻译，能有效避免上下文溢出问题
