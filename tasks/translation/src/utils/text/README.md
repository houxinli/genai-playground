# tasks/translation/src/utils/text

## 作用

文本处理和 token 估算工具目录。

## 直接子项

- `__init__.py`：package 标记。
- `chunking.py`：文本分块工具。
- `cleaning.py`：文本清理工具。
- `token_analyzer.py`：token 分析工具。
- `token_estimation.py`：token 估算实现。
- `token_utils.py`：token 相关辅助函数。

## 维护规则

- CI 中应避免远程 tokenizer 下载；遵守现有环境变量兜底策略。
