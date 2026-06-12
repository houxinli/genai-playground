# Cross-Harness Agent Workflow

> 本文定义 Codex、Claude Code、Cursor 等开发 Agent 共用的任务继续、checkpoint 和 context management 协议。
> 开发规范仍以 [`../AGENTS.md`](../AGENTS.md) 为准。

## 1. 目标

用户在任意支持仓库指令的 Agent 中输入：

```text
继续
```

Agent 应能够：

1. 找到当前分支唯一的活动任务。
2. 恢复必要上下文，而不是依赖上一段聊天记录。
3. 核对任务状态与真实 Git 工作区是否一致。
4. 执行下一项可验收工作。
5. 运行验证。
6. 更新执行游标和 checkpoint。
7. 为下一个 Agent 留下明确的 `next_action`。

该协议服务于**同一分支上的顺序交替开发**。不支持两个 Agent 同时修改同一个 worktree。

## 2. 真相源分层

上下文分五层，越靠前越应优先读取：

| 层 | 真相源 | 作用 | 更新频率 |
| --- | --- | --- | --- |
| L0 | `AGENTS.md` | 仓库不变量、编码和 Git 纪律 | 低 |
| L1 | `docs/PROJECT_STATUS.md`、系统设计 | 项目方向、阶段目标、稳定设计 | 阶段级 |
| L2 | `agent/tasks/<task-id>/state.json` | 当前任务执行游标 | 每个 checkpoint |
| L3 | `checkpoints.jsonl`、Git diff/log、测试输出 | 已发生工作的证据 | 每个子任务 |
| L4 | `docs/journal/` | 已合并决策与历史排障 | PR/里程碑级 |

重要约束：

- `state.json` 是“下一步做什么”的真相源。
- Git diff、commit 和测试结果是“实际上做了什么”的真相源。
- 两者冲突时必须先 reconcile，不能盲信 `state.json`。
- Journal 不承担实时 task list，Agent 不应通过遍历全部 journal 重建当前上下文。
- `PROJECT_STATUS.md` 不记录每个会话的细节。

## 3. 目录结构

```text
agent/
├── README.md
├── schemas/
│   ├── task-state.schema.json
│   └── checkpoint.schema.json
├── templates/
│   ├── task-state.json
│   └── checkpoint.json
└── tasks/
    └── <task-id>/
        ├── state.json
        └── checkpoints.jsonl
```

一个 Git branch 最多有一个状态为 `planned`、`active` 或 `blocked` 的任务。

`task-id` 推荐使用 GitHub issue：

```text
gh-123-canonical-json
```

没有 issue 时使用：

```text
local-20260612-agent-continuity
```

## 4. `state.json` 职责

`state.json` 保存：

- 任务目标、范围和 branch
- GitHub issue / PR
- 只需读取的 context files
- 已确认的决策和未决问题
- 结构化 blocker、已尝试方法和解除条件
- 有依赖关系的执行步骤
- 当前唯一 `next_action`
- 必跑验证和最近结果
- 已知的无关工作区改动
- 最近 checkpoint
- 完成后的下一任务引用

它不保存：

- 大段代码分析
- 完整命令输出
- 每轮聊天摘要
- 可从 Git 得到的 diff
- 已经进入 journal 的长期历史

建议控制在 12 KB 以内。超过后应把稳定设计移入正式文档，只在 `context_files` 中引用。

## 5. `checkpoints.jsonl` 职责

每行是一个独立 JSON 对象，按时间追加。记录：

- 哪个 Agent 完成了什么
- 对应 step
- 影响文件
- 写入时观察到的 branch、Git HEAD 和 worktree 快照
- 验证结果
- 风险或 blocker
- 留给下一 Agent 的具体动作

checkpoint 是交接日志，不是聊天流水账。只有以下时机追加：

- 一个独立子任务完成
- 准备从 Codex 切换到 Claude Code，或反向切换
- 遇到需要外部输入的 blocker
- 准备 commit / push / PR
- 任务完成

日志只追加，不修改历史行。写入前必须检查敏感信息和私有语料。

每条 checkpoint 使用唯一 `checkpoint_id`。写入顺序是：

1. 生成 checkpoint，并追加到 `checkpoints.jsonl`。
2. 更新 `state.json`，让 `last_checkpoint.checkpoint_id` 指向该记录。
3. 尽量在同一个提交中保存两者。

如果过程中断，下一 Agent 会发现 `state.json` 与最后一条 checkpoint ID 不一致。有效但未被 state 引用的
checkpoint 只作为待核实证据，不能自动视为已完成；根据 Git、文件和验证结果确认后，追加 reconcile checkpoint，
再更新 state。无法解析的 JSONL 行是损坏，validator 必须失败，不能静默忽略。`observed_head` 表示写 checkpoint
前看到的 HEAD，不尝试在一个 commit 中记录该 commit 自身的 SHA。

## 6. “继续”标准算法

