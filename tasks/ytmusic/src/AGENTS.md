# src/ 代码结构

按数据源/职责分包;项目背景与数据流见上级 [`../AGENTS.md`](../AGENTS.md)。

| 包 | 职责 |
| --- | --- |
| `core/` | 与平台无关的核心:缓存(`SongCache`)、key/查询规范化、合并生成 local CSV、老歌搬移 |
| `ytmusic/` | YT 侧:客户端构建(headers/oauth)、搜索补 videoId、歌单重建同步、批量同步 |
| `qqmusic/` | QQ 侧:导出 CSV 规范化、song_detail API 补 time_public |
| `musicbrainz/` | MB 录音搜索补 release_date,含可疑日期判定 |
| `logging/` | `get_logger`:控制台 + 可选文件的统一 logger |
| `scripts/` | 一次性/辅助脚本(自带 sys.path 注入,可直接执行) |
| `cli.py` | argparse 入口(list/create/add/items/remove/move-old),运行方式 `python -m tasks.ytmusic.src.cli` |

## 约定

- 跨包导入一律用绝对路径 `tasks.ytmusic.src.<pkg>.<mod>`,因此运行/测试必须在 `genai-playground` 仓库根目录下。
- 依赖方向:`ytmusic/ qqmusic/ musicbrainz/` → `core/` + `logging/`;`core/` 不得反向依赖平台包(现状有一个例外:`core/move_old_tracks.py` 引 `ytmusic/sync_pipeline`,新代码不要扩大这个例外)。
- 所有外部网络调用(YT 搜索、MB、QQ API)都要支持注入 `search_fn`/factory 之类的桩,保证测试离线可跑。
- 缓存写入统一走 `SongCache.set(key, platform, field, value)`,platform 取 `mb` / `yt` / `qq`。
- 日志用 `logging.logger.get_logger(__name__, log_path)`,不要直接 `print`。
