# tasks/translation/src/cli

## 作用

翻译 CLI 分层预留目录，用于承载 argparse 和命令行参数校验层。

## 直接子项

- `__init__.py`：package 标记。

## 维护规则

- 新增 CLI flag 时必须同步 `TranslationConfig`、preset 加载和必要测试。
- 不在 CLI 层实现业务逻辑。
