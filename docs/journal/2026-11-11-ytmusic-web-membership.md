# ytmusic 本地跟随网页上的增删移改

## 背景

用户决定（2026-11-11）：歌单的增删、跨歌单移动、改日期、满 20 年从 not yet 搬到昨日重现 / Yesterday once more，
都在 paperbridge `/music/` 网页上做，服务器快照是唯一真相源。原来的 `import-paperbridge` 只跟随 videoId，不增删 CSV 行。

## 改动

- `core/paperbridge_import.py`：拉回时 CSV 跟随服务器——网页加的歌新增一行（`source=paperbridge`），删掉的歌去掉并记到
  `data/paperbridge_removed.json`，在歌单间移动的歌沿用原来那行的其余列，改过的日期写 CSV 和 `overrides.json`；
  CSV 内重复行只留第一条；结果按 `sort_rows` 排序。服务器有、本地没有 CSV 的歌单只报告。
- `cli import-paperbridge`：逐条打印增删移改。
- `tasks/ytmusic/AGENTS.md`、`ytmusic-sync` skill：真相源改为服务器；不要再用 `build_local_csv` 从 QQ 导出重建这几个歌单；
  只补候选时的发布步骤；更新留空歌曲的现状。
- paperbridge 侧（另一个仓库）同日新增网页增删移改、加歌搜索、满 20 年搬歌、最近删除。

## 验证

- `tasks/ytmusic/tests/test_paperbridge_import.py`：原用例改为"服务器多出的歌会加进 CSV"，新增移入/移出/删除/加歌/改日期、
  dry-run 不落盘、再次拉回无改动的用例。`tasks/ytmusic/tests` 除既有的 `test_qq_extractor`（依赖 git-ignored 样例）外全部通过。
- 用当天服务器快照对本地数据 `--dry-run`，结果见 PR 描述。

## 后续

- QQ 新加的歌：拉 QQ 后与服务器快照和 `paperbridge_removed.json` 比对，作为"QQ 新加，待确认"推到网页。
