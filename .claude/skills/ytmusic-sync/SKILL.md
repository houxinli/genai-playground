---
name: ytmusic-sync
description: 审计/修正/同步 YT Music 歌单(昨日重现、not yet、Yesterday once more 等):逐首核对版本、选原唱首发版、按发布时间从新到旧重建歌单。凭据过期时自动走浏览器 InnerTube 方案。当用户要"检查/审计/修/同步 XX 歌单"或跑三歌单流转(move-old)时使用。
argument-hint: "<歌单名或CSV路径> [audit|fix|push|move-old]"
---

# ytmusic-sync

你是歌单管家。业务规则的真相源是 [`tasks/ytmusic/AGENTS.md`](../../tasks/ytmusic/AGENTS.md)(三歌单流转、数据流、overrides 语义)——先读它,本文件只写编排流程与判断规则,不重复业务规则。

所有命令在仓库根目录、conda `llm` 环境下运行。数据文件(CSV/缓存/overrides)都在 `tasks/ytmusic/data/`,git-ignored。

## 标准流程:审计 → 修 → 推送

### 1. 审计

```bash
conda run -n llm python -m tasks.ytmusic.src.cli audit \
  --csv tasks/ytmusic/data/local/<歌单>.csv \
  --qq-csv tasks/ytmusic/data/qqmusic/<歌单>.csv \
  --report <scratch>/audit_report.jsonl --snapshot <scratch>/yt_snapshot.json
```

读报告时按信号强弱分层,**不要把 288 个 flag 全当问题**:

- 强信号(基本都是真问题):`unavailable`、`bad_keyword`、`duration_gap`、`no_videoId`
- 弱信号(大多误报):单独的 `title_mismatch`/`artist_mismatch` 常是官方英文/拼音曲名
  (如《对你爱不完》→ "I Love You Forever")或对照表没收录的艺名。人工过一遍,
  真错配的特征是"另一位歌手的同名歌"或"完全不同的歌"。

### 2. 修正(判断规则)

- **原唱首发版优先**;live/remix/翻唱/重录/串烧都算错版本。时长与 QQ 原曲差 ≤12s 是最强的对版本信号。
- **宁缺毋滥**:YT 没有可接受版本就把 videoId 清空(该歌不进歌单),不塞错歌。
  用户确认过的例外(如"原唱没有就用著名翻唱")要逐首经用户点头。
- 选版用 `ytmusic.audit.pick_video`(打分含艺名对照);返回 None 的输出候选列表让用户/你人工挑,不要降阈值硬选。
- 每个修正写三处:CSV 的 videoId、`data/cache_mb.json`、**`data/overrides.json`(必须带 reason)**。
- 日期可疑(比同曲常识晚很多年)→ 上网查证首发时间(维基/Discogs/百科),结论进 overrides;
  是"歌手后录版本"导致的日期偏晚要问用户按哪个算。
- 新收录的艺名映射补进 `src/ytmusic/artist_aliases.json`。

### 3. 推送

本地 CSV 按旧→新存;YT 歌单要**新→旧**,推送前反转、按 videoId 去重。

- **首选** CLI(需要 `config/headers_auth.json` 有效):`apply_csv_to_playlist` 或 move-old `--sync`。
- **凭据过期(写操作 401 / 库内歌单数为 0)→ 浏览器方案**,不要让用户手工导 headers:
  1. Claude in Chrome 打开已登录的 music.youtube.com;
  2. 把 [`src/ytmusic/browser_push.js`](../../tasks/ytmusic/src/ytmusic/browser_push.js) 整段用 javascript_tool 执行;
  3. 大 videoId 数组嵌入后先核对长度+校验和(算法见 js 文件头注释)再执行;
  4. 大歌单分步调 `clearPlaylist`/`addAll`/`verify`(单次 CDP 调用 45s 上限);
  5. `verify` 必须 orderOK 才算完成。js 文件头列了全部已知坑(写后读延迟、
     批次落顶部的歌单、YT 自动替换等价视频、409 重试)。

### 每次动过歌单后

把有价值的状态更新回 `tasks/ytmusic/AGENTS.md` 的已知问题节(留空待补清单等),修一条删一条。

## 三歌单流转(move-old)

```bash
conda run -n llm python -m tasks.ytmusic.src.cli move-old \
  --source-csv tasks/ytmusic/data/local/not_yet.csv \
  --target-csv tasks/ytmusic/data/local/昨日重现.csv \
  --foreign-target-csv tasks/ytmusic/data/local/Yesterday_once_more.csv \
  --older-than 20 --dry-run   # 先看预览,再去掉 --dry-run
```

搬移后按上面第 3 步推送三个歌单。QQ 音乐侧只读(`pull-qq` 拉取对比),改动要用户手动做。

## 边界

- 不改仓库代码/打分逻辑——那是开发任务,走正常分支+PR。
- 不动 `data/qqmusic/*.csv` 原始导出(只读原料)。
- 破坏性重建(清空歌单)前确认本地 CSV 就是期望状态。
