# tasks/translation/src/scripts

## 作用

与翻译主流水线强耦合的脚本目录。这里的脚本依赖 `tasks/translation/src/core` 的内部模型或文件约定。

## 直接子项

- `__init__.py`：package 标记。
- `batch_download_v1.py`：Pixiv 批量下载入口。
- `cleanup_bilingual.py`：清理 bilingual 输出。
- `count_tokens.py`：token 计数工具。
- `extract_chinese.py` / `extract_chinese_test.py`：从 bilingual 提取中文输出与测试。
- `file_manager.py`：脚本级文件管理辅助。
- `inventory_content.py` / `inventory_content_test.py`：内容盘点工具与测试。
- `pixiv_auth.py`：Pixiv 认证辅助。
- `qa_baseline.py` / `qa_baseline_test.py`：QA 基线生成与测试。
- `shift_bilingual.py`：双语内容移位/调整工具。

## 维护规则

- 可复用业务逻辑应沉到 `core/`。
- 新脚本要明确是否属于强耦合 `src/scripts/`，不要和 `tasks/translation/scripts/` 混用。
