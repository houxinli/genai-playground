# tasks/ytmusic/src/core

## 作用

YTMusic 子项目核心数据处理目录。

## 直接子项

- `__init__.py`：package 标记。
- `build_local_csv.py`：构建本地曲库 CSV。
- `cache_utils.py`：缓存辅助函数。
- `move_old_tracks.py`：旧曲目移动工具。
- `normalize.py`：曲目信息规范化。

## 维护规则

- 核心逻辑应保持可离线测试。
