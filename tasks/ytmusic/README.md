# YouTube Music 播放列表示例任务

这个任务用于通过 `ytmusicapi` 管理 YouTube Music 播放列表（创建、列出、添加歌曲）。代码入口在 `tasks/ytmusic/src/cli.py`，默认读取 `config/headers_auth.json` 中的认证头。

## 准备工作
- 建议继续使用仓库里的 `llm` conda 环境：`conda run -n llm python ...`
- 依赖：`ytmusicapi`（后续可按需要加入环境文件或单独 `pip install ytmusicapi`）
- 在浏览器中登录同一 Google 账号，运行 `python -m ytmusicapi setup` 按提示导出 headers，再把生成的 `headers_auth.json` 放到 `tasks/ytmusic/config/`，或通过 `--headers` 指定自定义路径。

## 快速开始
- 列出播放列表：`conda run -n llm python tasks/ytmusic/src/cli.py list`
- 创建播放列表：`conda run -n llm python tasks/ytmusic/src/cli.py create --name "AI Mix" --description "LLM demo" --privacy PRIVATE`
- 向播放列表添加歌曲：`conda run -n llm python tasks/ytmusic/src/cli.py add --playlist-id <PL_ID> --video-ids VIDEO_ID1 VIDEO_ID2`

## 目录结构
- `src/cli.py`：命令行入口。
- `src/client.py`：加载 `YTMusic` 客户端。
- `src/playlist_manager.py`：封装播放列表相关操作。
- `config/`：存放本地的 `headers_auth.json`（已被 `.gitignore` 忽略）。
- `logs/`：后续可写入调试日志的目录。

## 下一步想法
- 增加搜索歌曲/专辑并直接加入播放列表的命令。
- 用本地 JSON/YAML 保存播放列表期望状态，增加同步校验命令。
- 补充单元测试并接入现有 make/conda 流程。
