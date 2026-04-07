#!/usr/bin/env python3
"""
翻译流程控制模块
"""

import os
import time
from pathlib import Path
from typing import Any, List, Tuple, Dict, Optional

from .config import TranslationConfig
from .logger import UnifiedLogger
from .quality_checker import QualityChecker
from .run_state import TranslationStateStore
from .translator import Translator
from .file_handler import FileHandler
from .enhanced_mode import EnhancedModeHandler
from .task import TranslationTask
from ..utils.file import parse_yaml_front_matter


class TranslationPipeline:
    """翻译流程控制类"""
    
    def __init__(self, config: TranslationConfig):
        """
        初始化翻译流程
        
        Args:
            config: 翻译配置
        """
        self.config = config
        # 始终使用流式（用户要求仅保留流式路径）
        self.config.stream = True

        # 配置 token 估算策略，必要时强制简易模式
        if getattr(self.config, "token_estimator", "auto") == "simple":
            os.environ["TRANSLATION_FORCE_SIMPLE_ESTIMATOR"] = "1"
            # ensure remote download stays disabled
            os.environ.setdefault("TRANSLATION_SKIP_REMOTE_TOKENIZER", "1")
        else:
            os.environ.pop("TRANSLATION_FORCE_SIMPLE_ESTIMATOR", None)
        
        # 初始化组件（默认开启文件日志；仅当realtime_log关闭且无法定位文件时才退回控制台）
        self.logger = UnifiedLogger.create_console_only()
        self.quality_checker = QualityChecker(config, self.logger)
        self.translator = Translator(config, self.logger, self.quality_checker)
        self.state_store = TranslationStateStore(config.log_dir)
        self.file_handler = FileHandler(config, self.logger, self.quality_checker, self.state_store)
        self.current_run_id = ""
        self.current_file_path: Optional[Path] = None
        
        # 初始化增强模式处理器
        if config.enhanced_mode:
            self.enhanced_handler = EnhancedModeHandler(config, self.logger)
        else:
            self.enhanced_handler = None

    def _build_run_snapshot(self) -> Dict[str, Any]:
        """记录本次运行的关键配置快照。"""
        return {
            "model": self.config.model,
            "bilingual_simple": self.config.bilingual_simple,
            "enhanced_mode": self.config.enhanced_mode,
            "overwrite": self.config.overwrite,
            "debug": self.config.debug,
            "debug_files": self.config.debug_files,
            "metadata_only": self.config.metadata_only,
            "line_batch_size_lines": self.config.line_batch_size_lines,
            "context_lines": self.config.context_lines,
            "prompt_style": self.config.prompt_style,
        }

    def run(self, inputs: List[str]) -> int:
        """
        运行翻译流程
        
        Args:
            inputs: 输入文件/目录列表
            
        Returns:
            成功处理的文件数量
        """
        # 验证配置
        errors = self.config.validate()
        if errors:
            for error in errors:
                self.logger.error(f"配置错误: {error}")
            return 0
        
        # 查找文件
        target_total = 0
        run_id = ""
        success_count = 0
        failure_count = 0
        try:
            if self.config.enhanced_mode:
                files_to_process = self.file_handler.find_files_to_process(inputs)
                if not files_to_process:
                    self.logger.warning("没有找到需要处理的文件")
                    return 0
                if self.config.offset > 0:
                    files_to_process = files_to_process[self.config.offset:]
                    self.logger.info(f"跳过前 {self.config.offset} 个文件，剩余: {len(files_to_process)} 个文件")
                if self.config.limit > 0:
                    files_to_process = files_to_process[:self.config.limit]
                    self.logger.info(f"限制处理文件数量为: {len(files_to_process)} 个文件")
                target_total = len(files_to_process)
                self.logger.info(f"开始处理 {target_total} 个文件")
                run_id = self.state_store.start_run(
                    mode="enhanced",
                    inputs=inputs,
                    target_total=target_total,
                    config_snapshot=self._build_run_snapshot(),
                )
                self.current_run_id = run_id
                # 增强模式：处理双语文件
                success_count, failure_count = self._run_enhanced_mode(files_to_process, run_id)
            else:
                tasks_to_process = self.file_handler.plan_tasks(inputs)
                if not tasks_to_process:
                    self.logger.warning("没有找到需要处理的文件")
                    return 0
                if self.config.offset > 0:
                    tasks_to_process = tasks_to_process[self.config.offset:]
                    self.logger.info(f"跳过前 {self.config.offset} 个文件，剩余: {len(tasks_to_process)} 个文件")
                if self.config.limit > 0:
                    tasks_to_process = tasks_to_process[:self.config.limit]
                    self.logger.info(f"限制处理文件数量为: {len(tasks_to_process)} 个文件")
                target_total = len(tasks_to_process)
                self.logger.info(f"开始处理 {target_total} 个文件")
                run_id = self.state_store.start_run(
                    mode="translate",
                    inputs=inputs,
                    target_total=target_total,
                    config_snapshot=self._build_run_snapshot(),
                )
                self.current_run_id = run_id
                # 普通模式：处理原始文件
                success_count, failure_count = self._run_normal_mode(tasks_to_process, run_id)

            run_status = "complete" if failure_count == 0 else ("partial" if success_count > 0 else "failed")
            self.state_store.finish_run(
                run_id,
                status=run_status,
                success_count=success_count,
                failure_count=failure_count,
            )
            self.logger.info(f"处理完成: {success_count}/{target_total} 个文件成功")
            return success_count
        except Exception:
            if run_id:
                self.state_store.finish_run(
                    run_id,
                    status="failed",
                    success_count=success_count,
                    failure_count=max(failure_count, max(target_total - success_count, 1)),
                )
            raise
        finally:
            self.current_run_id = ""
    
    def _run_enhanced_mode(self, files_to_process: List[Path], run_id: str) -> Tuple[int, int]:
        """运行增强模式"""
        self.logger.info("启用增强模式：QC检测 + 重新翻译")
        success_count = 0
        failure_count = 0
        
        for i, file_path in enumerate(files_to_process, 1):
            self.logger.info(f"处理文件 {i}/{len(files_to_process)}: {file_path}")
            # 预判是否跳过：若非覆盖且目标输出已存在，则跳过且不创建日志
            try:
                target_path = self.enhanced_handler._resolve_output_path(file_path)  # 使用增强处理器的路径规则
            except Exception:
                target_path = None
            if (not self.config.overwrite) and target_path and target_path.exists():
                self.logger.info(f"输出文件已存在，跳过: {target_path}")
                continue

            # 确认需要处理：先创建文件日志器并分发到组件，再开始处理，确保全过程有文件日志
            UnifiedLogger._debug_files_mode = self.config.debug_files
            UnifiedLogger._log_level = self.config.log_level
            log_dir = file_path.parent if self.config.debug_files else self.config.log_dir
            custom_basename = None
            if self.config.enhanced_mode and getattr(self.config, 'enhanced_output', 'copy') == 'copy':
                custom_basename = f"{file_path.stem}_enhanced"
            self.logger = UnifiedLogger.create_for_file(
                file_path,
                log_dir,
                stream_output=bool(self.config.realtime_log),
                custom_basename=custom_basename,
            )
            # 将新日志器分发到组件
            self.enhanced_handler.logger = self.logger
            if hasattr(self.enhanced_handler, 'streaming_handler') and self.enhanced_handler.streaming_handler:
                self.enhanced_handler.streaming_handler.logger = self.logger
            if hasattr(self.file_handler, 'logger'):
                self.file_handler.logger = self.logger
            if hasattr(self.quality_checker, 'logger'):
                self.quality_checker.logger = self.logger
            # 打印日志文件路径
            if hasattr(self.logger, 'get_log_file_path'):
                log_file_path = self.logger.get_log_file_path()
                if log_file_path:
                    self.logger.info(f"📝 日志文件路径: {log_file_path}")

            processed = self.enhanced_handler.process_bilingual_file(file_path)
            if processed:
                success_count += 1
            else:
                self.logger.error(f"增强模式处理失败: {file_path}")
                failure_count += 1
            self.state_store.update_run_progress(
                run_id,
                success_delta=1 if processed else 0,
                failure_delta=0 if processed else 1,
            )
        
        return success_count, failure_count

    def _run_normal_mode(self, tasks_to_process: List[TranslationTask], run_id: str) -> Tuple[int, int]:
        """运行普通模式"""
        success_count = 0
        failure_count = 0
        for i, task in enumerate(tasks_to_process, 1):
            display_path = task.original_path or task.output_path
            self.logger.info(f"处理文件 {i}/{len(tasks_to_process)}: {display_path}")
            
            # 在显式调试模式下限制重试次数以加快迭代
            if getattr(self.config, 'debug', False):
                if self.config.retries > 1:
                    self.logger.info("调试模式下将重试次数限制为 1")
                    self.config.retries = 1

            if self.process_task(task):
                success_count += 1
                self.state_store.update_run_progress(run_id, success_delta=1)
            else:
                self.logger.error(f"文件处理失败: {display_path}")
                failure_count += 1
                self.state_store.update_run_progress(run_id, failure_delta=1)
        
        return success_count, failure_count
    
    def process_task(self, task: TranslationTask) -> bool:
        if task.mode == "repair":
            target = task.existing_bilingual_path or task.output_path
            self.logger.error(
                f"暂未在 translate.py 中支持修复流程，请使用 scripts/repair_bilingual.py 处理: {target}"
            )
            return False
        if not task.original_path:
            self.logger.error("缺少原文路径，暂不支持此任务类型")
            return False
        return self.process_file(task.original_path, task=task)

    def _record_processing_state(
        self,
        *,
        source_path: Optional[Path],
        output_path: Path,
        status: str,
        stage: str,
        reason: str = "",
        progress: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.state_store:
            return
        self.state_store.record_file_state(
            run_id=self.current_run_id,
            source_path=source_path,
            output_path=output_path,
            mode="translate",
            status=status,
            stage=stage,
            reason=reason,
            progress=progress,
        )

    def process_file(self, path: Path, task: Optional[TranslationTask] = None) -> bool:
        """
        处理单个文件
        
        Args:
            path: 文件路径
            task: 可选的任务对象，用于携带已有输出状态。
        
        Returns:
            是否处理成功
        """
        # 设置日志
        log_file_path = None
        # 默认开启文件日志；仅当显式要求关闭时才不创建
        UnifiedLogger._debug_files_mode = self.config.debug_files
        UnifiedLogger._log_level = self.config.log_level
        log_dir = path.parent if self.config.debug_files else self.config.log_dir
        self.logger = UnifiedLogger.create_for_file(
            path,
            log_dir,
            stream_output=bool(self.config.realtime_log),
        )
        self.translator.logger = self.logger
        self.file_handler.logger = self.logger
        # 同步更新质量检测与流式处理器上的logger，避免控制台重复调试输出
        if hasattr(self.quality_checker, 'logger'):
            self.quality_checker.logger = self.logger
        if hasattr(self.translator, 'streaming_handler') and self.translator.streaming_handler:
            self.translator.streaming_handler.logger = self.logger
        if hasattr(self.quality_checker, 'streaming_handler') and self.quality_checker.streaming_handler:
            self.quality_checker.streaming_handler.logger = self.logger
        # 获取日志文件路径
        log_file_path = self.logger.get_log_file_path()
        self.logger.info(f"开始处理文件: {path}")
        self.logger.info(f"📝 日志文件路径: {log_file_path}")
        if task and task.output_status:
            self.logger.info(
                f"任务状态: {task.output_status}"
                + (f" ({task.output_reason})" if task.output_reason else "")
            )

        # 提前计算输出路径，便于在读取或解析失败时也能记录到目标文件
        output_path = self._get_output_path(path)
        self.current_file_path = path
        self._record_processing_state(
            source_path=path,
            output_path=output_path,
            status="running",
            stage="start",
            reason=task.output_reason if task else "开始处理",
        )
        
        # 显示配置信息
        self._log_config_info()
        
        # 读取文件内容
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            self.logger.error(f"读取文件失败: {e}")
            self._record_processing_state(
                source_path=path,
                output_path=output_path,
                status="failed",
                stage="read",
                reason=f"读取文件失败: {e}",
            )
            return False
        
        # 解析YAML front matter
        yaml_data, text_content = parse_yaml_front_matter(content)
        
        # 显示文章信息
        self._log_article_info(yaml_data, len(text_content))
        
        # 检查是否需要处理
        if not self.config.overwrite and output_path.exists():
            if task and task.output_status in {"partial", "failed", "running"}:
                self.logger.info(
                    f"检测到{task.output_status}输出，将重新生成: {output_path}"
                )
            else:
                if self.config.debug:
                    self.logger.info(f"Debug模式：文件已存在但会重新处理: {output_path}")
                else:
                    inspection = self.state_store.inspect_output(
                        source_path=path,
                        output_path=output_path,
                        bilingual_simple=self.config.bilingual_simple,
                    )
                    if inspection.status == "complete":
                        self.logger.info(f"输出文件已存在，跳过: {output_path}")
                        self._record_processing_state(
                            source_path=path,
                            output_path=output_path,
                            status="complete",
                            stage="skip",
                            reason=inspection.reason,
                        )
                        return True
                    self.logger.info(
                        f"检测到{inspection.status}输出，将重新生成: {output_path} ({inspection.reason})"
                    )
        
        # 先分别处理 YAML 与 正文
        if yaml_data:
            # 分离原文 YAML 段与正文段（保留分隔线）
            yaml_raw = content.split('---', 2)[1].strip()
            body_raw = content.split('---', 2)[2].strip()
            # 还原带分隔线的 YAML 文本（传给 YAML 翻译器）
            yaml_block_full = f"---\n{yaml_raw}\n---"
            # metadata-only 模式：直接整块调用 YAML 翻译（不逐项）
            if getattr(self.config, 'metadata_only', False):
                # 优先使用结构化逐项翻译（最小上下文），避免整段 YAML 导致跑偏
                try:
                    # 1) 收集四个目标键的原值
                    title_v = None
                    caption_v = None
                    excerpt_v = None
                    series_title_v = None
                    tags_v: list[str] | None = None
                    for ln in yaml_raw.splitlines():
                        s = ln.strip()
                        if s.startswith('title:') and not ln.startswith('  '):
                            title_v = s.split(':',1)[1].strip()
                        elif s.startswith('caption:'):
                            caption_v = s.split(':',1)[1].strip()
                        elif s.startswith('excerpt:'):
                            excerpt_v = s.split(':',1)[1].strip()
                        elif s.startswith('title:') and ln.startswith('  '):
                            # 可能是 series.title
                            series_title_v = s.split(':',1)[1].strip()
                        elif s.startswith('tags:'):
                            val = s.split(':',1)[1].strip()
                            if val.startswith('[') and val.endswith(']'):
                                tags_v = [x.strip() for x in val[1:-1].split(',')]
                    # 2) 批量调用
                    batch_in: dict = {}
                    if title_v is not None and title_v.strip():
                        batch_in['title'] = title_v
                    if caption_v is not None and caption_v.strip():
                        batch_in['caption'] = caption_v
                    if excerpt_v is not None and excerpt_v.strip():
                        batch_in['excerpt'] = excerpt_v
                    if series_title_v is not None and series_title_v.strip():
                        batch_in['series.title'] = series_title_v
                    elif series_title_v is not None and not series_title_v.strip():
                        self.logger.info("series.title 为空，跳过翻译")
                    if tags_v is not None:
                        batch_in['tags'] = tags_v
                    batch_out, _, ok_batch, _ = self.translator.translate_yaml_kv_batch(batch_in)
                    self.logger.debug(f"YAML KV输入: {batch_in}")
                    self.logger.debug(f"YAML KV输出: {batch_out}")
                    # 3) 重建 YAML（双行原/译；tags 中文列表）
                    yaml_out_lines: list[str] = ["---"]
                    for ln in yaml_raw.splitlines():
                        yaml_out_lines.append(ln)
                        s = ln.strip()
                        indent = ln[:len(ln)-len(s)]
                        if s.startswith('title:') and not ln.startswith('  ') and 'title' in batch_out and batch_out['title'].strip():
                            yaml_out_lines.append(f"{indent}title: {batch_out['title']}")
                        elif s.startswith('caption:') and 'caption' in batch_out and batch_out['caption'].strip():
                            yaml_out_lines.append(f"{indent}caption: {batch_out['caption']}")
                        elif s.startswith('excerpt:') and 'excerpt' in batch_out and batch_out['excerpt'].strip():
                            yaml_out_lines.append(f"{indent}excerpt: {batch_out['excerpt']}")
                        elif s.startswith('title:') and ln.startswith('  ') and 'series.title' in batch_out and batch_out['series.title'].strip():
                            yaml_out_lines.append(f"{indent}title: {batch_out['series.title']}")
                        elif s.startswith('tags:') and 'tags' in batch_out and isinstance(batch_out['tags'], list):
                            yaml_out_lines.append(f"{indent}tags: [{', '.join(batch_out['tags'])}]")
                    yaml_out_lines.append('---')
                    yaml_translated = '\n'.join(yaml_out_lines)
                    yaml_ok = True and ok_batch
                except Exception:
                    # 回退一：整块 YAML 调用
                    yaml_translated, yaml_prompt, yaml_ok, _ = self.translator.translate_yaml_text(yaml_block_full)
            else:
                # 统一策略：优先批量四键翻译，失败回退整块 YAML
                try:
                    # 1) 收集四个目标键的原值
                    title_v = None
                    caption_v = None
                    excerpt_v = None
                    series_title_v = None
                    tags_v: list[str] | None = None
                    for ln in yaml_raw.splitlines():
                        s = ln.strip()
                        if s.startswith('title:') and not ln.startswith('  '):
                            title_v = s.split(':',1)[1].strip()
                        elif s.startswith('caption:'):
                            caption_v = s.split(':',1)[1].strip()
                        elif s.startswith('excerpt:'):
                            excerpt_v = s.split(':',1)[1].strip()
                        elif s.startswith('title:') and ln.startswith('  '):
                            # 可能是 series.title
                            series_title_v = s.split(':',1)[1].strip()
                        elif s.startswith('tags:'):
                            val = s.split(':',1)[1].strip()
                            if val.startswith('[') and val.endswith(']'):
                                tags_v = [x.strip() for x in val[1:-1].split(',')]
                    # 2) 批量调用
                    batch_in: dict = {}
                    if title_v is not None and title_v.strip():
                        batch_in['title'] = title_v
                    if caption_v is not None and caption_v.strip():
                        batch_in['caption'] = caption_v
                    if excerpt_v is not None and excerpt_v.strip():
                        batch_in['excerpt'] = excerpt_v
                    if series_title_v is not None and series_title_v.strip():
                        batch_in['series.title'] = series_title_v
                    elif series_title_v is not None and not series_title_v.strip():
                        self.logger.info("series.title 为空，跳过翻译")
                    if tags_v is not None:
                        batch_in['tags'] = tags_v
                    batch_out, _, ok_batch, _ = self.translator.translate_yaml_kv_batch(batch_in)
                    # 3) 重建 YAML（双行原/译；tags 中文列表）
                    yaml_out_lines: list[str] = ["---"]
                    for ln in yaml_raw.splitlines():
                        yaml_out_lines.append(ln)
                        s = ln.strip()
                        indent = ln[:len(ln)-len(s)]
                        if s.startswith('title:') and not ln.startswith('  ') and 'title' in batch_out and batch_out['title'].strip():
                            yaml_out_lines.append(f"{indent}title: {batch_out['title']}")
                        elif s.startswith('caption:') and 'caption' in batch_out and batch_out['caption'].strip():
                            yaml_out_lines.append(f"{indent}caption: {batch_out['caption']}")
                        elif s.startswith('excerpt:') and 'excerpt' in batch_out and batch_out['excerpt'].strip():
                            yaml_out_lines.append(f"{indent}excerpt: {batch_out['excerpt']}")
                        elif s.startswith('title:') and ln.startswith('  ') and 'series.title' in batch_out and batch_out['series.title'].strip():
                            yaml_out_lines.append(f"{indent}title: {batch_out['series.title']}")
                        elif s.startswith('tags:') and 'tags' in batch_out and isinstance(batch_out['tags'], list):
                            yaml_out_lines.append(f"{indent}tags: [{', '.join(batch_out['tags'])}]")
                    yaml_out_lines.append('---')
                    yaml_translated = '\n'.join(yaml_out_lines)
                    yaml_ok = True and ok_batch
                except Exception:
                    # 回退到 LLM 整块 YAML 路径
                    yaml_translated, yaml_prompt, yaml_ok, _ = self.translator.translate_yaml_text(yaml_block_full)
            if not yaml_ok or not yaml_translated:
                self.logger.error("YAML 段翻译失败")
                self._record_processing_state(
                    source_path=path,
                    output_path=output_path,
                    status="failed",
                    stage="yaml",
                    reason="YAML 段翻译失败",
                )
                return False
            # YAML 规则 QC（不中断版）：仅告警
            ok, reason = self.quality_checker.check_yaml_quality_rules(yaml_block_full, yaml_translated)
            if not ok:
                self.logger.warning(f"YAML 规则检测未通过：{reason}")
            
            # 如果是bilingual_simple模式，先预创建文件
            if self.config.bilingual_simple:
                self._create_prefilled_bilingual_file(content, output_path)
                # YAML翻译完成后立即更新文件
                self._update_bilingual_file_yaml(output_path, yaml_translated)
                self._record_processing_state(
                    source_path=path,
                    output_path=output_path,
                    status="partial",
                    stage="yaml_prefill",
                    reason="YAML 已写入，正文仍在处理中",
                    progress={
                        "phase": "yaml",
                        "bilingual_simple": True,
                    },
                )
            
            # 若仅翻译元数据，则不处理正文
            if getattr(self.config, 'metadata_only', False):
                translated_content = yaml_translated
            else:
                # 翻译正文（保留现有分块逻辑）
                body_translated = self._translate_text(body_raw, use_body_prompt=True)
                if not body_translated:
                    self.logger.error("正文翻译失败")
                    self._record_processing_state(
                        source_path=path,
                        output_path=output_path,
                        status="failed",
                        stage="body",
                        reason="正文翻译失败",
                    )
                    return False
                translated_content = f"{yaml_translated}\n{body_translated}"
        else:
            # 无 YAML，直接按正文处理
            if getattr(self.config, 'metadata_only', False):
                self.logger.warning("启用了 --metadata-only 但输入不含 YAML，跳过文件")
                self._record_processing_state(
                    source_path=path,
                    output_path=output_path,
                    status="failed",
                    stage="metadata_only",
                    reason="输入不含 YAML，无法仅翻译元数据",
                )
                return False
            
            # 如果是bilingual_simple模式，先预创建文件
            if self.config.bilingual_simple:
                self._create_prefilled_bilingual_file(content, output_path)
            
            translated_content = self._translate_text(content)
        
        if not translated_content:
            self.logger.error("翻译失败")
            self._record_processing_state(
                source_path=path,
                output_path=output_path,
                status="failed",
                stage="translate",
                reason="翻译结果为空",
            )
            return False
        
        # 保存结果
        final_status = "complete"
        final_reason = "写入完成"
        if "[翻译未完成]" in translated_content:
            final_status = "partial"
            final_reason = "输出中仍含未完成标记"
        elif "[翻译失败]" in translated_content:
            final_status = "failed"
            final_reason = "输出中仍含失败标记"

        saved = self._save_result(output_path, translated_content, yaml_data)
        self._record_processing_state(
            source_path=path,
            output_path=output_path,
            status=final_status if saved else "failed",
            stage="save",
            reason=final_reason if saved else "保存文件失败",
            progress={
                "bilingual_simple": self.config.bilingual_simple,
                "metadata_only": getattr(self.config, "metadata_only", False),
            },
        )
        return saved and final_status == "complete"
    
    def _log_config_info(self) -> None:
        """记录配置信息"""
        self.logger.info("🔧 翻译配置:")
        self.logger.info(f"   模型: {self.config.model}")
        self.logger.info(f"   简化双语模式: {self.config.bilingual_simple}")
        self.logger.info(f"   增强模式: {self.config.enhanced_mode}")
        self.logger.info(f"   实时日志: {self.config.realtime_log}")
        self.logger.info(f"   重试次数: {self.config.retries}")
        self.logger.info(f"   重试等待: {self.config.retry_wait} 秒")
        self.logger.info(f"   上下文长度: {self.config.get_max_context_length()}")
        self.logger.info(f"   温度: {self.config.temperature}")
        self.logger.info(f"   频率惩罚: {self.config.frequency_penalty}")
        self.logger.info(f"   存在惩罚: {self.config.presence_penalty}")
        self.logger.info(f"   术语文件: {self.config.terminology_file}")
        self.logger.info(f"   示例文件: {self.config.sample_file}")
        self.logger.info(f"   前言文件: {self.config.preface_file}")
        self.logger.info(f"   停止词: {self.config.stop}")
        self.logger.info(f"   日志目录: {self.config.log_dir}")
        self.logger.info("   ==================================================")
    
    
    def _log_article_info(self, yaml_data: Optional[Dict], text_length: int) -> None:
        """记录文章信息"""
        self.logger.info("📖 文章信息:")
        
        if yaml_data:
            self.logger.info(f"   标题: {yaml_data.get('title', 'N/A')}")
            self.logger.info(f"   作者: {yaml_data.get('author', {}).get('name', 'N/A')}")
            self.logger.info(f"   系列: {yaml_data.get('series', {}).get('title', 'N/A')}")
            self.logger.info(f"   创建时间: {yaml_data.get('create_date', 'N/A')}")
            tags = yaml_data.get('tags', [])
            if tags:
                self.logger.info(f"   标签: {', '.join(tags)}")
        
        self.logger.info(f"   原文长度: {text_length} 字符")
    
    def _get_output_path(self, input_path: Path) -> Path:
        """获取输出文件路径"""
        stem = input_path.stem
        suffix = self.config.get_output_suffix()
        
        # 在debug模式下，输出文件使用stem + timestamp格式，放在原目录
        if self.config.debug:
            from datetime import datetime
            ts = datetime.now().strftime('%Y%m%d-%H%M%S')
            return input_path.parent / f"{stem}_{ts}{suffix}.txt"
        else:
            # 非debug模式下，根据翻译模式创建不同的子目录
            if self.config.bilingual_simple:
                # bilingual模式：创建 _bilingual 子目录
                output_dir = input_path.parent.parent / f"{input_path.parent.name}_bilingual"
            else:
                # 纯中文模式：创建 _zh 子目录
                output_dir = input_path.parent.parent / f"{input_path.parent.name}_zh"
            
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)
            
            return output_dir / f"{stem}.txt"
    
    def _translate_text(self, text_content: str, use_body_prompt: bool = False) -> str:
        """翻译文本内容"""
        
        # 检查是否使用bilingual-simple模式
        if self.config.bilingual_simple:
            return self._translate_text_simple_bilingual(text_content)
        
        # 不需要分块，直接单块翻译
        if use_body_prompt:
            result, prompt, success, token_meta = self.translator.translate_body_text(text_content)
        else:
            result, prompt, success, token_meta = self.translator.translate_text(text_content)
        if not success:
            self.logger.error("翻译失败，保留原文")
            return text_content  # 保留原文而不是返回空字符串
        self.logger.info(f"Token使用情况: {token_meta}")
        return result
    
    def _save_result(self, output_path: Path, content: str, yaml_data: Optional[Dict]) -> bool:
        """保存翻译结果"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.logger.info(f"WRITE {output_path}")
            
            # 记录日志文件路径（如果启用了实时日志）
            if self.config.realtime_log and hasattr(self.logger, 'get_log_file_path'):
                log_file_path = self.logger.get_log_file_path()
                if log_file_path:
                    self.logger.info(f"📝 日志文件路径: {log_file_path}")
            
            return True
        except Exception as e:
            self.logger.error(f"保存文件失败: {e}")
            return False

    def _postprocess_bilingual_punctuation(self, content: str) -> str:
        """对双语对照文本的中文行进行句末标点补全（保守规则）。
        规则：
        - 仅处理成对的行（奇数行为原文，偶数行为中文）。
        - 若中文行非空，且不以中文句末标点或闭合符号结束，则补一个全角句号“。”。
        - 不改动空行、YAML 区域与以闭合引号/括号/书名号结尾的行。
        """
        lines = content.split('\n')
        # 粗略判定：YAML front matter 结束后再处理
        yaml_end = -1
        if lines and lines[0].strip() == '---':
            for idx, ln in enumerate(lines[1:], start=1):
                if ln.strip() == '---':
                    yaml_end = idx
                    break
        start_idx = yaml_end + 1 if yaml_end >= 0 else 0
        endings = tuple("。！？…?!")
        closers = tuple("’”』」】）》》")
        out = list(lines)
        # 从正文开始，按对照对处理
        i = start_idx
        while i + 1 < len(out):
            ja = out[i]
            zh = out[i + 1]
            zh_stripped = zh.rstrip()
            # 跳过空行
            if zh_stripped:
                last_char = zh_stripped[-1]
                # 简单判断是否中文句末或闭合
                if last_char not in endings and last_char not in closers:
                    # 避免在明显的省略“——”“…”后追加句号
                    if not zh_stripped.endswith('——') and not zh_stripped.endswith('…'):
                        out[i + 1] = zh_stripped + '。' + zh[len(zh_stripped):]
            i += 2
        return '\n'.join(out)
    
    def _create_prefilled_bilingual_file(self, text_content: str, output_path: Path) -> None:
        """
        创建预填充的双语文件，未翻译行标注为[翻译未完成]
        """
        lines = text_content.splitlines(keepends=True)
        if not lines:
            return
        
        # 过滤掉YAML部分（如果存在）
        start_idx = 0
        if lines and lines[0].strip() == '---':
            # 找到YAML结束位置
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == '---':
                    start_idx = i + 1
                    break
        
        # 创建预填充内容
        prefilled_lines = []
        for i, line in enumerate(lines):
            if i < start_idx:
                # YAML部分保持原样
                prefilled_lines.append(line)
            else:
                # 正文部分
                if line.strip():
                    # 有内容的行标注为[翻译未完成]
                    prefilled_lines.append(f"{line.rstrip()}\n[翻译未完成]\n")
                else:
                    # 空白行保持原样
                    prefilled_lines.append(line)
        
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入预填充文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(prefilled_lines)
        
        self.logger.info(f"📝 预创建双语文件: {output_path}")

    def _update_bilingual_file_yaml(self, output_path: Path, yaml_translated: str) -> None:
        """
        更新双语文件中的YAML部分
        """
        if not output_path.exists():
            self.logger.warning(f"输出文件不存在: {output_path}")
            return
        
        # 读取现有文件内容
        with open(output_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 找到YAML结束位置
        yaml_end_idx = 0
        if lines and lines[0].strip() == '---':
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == '---':
                    yaml_end_idx = i + 1
                    break
        
        # 替换YAML部分
        yaml_lines = yaml_translated.split('\n')
        new_lines = []
        for i, line in enumerate(yaml_lines):
            new_lines.append(line + '\n')
        
        # 保留YAML后的内容
        if yaml_end_idx < len(lines):
            new_lines.extend(lines[yaml_end_idx:])
        
        # 写回文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        self.logger.info(f"✅ 更新双语文件YAML部分: {output_path}")

    def _update_bilingual_file_batch(
        self,
        output_path: Path,
        batch_start_idx: int,
        batch_end_idx: int,
        bilingual_pairs: List[Tuple[str, str]],
    ) -> None:
        """
        更新双语文件中的特定批次行
        """
        if not output_path.exists():
            self.logger.warning(f"输出文件不存在: {output_path}")
            return
        
        # 读取现有文件内容
        with open(output_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 找到YAML结束位置
        yaml_end_idx = 0
        if lines and lines[0].strip() == '---':
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == '---':
                    yaml_end_idx = i + 1
                    break
        
        # 计算在文件中的实际行索引
        file_start_idx = yaml_end_idx + batch_start_idx * 2  # 每行原文+译文占2行
        file_end_idx = yaml_end_idx + batch_end_idx * 2
        
        # 确保文件内容长度足够
        if file_end_idx > len(lines):
            lines.extend(['\n'] * (file_end_idx - len(lines)))
        
        # 更新文件内容（成对写入原文/译文）
        for offset, (orig_line, trans_line) in enumerate(bilingual_pairs):
            file_idx = file_start_idx + offset * 2
            if file_idx < len(lines):
                lines[file_idx] = orig_line.rstrip('\n') + '\n'
            if file_idx + 1 < len(lines):
                lines[file_idx + 1] = trans_line.rstrip('\n') + '\n'
        
        # 写回文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
       
        self.logger.info(f"✅ 更新双语文件批次 {batch_start_idx+1}-{batch_end_idx}: {output_path}")

    def _translate_text_simple_bilingual(self, text_content: str) -> str:
        """
        简化的bilingual翻译方法
        使用小批量翻译 + 代码拼接的方式
        """
        self.logger.info("使用简化bilingual模式进行翻译")
        
        # 按行分割文本
        lines = text_content.splitlines(keepends=True)
        if not lines:
            return ""
        
        # 过滤掉YAML部分（如果存在）
        start_idx = 0
        if lines and lines[0].strip() == '---':
            # 找到YAML结束位置
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == '---':
                    start_idx = i + 1
                    break
        
        # 只翻译正文部分
        body_lines = lines[start_idx:]
        if not body_lines:
            return text_content
        
        # 批次处理
        batch_size = self.config.line_batch_size_lines
        context_size = self.config.context_lines
        
        translations_map: Dict[int, str] = {}
        # 预处理：收集所有有内容的行及其索引
        content_lines = []
        content_indices = []
        for idx, line in enumerate(body_lines):
            if line.strip():  # 只收集非空白行
                content_lines.append(line.rstrip())
                content_indices.append(idx)
        
        self.logger.info(f"总行数: {len(body_lines)}, 有内容行数: {len(content_lines)}")
        
        # 按有内容的行分批处理
        content_batch_size = batch_size
        original_batch_size = batch_size  # 保存原始批次大小
        # 自适应回升：记录连续成功批次数，用于逐步回升到初始批量
        consecutive_success_batches = 0
        content_i = 0
        previous_io = None  # 跟踪前一次的输入输出
        start_time = time.time()  # 记录开始时间
        # 单篇文章超时（秒），使用config中的配置
        max_duration = self.config.article_timeout_s
        
        while content_i < len(content_lines):
            # 检查时间限制
            elapsed_time = time.time() - start_time
            if elapsed_time > max_duration:
                self.logger.warning(f"翻译超时（{elapsed_time:.1f}秒 > {max_duration}秒），停止处理，已翻译 {content_i} 行有内容行")
                break
            
            # 每10分钟记录一次进度
            if content_i > 0 and int(elapsed_time) % 600 == 0:
                self.logger.info(f"翻译进度: {content_i}/{len(content_lines)} 行，耗时 {elapsed_time:.1f}秒")
                
            # 确定当前批次的有内容行
            content_end_idx = min(content_i + content_batch_size, len(content_lines))
            batch_content_lines = content_lines[content_i:content_end_idx]
            batch_content_indices = content_indices[content_i:content_end_idx]
            
            # 获取对应的原始行（包含空白行）
            start_file_idx = batch_content_indices[0]
            end_file_idx = batch_content_indices[-1] + 1
            batch_lines = body_lines[start_file_idx:end_file_idx]
            
            # 获取上下文
            context_before = []
            context_after = []
            
            if context_size > 0:
                # 前文上下文
                context_start = max(0, start_file_idx - context_size)
                context_before = body_lines[context_start:start_file_idx]
                
                # 后文上下文
                context_end = min(len(body_lines), end_file_idx + context_size)
                context_after = body_lines[end_file_idx:context_end]
            
            # 合并上下文
            context_lines = context_before + context_after
            
            self.logger.info(f"翻译批次 {content_i//content_batch_size + 1}: 有内容行 {content_i+1}-{content_end_idx} (共{len(batch_content_lines)}行)")
            
            # 调用简化翻译
            chinese_lines, prompt, success, token_stats, current_io = self.translator.translate_lines_simple(
                batch_content_lines,
                previous_io=previous_io,
                start_line_number=content_i + 1,
                context_lines=[line.strip('\n') for line in context_lines],
            )
            
            if success and len(chinese_lines) == len(batch_content_lines):
                # 使用统一的bilingual工具函数拼接原文和译文
                from ..utils.format import create_bilingual_output
                
                # 准备原文和译文行，并记录到映射中
                orig_lines = batch_content_lines
                batch_pairs: List[Tuple[str, str]] = []
                for idx_in_body, orig_line, trans_line in zip(batch_content_indices, orig_lines, chinese_lines):
                    translations_map[idx_in_body] = trans_line
                    batch_pairs.append((orig_line, trans_line))
                
                bilingual_result = create_bilingual_output(orig_lines, chinese_lines)
                
                # 记录对照版结果到日志
                self.logger.debug(f"批次对照结果（有内容行 {content_i+1}-{content_end_idx}）:\n{bilingual_result}")
                
                # 更新预创建的双语文件
                if batch_pairs:
                    current_output_path = self._get_output_path(self.current_file_path)
                    self._update_bilingual_file_batch(
                        current_output_path,
                        content_i,
                        content_end_idx,
                        batch_pairs,
                    )
                    self._record_processing_state(
                        source_path=self.current_file_path,
                        output_path=current_output_path,
                        status="partial",
                        stage="body_batch",
                        reason=f"已完成批次 {content_i // content_batch_size + 1}",
                        progress={
                            "translated_content_lines": len(translations_map),
                            "total_content_lines": len(content_lines),
                            "completed_content_index": content_end_idx,
                            "batch_size": len(batch_pairs),
                        },
                    )
                
                # 更新前一次的输入输出（用于下一批次的上下文）
                # 使用翻译器返回的 current_io
                previous_io = current_io
                
                # 记录批次完成信息
                batch_num = content_i//content_batch_size + 1
                self.logger.info(f"✅ 批次 {batch_num} 翻译完成:")
                self.logger.info(f"   📝 日志文件: {self.logger.log_file_path}")
                self.logger.info(f"   📄 输出文件: {current_output_path}")
                self.logger.info(f"   🔢 Token使用: {token_stats}")
                self.logger.info(f"   📊 进度: {content_end_idx}/{len(content_lines)} 行")
                
                content_i = content_end_idx
                # 累计成功批次数，按阶梯逐步回升批量（例如 25→50→100）
                consecutive_success_batches += 1
                if content_batch_size < original_batch_size and consecutive_success_batches >= 1:
                    # 简单策略：每次成功将批量翻倍，直至不超过初始值
                    new_size = min(original_batch_size, max(1, content_batch_size * 2))
                    if new_size != content_batch_size:
                        self.logger.info(f"连续成功 {consecutive_success_batches} 次，提升批次大小：{content_batch_size} → {new_size}")
                        content_batch_size = new_size
            else:
                # 翻译失败
                # 尝试降级处理（debug和非debug模式都使用fallback机制）
                self.logger.warning(f"批次翻译失败，尝试降级处理")
                # 失败则重置连续成功计数
                consecutive_success_batches = 0
                
                if content_batch_size > 1:
                    # 减小批次大小
                    content_batch_size = max(1, content_batch_size // 2)
                    self.logger.info(f"降级批次大小到 {content_batch_size}")
                    continue
                else:
                    # 使用有内容的行进行小批次处理
                    self.logger.warning(f"使用有内容的行进行小批次处理，从第 {content_i+1} 行开始")
                    
                    # 收集接下来的有内容的行（最多5行）
                    fallback_content_lines = []
                    fallback_content_indices = []
                    j = content_i
                    while j < len(content_lines) and len(fallback_content_lines) < 5:
                        fallback_content_lines.append(content_lines[j])
                        fallback_content_indices.append(content_indices[j])
                        j += 1
                    
                    if fallback_content_lines:
                        fallback_start_idx = content_i
                        fallback_pairs: List[Tuple[str, str]] = []
                        from ..utils.format import create_bilingual_output
                        chinese_lines, _, success, _, current_io = self.translator.translate_lines_simple(
                            fallback_content_lines,
                            previous_io=previous_io,
                        )
                        
                        if success and len(chinese_lines) == len(fallback_content_lines):
                            bilingual_result = create_bilingual_output(fallback_content_lines, chinese_lines)
                            self.logger.debug(
                                f"小批次对照结果（有内容行 {content_i+1}-{content_i+len(fallback_content_lines)}）:\n{bilingual_result}"
                            )
                            for idx, trans_line in enumerate(chinese_lines):
                                target_body_idx = fallback_content_indices[idx]
                                translations_map[target_body_idx] = trans_line
                                fallback_pairs.append((fallback_content_lines[idx], trans_line))
                            previous_io = current_io
                            self.logger.info("fallback成功，保持当前较小批量，后续根据成功次数逐步回升")
                        else:
                            if self.config.debug:
                                self.logger.warning(f"小批次翻译失败，逐行处理有内容的行")
                                for idx, orig_line in enumerate(fallback_content_lines):
                                    single_line = [orig_line]
                                    single_trans, _, success, _, current_io = self.translator.translate_lines_simple(
                                        single_line,
                                        previous_io=previous_io,
                                    )
                                    target_body_idx = fallback_content_indices[idx]
                                    if success and len(single_trans) == 1:
                                        translation = single_trans[0]
                                        self.logger.debug(
                                            f"单行对照结果（第 {content_i+idx+1} 行）:\n"
                                            f"{create_bilingual_output([orig_line], [translation])}"
                                        )
                                        previous_io = current_io
                                    else:
                                        translation = orig_line
                                        self.logger.error(f"第 {content_i+idx+1} 行翻译完全失败，保留原文")
                                        self.logger.debug(
                                            f"失败对照结果（第 {content_i+idx+1} 行）:\n"
                                            f"{create_bilingual_output([orig_line], [translation])}"
                                        )
                                    translations_map[target_body_idx] = translation
                                    fallback_pairs.append((orig_line, translation))
                            else:
                                self.logger.warning(f"小批次翻译失败，非debug模式下标记所有行为翻译失败")
                                for idx, orig_line in enumerate(fallback_content_lines):
                                    target_body_idx = fallback_content_indices[idx]
                                    translation = "[翻译失败]"
                                    translations_map[target_body_idx] = translation
                                    fallback_pairs.append((orig_line, translation))

                        if fallback_pairs:
                            current_output_path = self._get_output_path(self.current_file_path)
                            self._update_bilingual_file_batch(
                                current_output_path,
                                fallback_start_idx,
                                fallback_start_idx + len(fallback_pairs),
                                fallback_pairs,
                            )
                            self._record_processing_state(
                                source_path=self.current_file_path,
                                output_path=current_output_path,
                                status="partial",
                                stage="body_fallback",
                                reason="fallback 批次已写入",
                                progress={
                                    "translated_content_lines": len(translations_map),
                                    "total_content_lines": len(content_lines),
                                    "completed_content_index": fallback_start_idx + len(fallback_pairs),
                                    "batch_size": len(fallback_pairs),
                                },
                            )
                            content_i = fallback_start_idx + len(fallback_pairs)
                        self.logger.info("逐行处理完成，保持当前较小批量，后续根据成功次数逐步回升")
                    else:
                        # 没有找到有内容的行，跳过空白行
                        self.logger.warning(f"从第 {content_i+1} 行开始没有找到有内容的行，跳过空白行")
                        content_i += 1
        
        # 重新组装完整文本
        result_lines = []
        
        # 保留YAML部分
        if start_idx > 0:
            result_lines.extend(lines[:start_idx])
        
        # 创建完整行映射：将翻译结果映射回原始文件结构
        for idx_body, line in enumerate(body_lines):
            if line.strip():  # 有内容的行
                result_lines.append(line.rstrip())
                translation = translations_map.get(idx_body, "[翻译失败]")
                result_lines.append(translation)
            else:  # 空白行
                result_lines.append("")
        
        # 统计翻译情况
        total_content_lines = len(content_lines)
        translated_count = len(translations_map)
        remaining_content_lines = total_content_lines - content_i  # 未处理的有内容行数
        
        if self.config.debug and content_i < total_content_lines:
            self.logger.warning(f"调试模式：翻译中断，剩余 {remaining_content_lines} 行有内容行未处理")
        if self.current_file_path and total_content_lines > 0:
            final_status = "complete" if content_i >= total_content_lines else "partial"
            final_reason = (
                "正文批次全部完成"
                if final_status == "complete"
                else f"仍有 {remaining_content_lines} 行有内容行未处理"
            )
            self._record_processing_state(
                source_path=self.current_file_path,
                output_path=self._get_output_path(self.current_file_path),
                status=final_status,
                stage="body_finish",
                reason=final_reason,
                progress={
                    "translated_content_lines": translated_count,
                    "total_content_lines": total_content_lines,
                    "remaining_content_lines": remaining_content_lines,
                },
            )
        
        self.logger.info(f"翻译完成：总计 {total_content_lines} 行有内容行，已翻译 {translated_count} 行")
        
        return '\n'.join(result_lines)
