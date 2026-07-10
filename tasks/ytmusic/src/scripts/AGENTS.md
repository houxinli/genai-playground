# scripts/ — 辅助脚本

一次性/手动运维脚本,均自带 `sys.path` 注入(`parents[4]` = 仓库根),可在任意 cwd 直接 `python` 执行:

- `list_playlists.py` — 列出库内歌单的 title/id/count,用于人工确认 playlistId。注意它读的是 `config/headers.json`(不是 CLI 默认的 `headers_auth.json`)。
- `oneoff.py` — 调 `fetch_all_playlists_from_yt` 刷新 `data/local/playlists.json` 的 title→id 映射。

新脚本沿用同样的 path 注入头;一旦逻辑超过"调一个现成函数",应下沉到对应包并补测试,scripts 里只留薄入口。
