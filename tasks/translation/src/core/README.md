# tasks/translation/src/core

## 作用

翻译子系统核心实现目录。这里同时包含当前生产流水线和目标 artifact/version/store 架构的渐进迁移代码。

## 直接子项

- `__init__.py`：package 标记。
- `archive_derived.py` / `archive_derived_test.py`：归档历史派生产物的工具与测试。
- `artifact_schemas.py` / `artifact_schemas_test.py`：业务 artifact schema、内容寻址和校验测试。
- `artifact_store.py` / `artifact_store_test.py`：分片 JSONL ArtifactStore 与完整性测试。
- `bilingual_writer.py`：双语输出写入工具。
- `candidate_eval.py` / `candidate_eval_test.py`：candidate 硬规则评估与测试。
- `config.py` / `config_test.py`：运行时配置对象与测试。
- `e2e_test.py`：核心 vertical slice 端到端测试。
- `entity_extract.py` / `entity_extract_test.py`：实体抽取导入逻辑与测试。
- `entity_match.py` / `entity_match_test.py`：实体匹配逻辑与测试。
- `entity_review.py` / `entity_review_test.py`：实体 review queue 与测试。
- `entity_store.py` / `entity_store_test.py`：作用域实体库与测试。
- `file_handler.py` / `file_handler_test.py`：源/输出路径处理与状态识别测试。
- `legacy_import.py` / `legacy_import_test.py`：旧 bilingual 译文导入 candidate/store 与测试。
- `logger.py`：翻译日志配置。
- `normalize_bilingual_names_script_test.py`：人名规范化脚本回归测试。
- `openrouter_executor.py` / `openrouter_executor_test.py`：OpenRouter 执行器与测试。
- `parser/`：翻译输出 parser 子包。
- `partial_translator.py` / `partial_translator_test.py`：局部翻译逻辑与测试。
- `pipeline.py`：当前主翻译流水线。
- `pipeline_ingest.py` / `pipeline_ingest_test.py`：新架构 ingest/publish/render 编排与测试。
- `pipeline_repair_test.py`：repair 流水线回归测试。
- `profile_manager.py`：采样 profile 路由。
- `prompt/`：prompt 构建子包。
- `qa_gate.py` / `qa_gate_test.py`：离线硬规则 QA gate 与测试。
- `quality_checker.py` / `quality_checker_*_test.py`：在线质量检查与测试。
- `renderer.py` / `renderer_test.py`：bilingual/zh 渲染器与 golden 测试。
- `repairer.py` / `repairer_test.py`：修复器与测试。
- `result_assemble.py` / `result_assemble_test.py`：TSV 到 result.json 组装与测试。
- `result_import.py` / `result_import_test.py`：Result 导入 Candidate/Attestation 与测试。
- `rule_impact.py` / `rule_impact_test.py`：规则影响分析与测试。
- `rule_qc_integration_test.py`：规则 QC 集成测试。
- `run_state.py`：翻译运行状态持久化。
- `source_adapter.py` / `source_adapter_test.py`：源目录到 revision 的适配与测试。
- `source_identity.py` / `source_identity_test.py`：DocumentRevision/Segment 身份构建与测试。
- `sqlite_index.py` / `sqlite_index_test.py`：SQLite 只读投影与测试。
- `streaming_handler.py`：流式输出处理。
- `task.py`：翻译任务模型。
- `task_export.py` / `task_export_test.py`：Task/Job bundle 导出与测试。
- `testdata/`：核心测试 fixture 和 golden 数据。
- `translate_user.py` / `translate_user_test.py`：作者级 translate-user 编排与测试。
- `translator.py` / `translator_name_glossary_test.py`：主 Translator 与人名词表测试。
- `version_select.py` / `version_select_test.py`：保守选择和 DocumentVersion 构建与测试。

## 维护规则

- 改核心模块时补同目录测试。
- 改 schema、artifact、version 或架构决策时同步 `tasks/translation/docs/system-design.md` 或 `docs/PROJECT_STATUS.md`。
- 不把 prompt/parser 逻辑塞回 `translator.py` 或 `pipeline.py`。
