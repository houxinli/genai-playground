# tasks/translation/src/core/parser

## 作用

翻译输出 parser 子包，负责把模型输出解析为流水线可消费的结构。

## 直接子项

- `__init__.py`：package 标记。
- `translation_output_parser.py`：翻译输出解析实现。
- `translation_output_parser_test.py`：parser 回归测试。

## 维护规则

- 新增输出格式必须补成功和失败路径测试。
