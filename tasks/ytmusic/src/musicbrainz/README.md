# tasks/ytmusic/src/musicbrainz

## 作用

MusicBrainz 集成目录。

## 直接子项

- `__init__.py`：package 标记。
- `mb_cache_updater.py`：MusicBrainz 缓存更新逻辑。

## 维护规则

- 网络相关逻辑应便于 mock，避免测试依赖真实服务。
