# tests/ — 单元测试

- 运行(仓库根目录):`conda run -n llm python -m pytest tasks/ytmusic/tests -q`。当前 8 个用例,全绿,0.2s 内跑完。
- 风格:标准 `unittest`,文件名 `test_*.py`(注意与 translation 子项目的 `*_test.py` 约定不同,本目录保持现状即可)。
- **全部离线**:MB 用注入的 `search_fn` 桩,QQ/YT 网络调用不在测试覆盖内;新增涉及外部 API 的逻辑必须走依赖注入打桩,不许真打 API。
- fixture 放 `data/`(现有 `qq_sample.csv`);临时文件用 `tempfile.TemporaryDirectory()`(`test_mb_cache_updater.py` 里写死 `/tmp` 是历史遗留,别效仿)。
- 现状缺口:`sync_pipeline`/`playlists`/`move_old_tracks`/`cli` 均无测试——改这些文件时顺手补,尤其 `sync_playlist` 是破坏性操作。
