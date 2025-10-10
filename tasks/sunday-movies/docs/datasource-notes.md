# AMC 数据源调研

## 官方网站
- 访问 `https://www.amctheatres.com/movie-theatres/<city>/<theatre-slug>` 会触发 Cloudflare 人机校验。未通过校验时页面返回 403 或 “Attention Required”。
- 初步抓包显示 HTML 本体通过 React 组件渲染，电影与场次数据在前端进一步请求，具体 API 需要浏览器执行脚本后才能得到。
- 直接使用常规 `requests`/`curl` 访问会被阻拦，需要额外手段：
  - 在请求头中设置完整浏览器 UA 与必要的 `Accept`, `Accept-Language`, `Accept-Encoding`。
  - 搭配 Cloudflare 解决方案（如 `cloudscraper`），或使用真实浏览器驱动（Playwright/Selenium）完成挑战。

## 官方 API 线索
- AMC 移动端应用与部分第三方使用 `https://api.amctheatres.com/v2/...` 接口，需要 `X-AMC-Vendor-Key` 才能访问。
- 社区资料展示的 key 常规不对外公开，建议申请官方合作或抓包手机端以确定协议（需遵循法律与服务条款）。

## 替代渠道
- Fandango、Google Showtimes 等第三方提供 AMC 排片信息，网页数据较易解析；作为备选数据源可以减轻绕过 Cloudflare 的压力。
- Fandango 的 `napi/theatershowtimegroupings/<theater-id>/<date>` 接口需带上浏览器生成的定位 Cookie（如 `zip`、`searchcity`），否则常返回空 JSON；当前采集器允许外部注入这些 Cookie。
- 观察发现 `napi/theaterMovieShowtimes/<theater-id>` 接口返回更丰富的结构（`viewModel.movies[*].variants[*].amenityGroups[*]`），但同样依赖完整的 Akamai 反爬 Cookie（`_abck`、`bm_*`、`AKA_A2` 等），这些只能通过 Network 面板复制。
- 若使用第三方，应注明来源并验证与 AMC 官方同步程度。

## 建议
1. 优先尝试使用 Cloudflare 兼容客户端（`cloudscraper`）直连 AMC，保证数据权威性。
2. 若短期无法获取官方数据，可先集成 Fandango/Google 数据，后续再切换到 AMC。
3. 无论使用哪种数据源，均应缓存响应并避免高频访问，以免触发防护或违反使用条款。
