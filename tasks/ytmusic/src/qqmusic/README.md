# tasks/ytmusic/src/qqmusic

## 作用

QQ 音乐数据适配目录。

## 直接子项

- `__init__.py`：package 标记。
- `qq_extractor.py`：QQ 音乐数据抽取。
- `qq_time_fetcher.py`：QQ 音乐时长获取。

## 维护规则

- 外部服务访问与解析逻辑分开，解析行为用本地测试覆盖。
