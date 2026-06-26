# tasks/ytmusic/src

## 作用

YTMusic 子项目源码根目录，负责本地曲库构建、外部音乐服务适配和播放列表同步。

## 直接子项

- `__init__.py`：package 标记。
- `cli.py`：命令行入口。
- `core/`：本地 CSV、缓存和曲目移动核心逻辑。
- `logging/`：日志工具。
- `musicbrainz/`：MusicBrainz 适配。
- `qqmusic/`：QQ 音乐适配。
- `scripts/`：手动脚本。
- `ytmusic/`：YouTube Music 适配和同步流程。

## 维护规则

- 服务适配代码与核心数据处理分层放置。
- 测试放 `tasks/ytmusic/tests/`。
