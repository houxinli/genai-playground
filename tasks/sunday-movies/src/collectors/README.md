# tasks/sunday-movies/src/collectors

## 作用

影院场次采集器目录，封装不同来源的数据解析。

## 直接子项

- `__init__.py`：package 标记。
- `amc.py` / `amc_test.py`：AMC 场次采集与测试。
- `fandango.py` / `fandango_test.py`：Fandango 场次采集与测试。
- `models.py`：采集器共享的数据模型。

## 维护规则

- 新采集器应把网络访问和解析逻辑分开，解析测试使用本地 fixture。
