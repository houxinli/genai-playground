# scripts

## 作用

仓库级开发、服务管理和校验脚本目录。这里的脚本服务整个仓库，不属于单一业务 task。

## 直接子项

- `bootstrap_agent_task.py` / `bootstrap_agent_task_test.py`：创建 `agent/tasks/<task-id>/` 状态骨架并测试。
- `check_code_readmes.py` / `check_code_readmes_test.py`：校验受 Git 管理的代码目录是否有 `README.md`。
- `check_docs_drift.py` / `check_docs_drift_test.py`：校验文档中机械事实与仓库状态一致。
- `check_vllm.py`：检查 vLLM 服务健康状态。
- `git-hooks/`：本仓库可安装的 Git hook。
- `install-git-hooks.sh`：安装仓库 Git hook。
- `manage_mlx.sh` / `serve_mlx.sh`：管理和启动本地 MLX 服务。
- `manage_translation.sh` / `monitor_translation.sh`：管理和监控翻译任务。
- `manage_vllm.sh` / `serve_vllm.sh`：管理和启动 vLLM 服务。
- `sync_github_task.py` / `sync_github_task_test.py`：同步 agent task 与 GitHub issue 状态并测试。
- `validate_agent_tasks.py` / `validate_agent_tasks_test.py`：校验 agent task state/checkpoint schema 与跨文件不变量。

## 维护规则

- 新增仓库级脚本时同时考虑 Makefile 入口和测试。
- 单一业务子系统脚本优先放到对应 `tasks/<name>/` 下。
