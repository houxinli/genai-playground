# tasks/translation/src

## 作用

翻译子系统源码根目录。这里包含当前 TXT 流水线、目标 JSON artifact 架构、执行器 harness 和工具包。

## 直接子项

- `__init__.py`：package 标记。
- `cli/`：argparse 入口层。
- `core/`：翻译流水线和新架构核心实现。
- `scripts/`：与主翻译流水线强耦合的脚本。
- `translate.py`：当前主 CLI 入口。
- `utils/`：纯工具函数包。

## 维护规则

- 主执行入口优先走 `tasks/translation/src/translate.py` 或 Makefile。
- 新核心逻辑放 `core/`，新纯工具放 `utils/`，不要新增平行源码目录。
