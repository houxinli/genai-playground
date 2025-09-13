# 增强模式功能说明

## 概述
增强模式是一个专门用于提升已有双语翻译质量的功能。它通过QC检测识别质量不佳的翻译行，然后使用LLM重新翻译这些行，从而提升整体翻译质量。

## 功能特性

### 1. QC检测
- 使用LLM对每行翻译进行质量评估
- 给出0-1之间的质量分数
- 可配置质量阈值（默认0.7）
- 低于阈值的行将被标记为需要重新翻译

### 2. 重新翻译
- 对质量不佳的行进行重新翻译
- 提供上下文信息保持翻译风格一致
- 支持可配置的重试次数（默认2次）
- 自动提取纯净的翻译结果

### 3. 文件更新
- 保留原始YAML元数据
- 更新翻译质量不佳的行
- 保持双语对照格式
- 支持增量更新

## 使用方法

### 基本用法
```bash
python -m src.translate <双语文件路径> --enhanced-mode --stream
```

### 配置参数
- `--enhanced-qc-threshold`: QC质量阈值（0-1，默认0.7）
- `--enhanced-retry-limit`: 最大重试次数（默认2）
- `--enhanced-context-lines`: 上下文行数（默认5）

### 示例
```bash
# 使用默认设置
python -m src.translate data/bilingual_file.txt --enhanced-mode --stream

# 自定义质量阈值
python -m src.translate data/bilingual_file.txt --enhanced-mode --stream --enhanced-qc-threshold 0.8

# 自定义重试次数和上下文
python -m src.translate data/bilingual_file.txt --enhanced-mode --stream --enhanced-retry-limit 3 --enhanced-context-lines 7
```

## 工作流程

1. **文件解析**: 解析双语文件，提取原文和译文对
2. **QC检测**: 逐行评估翻译质量
3. **重新翻译**: 对质量不佳的行进行重新翻译
4. **文件更新**: 更新双语文件，保留YAML元数据

## 注意事项

1. **文件格式**: 输入文件必须是双语对照格式（原文+译文交替）
2. **YAML支持**: 支持YAML前置元数据
3. **质量阈值**: 建议根据实际需求调整质量阈值
4. **上下文**: 更多的上下文行数可能提供更好的翻译一致性

## 技术实现

- **EnhancedModeHandler**: 核心处理类
- **QCResult**: QC检测结果数据结构
- **StreamingHandler**: LLM调用处理
- **文件解析**: 支持多种双语文件格式
- **结果提取**: 自动提取纯净的翻译结果

## 测试验证

增强模式已经通过多个测试用例验证：
- 双语内容解析正确性
- QC检测功能正常
- 重新翻译质量提升
- 文件更新完整性

