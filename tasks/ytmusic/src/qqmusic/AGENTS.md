# qqmusic/ — QQ 音乐侧

- `qq_extractor.py` — 读 `data/qqmusic/*.csv`(QQ 导出格式,含 song_mid/album_mid),做 title/artists 规范化并按 `title|artists` 去重,输出统一歌曲 dict(`source="qq"`)。注意:这是唯一在**落盘字段上**应用 `normalize_title/artists` 的地方,后续所有 key 都基于规范化后的文本。
- `qq_time_fetcher.py` — 用 `song_mid` 调 QQ `musicu.fcg` song_detail 接口取 `time_public`(优先曲目级,退album 级),写入缓存 `qq.time_public` + `qq.raw`;有 `max_lookups` 限流与 NDJSON 日志,失败不中断只记录。

QQ 接口无鉴权但不稳定,新增调用保持"单曲 try/except + 日志"模式,不要让一首歌失败中断整批。
