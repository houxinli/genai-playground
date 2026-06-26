# tasks/ytmusic/tests

## 作用

YTMusic 子项目测试目录。

## 直接子项

- `__init__.py`：测试 package 标记。
- `data/`：测试数据。
- `test_build_local_csv.py`：本地 CSV 构建测试。
- `test_build_local_csv_priorities.py`：本地 CSV 优先级测试。
- `test_logger.py`：日志测试。
- `test_mb_cache_updater.py`：MusicBrainz 缓存更新测试。
- `test_qq_extractor.py`：QQ 音乐抽取测试。
- `test_update_playlist_sort.py`：播放列表排序更新测试。

## 维护规则

- 新增稳定逻辑时补离线测试。
