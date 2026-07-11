# 2026-07-10 ytmusic 歌单审计/同步能力沉淀(gh-147 / PR #148)

## 动机

2026-07-09/10 对三个怀旧歌单(昨日重现 / not yet / Yesterday once more)做了全量审计:
511 首逐一核对,修正约 120 处(live/翻唱/错歌/失效/缺视频),并落地三歌单流转规则
(not yet 收 15–20 年,满 20 年按语言分流,YT 上从新到旧)。过程能力散落在会话
临时脚本里,按「确定性逻辑进代码、判断与编排进 skill」沉淀。

## 改动

- **基线修复**:cache.py NameError、sync_pipeline 死参数/调试 print、
  `Path(".")` 陷阱、build_local_csv override 优先级、CLI ImportError
- **move-old**:按天判界(`compute_cutoff_date`)+ 中外分流(`is_foreign`:
  假名/谚文→外文,含汉字→中文,纯拉丁→外文),`--foreign-target-csv`
- **audit / pull-qq 子命令**:审计(强弱信号分层)+ 选版打分
  (`artist_aliases.json` 中英艺名对照,数据文件持续补充)+ QQ 线上歌单拉取
- **browser_push.js**:凭据过期时页面内 InnerTube 推送(SAPISIDHASH),
  含 409 退避、批次落顶部歌单自适应、写后读延迟、顺序+数量双重校验
- **ytmusic-sync skill**:编排与判断规则(原唱首发优先、宁缺毋滥、
  overrides 必带 reason),业务规则引用 `tasks/ytmusic/AGENTS.md` 不复制

## 验证

- `pytest tasks/ytmusic/tests`:23 passed(基线 8 → 23)
- move-old 分流在实数据跑通(23 首,dry-run 与实跑一致)
- browser_push.js 即完成三歌单重建(511/78/77 首)的同一套函数

## Codex 评审(3 条 P2,全部采纳)

1. move-old `--sync` 推送顺序与设计矛盾 → `apply_csv_to_playlist` 增加 `newest_first`
2. clearPlaylist 重试耗尽未中止会产出脏歌单 → throw
3. rebuild 成功判定缺数量一致 → `ok = 顺序逐位一致 && count 相等`

## 后续

- P5(用新工具批量审计中国风/日本語/其它老歌)未开工,挂在 #147 讨论区
- `config/` 凭据(2025-11)仍过期:Python 侧写操作 401,推送走浏览器方案
- YT 曲库缺原唱待补:偷心海盗、ここにいるよ、Butter-Fly、いつも何度でも
