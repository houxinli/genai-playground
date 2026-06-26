# tasks/translation/src/utils

## 作用

翻译子系统纯工具包。这里的模块应尽量无副作用、可单独测试。

## 直接子项

- `__init__.py`：package 标记。
- `file/`：文件名和 YAML 解析工具。
- `format/`：输出格式化工具。
- `presets.py`：CLI preset 加载和应用。
- `text/`：文本清理、分块和 token 工具。
- `validation/`：纯函数级质量校验器。

## 维护规则

- 工具函数不应直接读写运行状态或调用模型。
- 新工具按职责放入现有子包。
