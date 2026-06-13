# 2026-06-13 export-job:task/result 协议生成端(agent 执行路线打通)

## 背景

"本地 agent"经用户澄清是 Claude Code/Codex/Cursor 这类编码 agent 作为 harness executor
(非本机 LLM API),零外部依赖。harness 需要把翻译 job 导出给执行器(issue #46)。

## 改动

- `task_export.py`:
  - `export_task(revision, segment_ids, ...)`:生成 schema 合法 Task;task_id 由身份内容
    确定性派生(同一 job 重复导出稳定),context_digest 覆盖源内容与约束。
  - `export_job(...)`:自包含 bundle = Task + task_digest + 每个 segment 的源文本,执行器据此翻译。
- `make export-job` 入口。
- 4 测试,含**端到端往返**:export_job → 模拟执行器产出 Result → import_result 落 candidate,
  不 quarantine、candidate 数正确。

## 意义

至此 **agent 执行路线端到端打通**:revision → 导出 job → 编码 agent(含 Claude Code 自身)翻译
→ 写 Result → import 落 candidate。**无需任何凭证/模型服务栈。** Grok 4 路线为同协议下的
另一执行器,仅需 xAI key(P2.2)。

## 验证

pytest 全量 175 绿(基线 171→175);make export-job 烟测通过。
