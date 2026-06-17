# 2026-06-17 实现过程复盘：从 #50 到 #72 的 review 规律

> 对 P1/P2 阶段(业务 schema → 内容寻址身份 → 分片 store → DocumentVersion + 保守择优 →
> translate→import 入库闭环)实现过程的一次复盘，结论用于调整开发流程与 roadmap 心智。

## 背景

到 #72 合并为止，translation 数据平面的核心链路已贯通：source → revision → candidate(多) →
evaluation → 保守择优 → DocumentVersion → bilingual，且新文档 translate→import 闭环达成。
测试基线 229 → 258。本文复盘**怎么实现出来的**，不是实现了什么。

## 压倒性规律：每个 feature 后跟着同一类 review fix

把 commit 排开（#36→#72，十个 feature PR），几乎每个紧跟一条 `fix(...): PR #N review`，
而且修的几乎是**同一类 bug**：

| feature | review 修的 |
| --- | --- |
| #37→#41 | provider-specific identity |
| #38→#45 | anchor parse + write integrity |
| #44→#47 | untrusted-input 加固 |
| #46→#49 | verify segment integrity、full task_id |
| #48→#51 | verify source_hash + eval identity |
| #52→#67 | 身份强校验 |
| #50→#71 | evaluation 绑定、version_id 覆盖全 payload、render 候选身份核对 |
| #72→#75 | ingest 前 revision 身份校验、空 STORE 静默 |

关键观察：**这些 feature PR 合并时 CI 全绿，review 照样找出真 bug。**

## 根因：JSON Schema 验形状，不验意义

架构价值押在内容寻址 + 不可变工件 + store 唯一真相源上，于是最关键的不变量是
`id == hash(content)`、引用指向真实对象——而这恰恰是 schema 管不到的。schema 保证
`cand_[0-9a-f]{64}` 的形状，不保证它真等于内容哈希。**价值最高处 = bug 最爱藏处**，
因为只有那里"看起来对、实际错"。同一个 `verify_*_identity` 模式被一次次重新发明。

测试为什么没拦住：测试是实现者写的，编码的是实现者的心智模型，于是在实现者的盲区也是盲的。
独立的对抗式 reviewer 有用，正因为它不共享实现者的盲区。

## 由此推出的结论

1. **Review 是承重墙，但更该把它前移。** 开 PR 前主动以审查者的对抗视角自检
   "怎样能 schema 合法却语义错"，先写那条反例测试。目标：把每任务 review 轮次从 1–2 降到 0–1。
2. **把反复出现的模式显式化成协议。** `verify_*_identity` + "每次写入过 gate" 已是事实契约，
   应收敛成每类工件统一的 identity/integrity 验证协议，而非每任务重新发明（已开 roadmap issue）。
3. **文档闸门守数字、不守散文。** `docs-drift` 强制基线数字、design-coupling 强制改 core 必动设计，
   但 §20 散文与已合并现实矛盾两次无人拦截。这类漂移目前只能靠周期性人工校准。
4. **顺序纪律被验证有效。** 把 P1.3 推成独立 #72 而非塞进 #50，使 PR 小而专注，
   直接提升了 review 信噪比。"一支一 scope、blocker 分流成 issue"值得坚持。
5. **Roadmap 风险曲线在拐弯。** 数据平面已稳固，剩余工作（#42 zh / current ref / annotation /
   #55 / 网页阅读器）多是"内核之上的表面与投影"，风险从"身份对不对"转向"端到端好不好用"，
   测试重心应随之从单元级身份转向真实文档 e2e demo。

## 自我批评

- **机械摩擦税**：反复在 agent task validator 上吃 round-trip（plan status 枚举、checkpoint
  branch 字段、open_questions 必须字符串、timestamp 格式）。先读一遍 schema 能省掉这些。
- **完成 PR 的仪式成本**：每任务额外一个只翻 `state.json` 的 chore-complete PR，永远 trivially 绿。
  给了干净审计点，但是开销；值得评估是否折进 feature PR 收尾 commit。
