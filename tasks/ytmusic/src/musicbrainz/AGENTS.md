# musicbrainz/ — MusicBrainz 侧

单文件 `mb_cache_updater.py`:

- `mb_search` — MB recording 搜索(urllib,自定义 User-Agent),用 `normalized_query` 之后的 title/artist 查询,但缓存 key 仍是原始文本。
- `best_mb_date` — 汇总 `first-release-date` 与各 release 日期,不完整日期补齐(`YYYY`→`YYYY-12-31`,`YYYY-MM`→`-28`)后取最早。
- `is_suspicious` — 未来年份、或比 album_year/time_public 兜底晚 2 年以上判为可疑,只写 `mb.suspect_release_date`,不进 `mb.release_date`。
- `update_mb_cache` — 主入口:只写缓存不出 CSV;`max_lookups` 限流、失败重试(`retries`/`retry_delay`)、`refresh_existing`/`refresh_suspect` 控制重查;原始响应存 `mb.raw`,NDJSON 日志带 `reasons` 溯源。

MB 有速率限制(约 1 req/s),批量跑保持默认 `retry_delay` 且别把 `max_lookups` 开太大。测试一律注入 `search_fn` 桩,不打真实 API。
