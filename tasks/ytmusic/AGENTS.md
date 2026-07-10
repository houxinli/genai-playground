# ytmusic 子项目指南

把 QQ 音乐导出的歌单迁移到 YouTube Music,并以本地 CSV 作为歌单的"期望状态"持续同步。
仓库级规范见根目录 [`AGENTS.md`](../../AGENTS.md);本文件只写 ytmusic 特有的约定。

## 这个项目做什么

核心数据流(从原始导出到 YT 歌单):

```
data/qqmusic/*.csv        QQ 音乐导出的原始 CSV
  → qqmusic/qq_extractor      规范化 title/artists、去重
  → qqmusic/qq_time_fetcher   调 QQ API 补 time_public   ┐
  → musicbrainz/mb_cache_updater 调 MB 补 release_date    ├→ 全部写入 data/cache_mb.json
  → ytmusic/cache             调 YT search 补 videoId     ┘
  → core/build_local_csv      合并 cache + overrides.json,按"最早日期"定 release_date,排序
  → data/local/*.csv          歌单期望状态(真相源,按发行日期升序)
  → ytmusic/sync_pipeline     清空并重建对应 YT 歌单
```

三个怀旧歌单的流转规则(用户设计,2026-07 确认):
- **not yet** 收发布距今 15–20 年的歌;满 20 年(精确到天)后移出:**中文歌 → 昨日重现,外文歌(日/韩/西) → Yesterday once more**。
- 搬移用 `cli move-old --foreign-target-csv ...`,中外判定在 `core/normalize.is_foreign`(假名/谚文→外文;含汉字→中文;纯拉丁→外文)。
- 三个歌单在 YT 上都按**发布时间从新到旧**排列;本地 CSV 仍按从旧到新存(管线约定),推送时反转。

关键设计决定:
- **本地 CSV 是歌单真相源**,YT 歌单是投影;同步策略是"清空后按序重加"(`sync_playlist`),不是增量 diff。
- **缓存 key 是 `title|artists` 原始文本**(`core/normalize.make_key`),规范化只用于对外查询,不用于 key。
- 日期优先级:override / MB / QQ time_public / YT album_year / 兜底年份,候选中**取最早日期**;可疑日期(未来年份、比兜底晚 2 年以上)进 `suspect_release_date` 不直接采用。
- 人工修正写 `data/overrides.json`,不要直接改 cache_mb.json。

## 怎么跑

- 环境:conda `llm`,依赖仅 `ytmusicapi`(`requirements.txt`)。
- **必须从 `genai-playground` 仓库根目录运行**,代码统一使用 `tasks.ytmusic.src.*` 绝对导入。
- 测试:`conda run -n llm python -m pytest tasks/ytmusic/tests -q`(当前 8 个,全绿;纯离线,外部调用全部打桩)。
- 认证:两种模式,headers(浏览器导出)与 oauth,见 `config/AGENTS.md`。

## 已知问题(2026-07-09 快照,修复后请删掉对应条目)

- **config/ 下所有凭据(headers×2、oauth)均已过期**(2025-11 导出;oauth refresh_token 已 invalid_grant)。读公开数据仍可用,写操作 401。"昨日重现"的推送已于 2026-07-09 通过浏览器内 InnerTube 方案完成;下次需要 Python 侧写操作前要重新导出 headers。
- 库内有两个同名歌单 "Yesterday once more":`PL...DlJET...NorM` 是正主(外语老歌,对应 `local/Yesterday_once_more.csv`,越晚越靠前);`PL...vDL8...N3F3` 已清空,等用户手动删除。
- 原唱不在 YT 曲库、videoId 留空待补的:YOM 的 Butter-Fly(和田光司)、いつも何度でも(木村弓);昨日重现的 偷心海盗(栗儿);not yet 的 ここにいるよ(SoulJa)。
- QQ 线上三歌单(昨日重现 8780163574 / not yet 8913623853 / YOM 9026345074)与本地的搬移结果不同步,QQ 侧需用户手动整理;本地+YT 已按规则于 2026-07-10 对齐。

## 目录导航

| 目录 | 内容 | 详见 |
| --- | --- | --- |
| `src/` | 全部代码,按数据源分包 | `src/AGENTS.md` |
| `config/` | 认证凭据(全部 git-ignored) | `config/AGENTS.md` |
| `data/` | 原始导出、期望状态 CSV、缓存、人工 override | `data/AGENTS.md` |
| `tests/` | 离线单测 | `tests/AGENTS.md` |
| `logs/` | 同步运行日志(NDJSON,每行一首歌 + 末行 summary) | — |
