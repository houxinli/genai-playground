# 翻译任务 (Translation Task)

## 目录结构

```
tasks/translation/
├── data/           # 数据文件
│   ├── input/      # 输入文件（日语原文）
│   ├── output/     # 输出文件（中文译文）
│   └── samples/    # 示例文件（用于few-shot learning）
├── scripts/        # 脚本文件
│   ├── test_prompt.py        # 测试翻译prompt
│   ├── translate_stable.py    # 稳定版本翻译脚本
│   ├── translate_exp.py       # 实验版本翻译脚本
│   └── manage_versions.py     # 版本管理工具
├── logs/           # 日志文件
└── README.md       # 本文件
```

## 使用方法

### 1. 启动翻译服务

```bash
# 使用 Qwen3-14B 模型（推荐，四张显卡）
make vllm-start-bg

# 或者指定其他模型
MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507 TP_SIZE=4 make vllm-start-bg
```

### 2. 测试翻译功能

```bash
# 运行测试
python tasks/translation/scripts/test_prompt.py

# 翻译文件
python tasks/translation/scripts/translate_stable.py --input data/input/input_1.txt --output data/output/translated.txt

# 使用实验版本
python tasks/translation/scripts/translate_exp.py --input data/input/input_1.txt --output data/output/translated.txt
```

### 3. 数据准备

将您的日语原文放在input目录：

```bash
# 日语原文
cp your_japanese_novel.txt tasks/translation/data/input/
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

## 版本管理

项目采用双版本管理策略：
- **stable版本**: 经过测试的稳定版本，推荐用于生产环境
- **exp版本**: 实验版本，用于测试新功能

### 版本管理命令

```bash
# 列出版本
python tasks/translation/scripts/manage_versions.py list

# 将实验版本提升为稳定版本
python tasks/translation/scripts/manage_versions.py promote

# 创建新的实验版本（基于当前稳定版本）
python tasks/translation/scripts/manage_versions.py new
```

### 工作流程

1. 在exp版本中开发和测试新功能
2. 测试通过后，使用`promote`命令将exp版本提升为stable版本
3. 使用`new`命令创建新的exp版本，继续开发

## 注意事项

1. 确保 vLLM 服务在 8000 端口运行
2. 四张 RTX 6000 显卡将用于并行推理
3. 翻译结果会保存在 `data/output/` 目录
4. 日志文件保存在 `logs/` 目录
5. 输入输出文件会被git忽略，避免提交版权内容
