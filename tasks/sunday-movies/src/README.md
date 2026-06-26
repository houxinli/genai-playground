# tasks/sunday-movies/src

## 作用

Sunday Movies 子项目源码，负责抓取影院场次、聚合评分并生成通知内容。

## 直接子项

- `__init__.py`：package 标记。
- `collectors/`：影院场次采集器。
- `notifier/`：通知发送逻辑。
- `ratings/`：评分来源与聚合逻辑。
- `report/`：报告 package，目前只有 package 标记。
- `scripts/`：离线调试和采集脚本。

## 维护规则

- 采集器和评分逻辑改动应使用离线 fixture 测试，避免 CI 依赖外部站点。
