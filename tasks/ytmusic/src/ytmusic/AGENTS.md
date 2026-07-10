# ytmusic/ — YouTube Music 侧

- `auth.py` / `client.py` — 认证与客户端构建。入口是 `client.get_client(auth_mode, ...)`,`auth_mode` 为 `"headers"`(浏览器导出 headers_auth.json)或 `"oauth"`(oauth.json + oauth_client_current.json),默认路径都指向 `../../config/`。`auth.health_check` 可做连通性自检。
- `search.py` — `search_song`:filter="songs" 搜索,返回首个带 videoId 的结果(精简为 videoId/album_year/album_id)。
- `cache.py` — `ensure_yt_cache_for_song`:单曲补 videoId 的决策链 **override → 缓存命中 → 行内已有 → 搜索**,返回 `status`(override/cache_hit/exists/search_hit/search_miss/error)。
- `playlists.py` — 底层批量操作:`sync_playlist` 采用**清空后按序重加**策略重建歌单;增删都是批 50、失败降级逐条。
- `sync_pipeline.py` — `apply_csv_to_playlist`:读 CSV → 补 videoId → `sort_rows`(release_date > album_year/time_public > 无日期)→ 重建歌单,可选 `write_back` 把补齐的 videoId 写回 CSV;NDJSON 日志每行一首歌、末行 summary。
- `playlist_sync_all.py` — 按 `data/local/playlists.json`(title/id/path 列表)批量执行上一条;id 为空时先按 title 匹配库内歌单、匹配不到才新建 PRIVATE 歌单。`fetch_all_playlists_from_yt` 反向刷新该 JSON。
- `audit.py` + `artist_aliases.json` — 歌单审计(逐首核对版本)与选版打分;艺名对照表是数据文件,持续补充。入口 `cli audit`,编排见 `.claude/skills/ytmusic-sync`。
- `browser_push.js` — 凭据过期时在已登录页面内直接调 InnerTube 增删/重建歌单;文件头注释列了全部已知坑,整段注入使用。

改动注意:`sync_playlist` 是破坏性操作(先清空),给它加新调用点前确认 CSV 侧确实是完整的期望状态。
