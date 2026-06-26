# tasks/ytmusic/src/ytmusic

## 作用

YouTube Music 适配和同步流程目录。

## 直接子项

- `auth.py`：认证辅助。
- `cache.py`：YTMusic 缓存。
- `client.py`：YTMusic 客户端封装。
- `playlist_manager.py`：播放列表管理。
- `playlist_sync_all.py`：全量播放列表同步入口。
- `playlists.py`：播放列表数据操作。
- `search.py`：搜索逻辑。
- `sync_pipeline.py`：同步流水线。

## 维护规则

- 外部 API 调用应封装在客户端/认证层，核心同步策略保持可测。
