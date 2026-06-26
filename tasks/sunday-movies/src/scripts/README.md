# tasks/sunday-movies/src/scripts

## 作用

Sunday Movies 的离线调试、抓取和一次性脚本目录。

## 直接子项

- `batch_fandango.py`：批量抓取 Fandango 数据。
- `debug_douban.py`：豆瓣调试脚本。
- `fetch_fandango_showtimes.py`：抓取 Fandango 场次。
- `fetch_multi_showtimes_with_all_ratings.py`：多影院场次和全部评分抓取。
- `fetch_ratings.py`：抓取评分。
- `fetch_showtimes_with_all_ratings.py`：单影院场次和全部评分抓取。
- `fetch_showtimes_with_ratings.py`：单影院场次和评分抓取。
- `find_theater_id.py`：查找影院 ID。
- `rating_summary.py`：评分摘要脚本。
- `read_and_send.py`：读取报告并发送通知。
- `search_theaters.py`：搜索影院。
- `test_douban_api.py` / `test_douban_fetcher.py` / `test_douban_scraping.py`：豆瓣手动测试脚本。
- `test_fandango.py`：Fandango 手动测试脚本。
- `test_imdb_fetcher.py`：IMDb 手动测试脚本。

## 维护规则

- 能进入 CI 的逻辑优先沉到 `collectors/` 或 `ratings/` 并写单元测试。
- 保留脚本的手动用途和运行前提。
