# core/ — 平台无关核心

- `cache_utils.py` — `SongCache`:`data/cache_mb.json` 的读写封装,结构 `{key: {mb|yt|qq: {field: value}}}`,改完记得调 `save()`。
- `normalize.py` — **`make_key(title, artists)` 用原始文本拼 `title|artists`,是全项目唯一的缓存/去重 key**;`normalize_title/artists` 只用于生成对外搜索 query(去括号后缀、只取第一艺人),绝不能用来生成 key,否则缓存对不上。
- `build_local_csv.py` — 管线汇合点:`choose_date` 按 override/MB/QQ/YT/兜底收集候选并**取最早日期**,产出带 `date_source`/`note` 溯源列的 local CSV;`build_local_csv` 支持 `filter_before/after`(ISO 字符串比较,含边界)。
- `move_old_tracks.py` — 把 source CSV 中发行年份 ≤ 当前年−N 的行搬到 target CSV,双侧重排序,可选 `--sync` 回写 YT 歌单。注意它依赖 `ytmusic/sync_pipeline`,是 core 依赖平台包的唯一例外,不要新增同类依赖。

改 `choose_date` 的优先级逻辑时,必须同步更新 `tests/test_build_local_csv*.py` 和上级 AGENTS.md 的日期优先级描述。
