# Sunday Movies Agent

目标：在每周日查询湾区 AMC Mercado 20 与 Eastridge 15 的下午场电影，获取各大评分（重点是豆瓣），整合报告并支持消息推送。

## 目录结构
- `src/`：核心代码
  - `collectors/`：影院档期抓取器（`amc.py`、`fandango.py`）
  - `ratings/`：评分源集成
  - `report/`：报告生成
  - `notifier/`：通知发送
- `config/`：默认配置与密钥模板
- `cache/`：抓取缓存
- `logs/`：运行日志
- `tests/`：单元测试与样例数据

## 下一步
1. 实现 AMC 排片 Collector 并缓存结果。
2. 添加评分抓取器（豆瓣、IMDb 等）。
3. 设计报告模板与输出格式。
4. 集成邮件或企业微信通知。

## 开发提示
- 依赖：`beautifulsoup4`、`cloudscraper`、`python-dateutil`（已在环境中存在）等已在根目录 `requirements-llm.txt`；若抓取 Fandango 时返回空对象，可在命令行提示后手动提供 `zip`、`searchcity` 等 Cookie。
- 测试：当前在 `tasks/sunday-movies/src/collectors/amc_test.py`，使用 `conda run -n llm python -m unittest discover -s tasks/sunday-movies/src/collectors -p 'amc_test.py'` 运行。
- 调试脚本：`tasks/sunday-movies/src/scripts/fetch_fandango_showtimes.py` 会读取 `config/fandango_cookies.json` 并输出指定影院的场次；需要时传入链路参数以模拟浏览器请求。
  ```bash
  python tasks/sunday-movies/src/scripts/fetch_fandango_showtimes.py \
    --theater-id AADYN \
    --theater-name "AMC Mercado 20" \
    --referer-slug amc-mercado-20-aadyn \
    --date 2025-10-12
  ```
  如需调用旧版 `theatershowtimegroupings` 接口，加上 `--legacy`。
