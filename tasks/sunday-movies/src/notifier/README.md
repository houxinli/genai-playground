# tasks/sunday-movies/src/notifier

## 作用

通知发送逻辑目录。

## 直接子项

- `__init__.py`：package 标记。
- `email.py`：邮件通知实现。

## 维护规则

- 发送逻辑应避免在测试中真实触发外部邮件服务。