当用户消息主要意图是“继续当前开发”时，所有 harness 执行相同流程。

### Step 1：定位任务

1. 读取 `AGENTS.md`。
2. 执行：

   ```bash
   git status --short --branch
   git branch --show-current
   git log --oneline -5
   ```

3. 在 `agent/tasks/*/state.json` 中找到 `branch` 等于当前分支，且状态为
   `planned` / `active` / `blocked` 的唯一任务。

异常处理：

- 找到多个：停止执行，报告状态冲突。
- 找不到：检查当前 PR/Issue 或用户明确目标；无法无歧义恢复时询问用户，不从 roadmap 随机挑任务。
- 当前任务 `complete`：只有 `next_task` 已明确且工作区满足切换条件时才进入下一任务。

### Step 2：加载最小上下文

按顺序读取：

1. 当前 `state.json`
2. `context_files` 中标记为 required 的文件
3. `checkpoints.jsonl` 最后 3-5 行
4. 当前 Git diff 和相关文件
5. GitHub issue / PR（工具可用且 state 中已配置时）

禁止默认读取所有 journal、所有日志或整个代码库。

### Step 3：状态校准

在继续编码前核对：

- 当前 branch 是否与 state 一致
- `last_checkpoint.observed_head` 是否仍在当前历史中
- `last_checkpoint.checkpoint_id` 是否等于日志最后一条有效记录
- state 声称完成的文件是否确实存在
- 工作区改动是否属于当前 scope
- 是否出现 `known_unrelated_changes` 之外的改动
- 最近 validation 是否已经被后续改动失效
- blocker 是否仍然存在

若 state 与 Git 冲突，以 Git/文件/测试证据为准，先修正 state 并追加 reconcile checkpoint。

开始执行前运行：

```bash
make agent-validate
```

validator 同时检查 JSON Schema 与跨文件不变量，包括：

- task 目录名等于 `state.task_id`
- 同一 branch 最多一个活动任务
- plan step ID、依赖和环无冲突
- 最多一个 `in_progress`，且与 `next_action.step_id` 一致
- checkpoint task/branch/step 引用有效
- `last_checkpoint` 指向日志最后一条有效记录

### Step 4：选择下一项

选择顺序：

1. `next_action`
2. 唯一 `in_progress` step
3. 第一个依赖已完成的 `pending` step

如果三者不一致，先修正任务状态。任何时候最多一个 step 是 `in_progress`。

### Step 5：执行

- 完成 `next_action` 定义的最小可验收单元。
- 遵守 task `scope.in` / `scope.out`。
- 不修改 `known_unrelated_changes`。
- 不因为切换 Agent 而重做已经有证据完成的工作。
- 遇到问题先自行排查；真正需要外部输入时才标记 blocker。

### Step 6：验证和 checkpoint

结束本轮前：

1. 运行该 step 的验收命令。
2. 更新 plan status。
3. 设置下一条单一、具体、可执行的 `next_action`。
4. 更新 `validation.last_results`。
5. 生成唯一 `checkpoint_id`，先向 `checkpoints.jsonl` 追加一行。
6. 更新 `last_checkpoint`，引用相同 `checkpoint_id`。
7. 独立子任务完成且自洽时提交 commit。

好的 `next_action`：

```json
{
  "step_id": "S2",
  "instruction": "实现 Candidate schema 的 source_hash/revision_id 交叉约束。",
  "acceptance": [
    "新增 3 个 invalid fixture 测试并通过。"
  ]
}
```

差的 `next_action`：

```text
继续开发。
```

## 7. Agent 切换流程

### 同一机器、同一 worktree

Agent A 在结束前更新 state/checkpoint。Agent B 收到“继续”后直接按标准算法恢复。

未提交改动可以交接，但 checkpoint 必须明确：

- 哪些文件是本任务改动
- 哪些是用户或其他任务的改动
- 当前测试状态
- 是否存在未完成的编辑

### 不同机器或新 worktree

切换前必须：

1. 形成自洽 checkpoint。
2. 提交当前子任务。
3. push branch。
4. 确保 task state 和 checkpoint 包含在 commit 中。

新机器：

```bash
git fetch origin
git switch <branch>
git pull --ff-only
```

然后输入“继续”。

### 禁止并发

两个 Agent 不应同时在同一 branch/worktree 开发。确实需要并行时：

- 拆成两个 GitHub issue
- 使用两个 branch/worktree
- 各自建立独立 task state
- 通过 PR 合并，不共享 `state.json`

## 8. GitHub 集成

职责分配：

| GitHub | Repository Task State |
| --- | --- |
| Issue：目标、验收标准、依赖 | 当前 step、next action、最近验证 |
| PR：代码 diff、review、CI | 本地/分支内执行游标 |
| Milestone：Phase | 子任务 checkpoint |
| Discussion/Journal：稳定决策 | 临时 blocker 和交接 |

避免复制：

