# tasks/fitness/src

## 作用

Fitness 子项目的实现代码，负责解析训练日志、规范化动作和生成报告。

## 直接子项

- `__init__.py`：package 标记。
- `cli.py`：命令行入口。
- `model.py`：训练记录领域模型。
- `normalize.py`：动作名和字段规范化。
- `parser.py`：训练日志解析。
- `report.py`：报告生成逻辑。

## 维护规则

- 解析行为变更应同步更新 `tasks/fitness/tests/`。
