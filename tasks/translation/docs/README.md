# 翻译任务使用指南

## 🎯 任务概述

本任务实现了基于 vLLM + Qwen3-4B 的本地机器翻译服务，支持日语到中文的翻译。

## 📁 文件结构

```
tasks/translation/
├── scripts/                    # 翻译相关脚本
│   ├── test_translation.py    # 翻译测试脚本
│   ├── serve_qwen3.sh         # Qwen3 服务启动脚本
│   └── translate_qwen3.py    # Qwen3 翻译脚本
├── docs/                       # 翻译任务文档
│   └── README.md              # 本文件
├── data/                       # 数据目录（待创建）
│   ├── input/                 # 输入文件
│   └── output/                # 输出文件
└── logs/                       # 日志目录（待创建）
```

## 🚀 快速开始

### 1. 启动翻译服务
```bash
# 使用主项目的管理脚本
make vllm-start

# 或直接使用翻译脚本
./tasks/translation/scripts/serve_qwen3.sh
```

### 2. 测试翻译功能
```bash
# 使用主项目的测试命令
make vllm-test

# 或直接运行测试脚本
python tasks/translation/scripts/test_translation.py
```

### 3. 批量翻译
```bash
# 使用翻译脚本
python tasks/translation/scripts/translate_qwen3.py --input input.txt --output output.txt
```

## 📝 使用示例

### 简单翻译测试
```python
import requests

def translate_japanese_to_chinese(text):
    url = "http://localhost:8000/v1/chat/completions"
    data = {
        "model": "Qwen/Qwen3-4B",
        "messages": [
            {"role": "system", "content": "你是日语翻译助手"},
            {"role": "user", "content": f"翻译：{text}"}
        ],
        "max_tokens": 1000
    }
    
    response = requests.post(url, json=data)
    return response.json()['choices'][0]['message']['content']

# 测试
result = translate_japanese_to_chinese("こんにちは、世界。")
print(result)  # 输出: 你好，世界。
```

## 🔧 配置说明

### 服务配置
- **模型**: Qwen/Qwen3-4B-Thinking-2507-FP8
- **端口**: 8000
- **最大长度**: 40960
- **显存利用率**: 90%

### 环境要求
- CUDA 12.4
- Python 3.10
- vLLM 0.10.1.1
- 4× RTX 6000 Ada GPU

## 📊 性能指标

### 测试结果
- ✅ `こんにちは、世界。` → `你好，世界。`
- ✅ `今日は良い天気ですね。` → `今天天气真好。`
- ✅ `私は日本語を勉強しています。` → `我正在学习日语。`

### 响应时间
- API 响应: < 1秒
- 翻译质量: 优秀
- 模型推理: 包含思考过程

## 🛠️ 故障排除

### 常见问题
1. **服务启动失败**: 检查 CUDA 环境变量设置
2. **翻译质量差**: 调整系统提示词
3. **响应超时**: 检查模型加载状态

### 日志查看
```bash
# 查看服务日志
make vllm-logs

# 查看翻译脚本日志
tail -f tasks/translation/logs/translation.log
```

## 🔮 扩展功能

### 计划中的功能
1. **多语言支持**: 添加其他语言对
2. **批量处理**: 支持文件批量翻译
3. **质量评估**: 添加翻译质量评估
4. **Web 界面**: 简单的 Web 翻译界面

### 技术升级
1. **模型升级**: 尝试更大的模型
2. **多卡并行**: 充分利用 4 卡资源
3. **缓存优化**: 添加翻译结果缓存

---

**最后更新**: 2024-09-01  
**维护者**: lujiang
