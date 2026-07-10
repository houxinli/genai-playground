# YouTube Music 歌单迁移与同步

把 QQ 音乐导出的歌单迁移到 YouTube Music,以本地 CSV(`data/local/*.csv`)作为歌单的期望状态持续同步。
整体数据流、目录说明和开发约定见 [`AGENTS.md`](AGENTS.md)。

## 准备

- conda `llm` 环境;依赖只有 `ytmusicapi`:`conda run -n llm pip install -r tasks/ytmusic/requirements.txt`
- 认证:浏览器登录 Google 账号后运行 `python -m ytmusicapi setup`,把生成的 `headers_auth.json` 放到 `tasks/ytmusic/config/`(该目录整体 git-ignored)。
- 所有命令都在 `genai-playground` 仓库根目录下运行。

## 常用命令

CLI(`python -m tasks.ytmusic.src.cli`):

```bash
# 列出歌单
conda run -n llm python -m tasks.ytmusic.src.cli list
# 创建歌单
conda run -n llm python -m tasks.ytmusic.src.cli create --name "AI Mix" --privacy PRIVATE
# 查看歌单曲目
conda run -n llm python -m tasks.ytmusic.src.cli items --url "https://music.youtube.com/playlist?list=..."
# 按标题删除曲目
conda run -n llm python -m tasks.ytmusic.src.cli remove --url "..." --title "稻香"
# 把超过 20 年的老歌从一个 CSV 移到另一个(可 --sync 同步 YT)
conda run -n llm python -m tasks.ytmusic.src.cli move-old \
  --source-csv tasks/ytmusic/data/local/not_yet.csv \
  --target-csv tasks/ytmusic/data/local/昨日重现.csv --dry-run
```

库函数(无 CLI 包装,用 `python -c` 或脚本调):

- `ytmusic.sync_pipeline.apply_csv_to_playlist` — 单个 CSV 同步到指定歌单(清空重建)
- `ytmusic.playlist_sync_all.sync_local_playlists_to_yt` — 按 `data/local/playlists.json` 批量同步
- `musicbrainz.mb_cache_updater.update_mb_cache` / `qqmusic.qq_time_fetcher.update_qq_times` — 补发行日期缓存
- `core.build_local_csv.build_local_csv` — 从缓存+override 生成期望状态 CSV

## 测试

```bash
conda run -n llm python -m pytest tasks/ytmusic/tests -q
```
