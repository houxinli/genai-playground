# ytmusic 选版搬到 paperbridge 网页，服务器成为歌单真相源

## 背景

2026-10-14 起选版改为"音质优先"，候选列表只能在终端里以文字 + 链接给用户挑，每个版本都要新开
YouTube 试听，手机上尤其麻烦；写入 YT 还要在对话里让 agent 用浏览器方案推送。

## 改动

- `cli export-paperbridge`（`core/paperbridge_export.py`）：本地 CSV + `data/candidates.json`
  → paperbridge `/music/` 快照（schema v1），经 SSH `music.cli publish` 发布。
- paperbridge 侧（另一个仓库）新增 `/music/` 页面：页内试听候选、选版，并通过 Google OAuth
  （仅 `youtube` scope）+ YouTube Data API 一键同步到 YT 歌单；同步后**服务器快照是真相源**。
- `cli import-paperbridge`（`core/paperbridge_import.py`）：把服务器快照拉回本地，videoId 改动按老规矩
  同时写 CSV、`overrides.json`（带 reason）、`cache_mb.json`，并回写候选列表；不增删 CSV 行。
- `ytmusic-sync` skill 增加"先拉回、改完再发布"的流程说明。
- 顺带修了 `cli.py` 里 `move-old` 分支局部 `import json` 遮蔽模块级导入的问题。

## 验证

- `tasks/ytmusic/tests` 新增 3 个用例（导出合并候选、slug、导入写三处 + dry-run 不落盘）。
- 2026-10-27 用户在网页完成首次同步（昨日重现 3 首、6 步写操作）；`import-paperbridge` 拉回后
  6 个歌单与服务器逐首 videoId 一致。

## 后续

- not yet → 昨日重现 / YOM 的满 20 年搬移仍在本地做，需要"拉回 → move-old → 发布"；考虑搬到服务器。
- `test_qq_extractor` 依赖 git-ignored 的 `tests/data/qq_sample.csv`，干净 worktree 里会失败（既有问题）。
