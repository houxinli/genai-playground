# 脚本整合总结

## 已整合的脚本

### 1. file_manager.py (新整合脚本)
**位置**: `tasks/translation/src/scripts/file_manager.py`

**功能**:
- `rename`: 重命名系列文件 (整合自 rename_series_files.py)
- `list`: 列出文件并按长度排序 (整合自 list_files_by_length.py)
- `cleanup`: 清理低质量双语文件 (整合自 check_bilingual_simple.py)

**用法**:
```bash
# 重命名系列文件
python file_manager.py rename --dir tasks/translation/data/pixiv/50235390

# 列出文件按长度排序
python file_manager.py list --dir tasks/translation/data/pixiv/50235390 --limit 20

# 清理低质量文件
python file_manager.py cleanup --dir tasks/translation/data/pixiv/50235390 --dry-run
```

## 保留的独立脚本

### 1. batch_download_v1.py
**位置**: `tasks/translation/src/scripts/batch_download_v1.py`
**功能**: Pixiv小说批量下载
**保留原因**: 数据获取工具，功能独立

### 2. count_tokens.py
**位置**: `tasks/translation/src/scripts/count_tokens.py`
**功能**: Token计数工具
**保留原因**: 调试和分析工具，对bilingual-simple模式有用

### 3. extract_chinese.py
**位置**: `tasks/translation/src/scripts/extract_chinese.py`
**功能**: 从双语文件提取中文部分
**保留原因**: 后处理工具，支持--bilingual参数

### 4. cleanup_bilingual.py
**位置**: `tasks/translation/src/scripts/cleanup_bilingual.py`
**功能**: 清理重复与低质量的bilingual文件
**保留原因**: 专门的质量清理工具

### 5. cleanup_bad_outputs.py
**位置**: `tasks/translation/scripts/cleanup_bad_outputs.py`
**功能**: 清理问题译文文件（few-shot泄漏等）
**保留原因**: 专门的问题检测工具

## 已删除的脚本

### 1. rename_series_files.py
**原因**: 功能已整合到 file_manager.py 中

### 2. check_bilingual_simple.py
**原因**: 功能已整合到 file_manager.py 中

### 3. list_files_by_length.py
**原因**: 功能已整合到 file_manager.py 中

## 核心翻译功能

### bilingual-simple模式
- 小批量翻译+代码拼接
- 确定性参数（temperature=0.0）
- 支持流式输出

### enhanced-mode
- QC检测+重新翻译
- 质量阈值可配置
- 支持copy/inplace输出策略

## 使用建议

1. **日常翻译**: 使用 `./translate` 命令配合 `--bilingual-simple` 参数
2. **质量提升**: 使用 `--enhanced-mode` 参数对已有双语文件进行质量提升
3. **文件管理**: 使用 `file_manager.py` 进行文件重命名、列表查看、质量清理
4. **数据获取**: 使用 `batch_download_v1.py` 从Pixiv下载小说
5. **后处理**: 使用 `extract_chinese.py` 提取中文内容
6. **调试分析**: 使用 `count_tokens.py` 进行token分析
