# tasks

## 作用

多业务子项目目录。每个子目录是一个相对独立的任务域或实验项目。

## 直接子项

- `__init__.py`：让 `tasks` 可作为 Python package 导入。
- `fitness/`：训练记录解析与报告小工具。
- `sunday-movies/`：周末电影场次和评分聚合工具。
- `translation/`：当前主战场，日译中流水线与目标新架构实现。
- `ytmusic/`：YouTube Music / QQ 音乐 / MusicBrainz 相关工具。

## 维护规则

- 不同子项目的改动应拆分支和 PR。
- 子项目内新增代码优先放到各自 `src/` 或 `scripts/` 约定目录。
