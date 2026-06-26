# tasks/translation/src/core/prompt

## 作用

Prompt 构建子包，负责把配置、样例和术语资产组装成模型请求内容。

## 直接子项

- `__init__.py`：package 标记。
- `assets/`：prompt 文本资产和示例。
- `builder.py` / `builder_test.py`：prompt 构建器与测试。
- `config.py` / `config_test.py`：prompt 配置模型与测试。

## 维护规则

- Prompt 文本资产放 `assets/`。
- 构建逻辑改动必须同步 builder/config 测试。
