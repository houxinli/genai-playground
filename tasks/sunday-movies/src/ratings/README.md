# tasks/sunday-movies/src/ratings

## 作用

电影评分抓取与聚合模块。

## 直接子项

- `__init__.py`：package 标记。
- `aggregator.py`：多来源评分聚合。
- `base.py`：评分 fetcher 基础接口。
- `douban.py`：豆瓣评分来源。
- `imdb.py`：IMDb 评分来源。
- `rottentomatoes.py`：Rotten Tomatoes 评分来源。
- `tests/`：评分模块测试。
- `utils.py`：评分解析和归一化工具。

## 维护规则

- 外部来源解析变更必须补离线测试。
- 聚合策略变更应同步更新 aggregator 测试。
