# 2026-06-13 Sharded ArtifactStore + integrity gate（#54，P1 第二步）

## 背景

#52 把 Candidate 改为内容寻址、importer 产出 v3 + Attestation,但写入仍是"一工件一 JSON 文件 +
调用方传任意 `store_dir`"的过渡形态(Codex 在 #52 复审明确标为 #54 要替换的缺口):

- 文件数 = candidate 数(单作者 momizi813 约 5.5 万),不可扩展。
- 写入边界分散,身份强校验只在 importer/eval/CLI 接,store 这层不存在。
- 没有 cross-artifact 引用完整性闸门。

## 改动

新增 `tasks/translation/src/core/artifact_store.py`:

- **分片**:`store/<kind>/<provider>/<creator_id>/<source_id>.jsonl`,由 document_id 三段拆出
  (pattern 已保证 path-safe,含冒号的 id 不直接当文件名)。文件数 = 文档数。
- **`put_many(document_id, artifacts)`**:按 kind 分组 → 每(kind,document)一 shard → `fcntl.flock`
  锁 shard → 读一次建 id map → 校验(schema + candidate `validate_candidate_identity`)→ 冲突检测 →
  写全量临时 shard + fsync + 原子 rename + dir fsync。**先校验全部再写**,任一失败不落半批。`put` 委托给它。
- **冲突保留**(Codex #52 纠正过的点):同 id + 同 canonical payload skip,payload 不同 `StoreConflictError`
  (防 normalization 漂移/截断 digest/算法 bug/存储损坏)。幂等仅凭 JSONL 成立,不依赖外部索引。
- **`verify_references(artifact, resolver)`**:candidate↔revision.segment.source_hash、
  attestation/evaluation.candidate_id→真 candidate、version.selections 同 revision/segment、parent 解析;
  resolver 按 document 作用域(attestation/evaluation 只带 candidate_id 不带 document_id)。
  **不替代** Task/Result stale-envelope 校验。
- **importer 迁移**:`legacy_import` / `result_import` 改走 `store.put_many`;legacy 连同 DocumentRevision
  一并入库(使 candidate↔revision 完整性可校验);旧 flat `write_candidates/write_attestations/write_artifacts` 移除。

## 设计取舍

- **kind 推断**:工件不显式带 kind。按唯一自有 id 字段(attestation_id/evaluation_id/version_id/
  annotation_id)+ revision 用 `segments`、candidate 用 candidate_id+text 兜底。引用字段(candidate_id 出现在
  多种工件上)不参与判别。
- **冲突测试为何用 document-revision**:candidate 的"同 id 不同 payload"会先被身份 gate 拦住,走不到冲突分支;
  document-revision 的 id 不被 store 重算,可干净构造"同 revision_id 不同内容"来纯测冲突机制。
- **真实 momizi813**:momizi813 几乎全是 NSFW,翻译走 Cursor+Grok,不在 Claude 自动化跑。这里用合成 SFW
  fixture(pixiv 700001)端到端验证 import_directory → 分片落盘 → 第二个 label 去重(N candidate + 2N attestation),
  机制等价;真实库批量导入是 ops 步骤。

## Review triage（三通道，Codex PR #69）

3 条全采纳,均为写入边界正确性的核心:

- **P1 integrity 没接入写入路径**:`verify_references` 原来只在测试里调用,生产 `put_many` 只做 schema+身份。
  → put_many 默认 `verify=True`,提交前对全部 staged 工件跑 `verify_references`,resolver=现有∪本批 staged∪
  已提交 shard(不在本批的 kind 如更早入库的 revision 回落 `self.get`)。result 导入前要求源 revision 已入库,
  否则整批 quarantine。
- **P1 跨 shard 非原子**:原实现逐 kind 锁+写,后一个 shard 冲突会留下前一个已 `os.replace` 的半批。
  → 改两阶段:先锁住全部相关 shard、做冲突预检 + integrity,全通过后再统一提交。按 kind 排序加锁避免死锁。
- **P2 document_id 与分片键不一致**:调用方把 A 文档工件传给 B 的 document_id 会污染 B 的 shard。
  → 对含 document_id 的 kind,写入前强制其值 == 分片键参数。

### 第二轮（PR #69 re-review）

- **P1 跨 shard 真正原子性**:两阶段只挡了逻辑预检失败;提交阶段第二个 shard 物理失败(磁盘满/崩溃)
  仍会留下前一个已 `os.replace` 的 shard。POSIX 多文件 rename 非事务,完整跨 shard 事务超出 #54 范围。
  → 折中:提交按引用依赖序(`COMMIT_ORDER`:revision→candidate→attestation/evaluation/version/annotation),
  使任何崩溃前缀都引用完整(只会少写后续工件,可幂等重导补齐),不产生悬空引用;并把"原子性"措辞
  诚实修正为"逻辑预检失败不落盘 + 物理崩溃前缀引用完整"。
- **P2 annotation 一致性**:原只查 target candidate 存在 → 现解析 revision/segment,且 target 非 null 时
  校验其 revision_id/segment_id 与 annotation 一致(防反馈应用到错句);target 为 null 也校验 segment 存在。
- **P2 document-version 父版本悬空**:`parent_version_id` 非 null 时解析校验,拒绝悬空版本链。

## 验证

`pytest tasks/translation/src -q` 全绿;基线 208 → 229(store 测试含 integrity-at-write/跨 shard 半批/
document_id 一致/依赖序提交/annotation 与 version 引用完整性 + importer 迁移与 revision 预置)。
`check_docs_drift` / `validate_agent_tasks` 通过。

## 仍待

- #55 SQLite 只读投影(从 JSONL 重建,不作第二写入真相源)。
- #50 conservative selection / DocumentVersion v2(依赖本 store)。
