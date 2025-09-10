# Bilingual文件QC处理脚本使用说明

## 功能概述

`qc_bilingual_handler.py` 是一个专门用于处理bilingual文件的QC（质量检查）脚本，参考了bilingual-simple模式的处理方式。

## 主要功能

1. **智能解析bilingual格式**：自动识别YAML部分、对话对照、正文对照
2. **逐行QC检查**：使用规则-based QC检测翻译质量问题
3. **QC标注输出**：在BAD行后添加 `[QC: BAD]` 标记
4. **灵活的文件输出**：支持debug模式和非debug模式

## 使用方法

```bash
python scripts/qc_bilingual_handler.py <bilingual_file>
```

### 示例

```bash
# 处理bilingual文件
python scripts/qc_bilingual_handler.py data/debug/13778952_20250908-105805_bilingual.txt
```

## 输出文件

### Debug模式（默认）
- 输出文件：`<原文件目录>/<文件名>_<时间戳>_qc_bilingual.txt`
- 示例：`data/debug/13778952_20250908-105805_20250908-190609_qc_bilingual.txt`

### 非Debug模式
- 输出目录：`<原文件上级目录>/<原文件目录名>_qc_bilingual/`
- 输出文件：`<原文件上级目录>/<原文件目录名>_qc_bilingual/<文件名>_qc_bilingual.txt`
- 示例：`data/debug_qc_bilingual/13778952_20250908-105805_qc_bilingual.txt`

## QC标注格式

### 正常行（GOOD）
```
　兵士に背中を叩かれ、少しよろめく。
　被士兵拍打后背，身体微微踉跄
```

### 问题行（BAD）
```
　鼻腔をくすぐる異様な香りに、目を大きく開いてしまう。
　鼻腔被异样的香气刺激，不由得睁大了眼睛 [QC: BAD]
```

## QC统计信息

脚本会输出详细的QC统计信息：

```
=== QC统计 ===
总行数: 645
GOOD: 246
BAD: 399
通过率: 38.1%
结论: 需要重译
输出文件: data/debug/13778952_20250908-105805_20250908-190609_qc_bilingual.txt
```

## 技术特点

1. **参考bilingual-simple模式**：
   - 使用相同的YAML处理逻辑
   - 使用相同的文件输出路径规则
   - 使用相同的bilingual格式解析

2. **智能格式识别**：
   - YAML字段对照（title:, caption:, tags:等）
   - 对话对照（「」开头）
   - 正文对照（　开头）

3. **QC规则检测**：
   - 长度比例检查
   - 重复字符检查
   - 日文复制检查
   - CJK标点检查

## 配置选项

可以通过修改脚本中的配置来调整行为：

```python
config = TranslationConfig()
config.bilingual_simple = True  # 使用bilingual模式
config.debug = True  # debug模式，False为非debug模式
```

## 注意事项

1. 脚本会自动跳过YAML部分，只对正文进行QC检查
2. 空白行会被正确保留，不影响bilingual格式
3. QC标注只添加在译文行后，不影响原文
4. 支持大文件处理，内存使用效率高

## 错误处理

- 如果输入文件不存在，会显示错误信息并退出
- 如果处理过程中出现异常，会记录错误日志
- 所有错误都会在控制台显示详细信息