- state 只引用 issue，不复制整个 issue。
- 每完成一个明显 milestone 才更新 issue comment，不同步每条 checkpoint。
- PR 描述汇总最终结果，不粘贴整个 `checkpoints.jsonl`。

推荐 GitHub 标签：

```text
agent-ready
agent-active
agent-blocked
phase:P0
phase:P1
area:translation
contract-change
migration
```

仓库提供：

- `.github/ISSUE_TEMPLATE/agent-task.yml`：固定 objective、acceptance、scope、dependencies、context 和 validation。
- `.github/pull_request_template.md`：要求 PR 关联 issue、task state、验证和最终 handoff。

Issue 创建后以 issue number 生成 `task-id`。Issue/PR 模板不能替代 repository task state：
GitHub 适合团队协作和 review，不适合每个本地编辑步骤都写一次远程 comment。
Issue 模板默认申请 `agent-ready` 标签；仓库必须先创建该标签，否则 GitHub 会忽略模板标签。

## 9. 生命周期

### 创建任务

1. 从最新 `main` 建 topic branch。
2. 创建 GitHub issue 或确认现有 issue。
3. 从模板创建 `agent/tasks/<task-id>/state.json`。
4. 创建空 `checkpoints.jsonl`。
5. 将第一项设为 `in_progress`，设置具体 `next_action`。
6. 运行 `make agent-validate`。
7. 提交 task bootstrap。

### 开发中

- 每个独立子任务一个 checkpoint 和 commit。
- phase 变化才更新 `PROJECT_STATUS.md`。
- 稳定设计变化才更新 system design。
- PR 合并或重要决策才更新 journal。

### Blocked

`status=blocked` 时必须写：

- blocker
- 已尝试的解决方式
- 解除 blocker 所需输入
- 无阻塞时可做的替代工作，若存在

同一个 blocker 未连续确认三次前，不应把任务永久搁置。

### 完成

完成条件：

- 所有 required step 完成
- required validation 通过
- 文档同步
- PR/issue 状态已记录
- `next_action` 为空
- `status=complete`
- 最终 checkpoint 已追加

任务文件保留在 Git 历史中，便于审计。后续可增加 archive 工具，但不能删除尚被开放 PR 引用的状态。

## 10. Context Management 规则

为控制 token 和陈旧信息：

1. `context_files` 最多 8 个。
2. 每个文件必须写 `purpose`。
3. 只加载当前 step 需要的代码文件。
4. checkpoint summary 建议 3-8 条短句。
5. 命令输出只记录结论和关键错误，不粘贴完整日志。
6. 稳定事实迁移到正式文档，然后从 task notes 删除。
7. 被新决策替代的内容在 state 中标记 superseded，不依赖 Agent 猜测。
8. 每 5 个 checkpoint 做一次 state compaction：清理完成步骤的临时说明，但不改 checkpoints 历史。

## 11. Prompt 约定

最短提示：

```text
继续
```

等价完整提示：

```text
按照 AGENTS.md 和 docs/AGENT_WORKFLOW.md 恢复当前分支任务：
读取 task state、必要 context、最近 checkpoints 和 Git 状态；
校准进度后执行 next_action，完成验证，并更新 state/checkpoint。
```

切换前提示：

```text
交接
```

含义：

- 不开始新的大步骤
- 运行当前可运行的验证
- 更新 state 和 checkpoint
- 明确未提交改动与下一动作

“整理进展”用于 PR/阶段级文档和提交整理，不替代日常 checkpoint。

## 12. 最小不变量

- 一个 branch 最多一个活动任务。
- 一个任务最多一个 `in_progress` step。
- `next_action` 必须唯一且具体。
- state 与 Git 冲突时先 reconcile。
- checkpoint 只追加。
- 不把聊天记忆当真相源。
- 不在 task state 中保存 secret、私有语料或大段模型输出。
- 不将用户无关改动纳入 checkpoint/commit。
- 未完成验证不能写成 passed。
- 任务完成后不能保留伪造的 pending step。

## 13. 采用与迁移

不要给所有历史 branch 批量补写虚构状态。按以下顺序启用：

1. 先合并本协议、schema、模板和 harness 入口。
2. 下一项实际开发先创建 GitHub issue，确认 objective、scope 和 acceptance。
3. 从最新 `main` 建干净 topic branch。
4. 创建该 branch 的 task state 和第一条 bootstrap checkpoint。
5. 之后 Codex、Claude Code、Cursor 都只用“继续/交接”推进。
6. 首个任务完成后复盘 state 字段和 checkpoint 粒度，再实现 bootstrap CLI 与 GitHub 状态同步。

已有且工作区混有多个任务的 branch 不应直接标记为 `active`，否则会把历史无关改动伪装成可恢复状态。
这类 branch 应先拆分或收尾；无法拆分时，只能建立明确列出所有 `known_unrelated_changes` 的迁移 checkpoint。
