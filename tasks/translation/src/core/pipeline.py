#!/usr/bin/env python3
"""
翻译流程控制模块
"""

import time
from pathlib import Path
from typing import List, Tuple, Dict, Optional

from .config import TranslationConfig
from .logger import UnifiedLogger
from .quality_checker import QualityChecker
from .translator import Translator
from .file_handler import FileHandler
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
        
        # 初始化组件（默认开启文件日志；仅当realtime_log关闭且无法定位文件时才退回控制台）
        self.logger = UnifiedLogger.create_console_only()
        self.quality_checker = QualityChecker(config, self.logger)
        self.translator = Translator(config, self.logger, self.quality_checker)
        self.file_handler = FileHandler(config, self.logger, self.quality_checker)
    
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
        files_to_process = self.file_handler.find_files_to_process(inputs)
        
        if not files_to_process:
            self.logger.warning("没有找到需要处理的文件")
            return 0
        
        self.logger.info(f"开始处理 {len(files_to_process)} 个文件")
        
        # 应用限制
        if self.config.offset > 0:
            files_to_process = files_to_process[self.config.offset:]
            self.logger.info(f"跳过前 {self.config.offset} 个文件，剩余: {len(files_to_process)} 个文件")
        
        if self.config.limit > 0:
            files_to_process = files_to_process[:self.config.limit]
            self.logger.info(f"限制处理文件数量为: {len(files_to_process)}")
        
        # 处理文件
        success_count = 0
        for i, file_path in enumerate(files_to_process, 1):
            self.logger.info(f"处理文件 {i}/{len(files_to_process)}: {file_path}")
            
            # 在显式调试模式下限制重试次数以加快迭代
            if getattr(self.config, 'debug', False):
                if self.config.retries > 1:
                    self.logger.info("调试模式下将重试次数限制为 1")
                    self.config.retries = 1

            if self.process_file(file_path):
                success_count += 1
            else:
                self.logger.error(f"文件处理失败: {file_path}")
        
        self.logger.info(f"处理完成: {success_count}/{len(files_to_process)} 个文件成功")
        return success_count
    
    def process_file(self, path: Path) -> bool:
        """
        处理单个文件
        
        Args:
            path: 文件路径
        
        Returns:
            是否处理成功
        """
        # 设置日志
        log_file_path = None
        # 默认开启文件日志；仅当显式要求关闭时才不创建
        UnifiedLogger._debug_mode = self.config.debug
        log_dir = path.parent if self.config.debug else self.config.log_dir
        self.logger = UnifiedLogger.create_for_file(path, log_dir, stream_output=False)
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
        
        # 显示配置信息
        self._log_config_info()
        
        # 读取文件内容
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            self.logger.error(f"读取文件失败: {e}")
            return False
        
        # 解析YAML front matter
        yaml_data, text_content = parse_yaml_front_matter(content)
        
        # 显示文章信息
        self._log_article_info(yaml_data, len(text_content))
        
        # 确定输出文件路径
        output_path = self._get_output_path(path)
        
        # 设置当前文件路径（用于批次更新）
        self.current_file_path = path
        
        # 检查是否需要处理
        if not self.config.overwrite and output_path.exists():
            # Debug模式下，每次都是新文件（带时间戳），不需要跳过
            if self.config.debug:
                self.logger.info(f"Debug模式：文件已存在但会重新处理: {output_path}")
            else:
                # 对于bilingual_simple模式，需要检查文件质量
                if self.config.bilingual_simple:
                    # 使用质量检查器检查现有文件质量
                    if self.file_handler._check_existing_bilingual_quality(output_path):
                        self.logger.info(f"高质量双语文件已存在，跳过: {output_path}")
                        return True
                    else:
                        self.logger.info(f"低质量双语文件存在，将重新翻译: {output_path}")
                        # 删除低质量文件
                        try:
                            output_path.unlink()
                            self.logger.info(f"已删除低质量文件: {output_path}")
                        except Exception as e:
                            self.logger.warning(f"删除低质量文件失败: {e}")
                else:
                    self.logger.info(f"输出文件已存在，跳过: {output_path}")
                    return True
        
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
                    series_title_v = None
                    tags_v: list[str] | None = None
                    for ln in yaml_raw.splitlines():
                        s = ln.strip()
                        if s.startswith('title:') and not ln.startswith('  '):
                            title_v = s.split(':',1)[1].strip()
                        elif s.startswith('caption:'):
                            caption_v = s.split(':',1)[1].strip()
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
                    series_title_v = None
                    tags_v: list[str] | None = None
                    for ln in yaml_raw.splitlines():
                        s = ln.strip()
                        if s.startswith('title:') and not ln.startswith('  '):
                            title_v = s.split(':',1)[1].strip()
                        elif s.startswith('caption:'):
                            caption_v = s.split(':',1)[1].strip()
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
            
            # 若仅翻译元数据，则不处理正文
            if getattr(self.config, 'metadata_only', False):
                translated_content = yaml_translated
            else:
                # 翻译正文（保留现有分块逻辑）
                body_translated = self._translate_text(body_raw, use_body_prompt=True)
                if not body_translated:
                    self.logger.error("正文翻译失败")
                    return False
                translated_content = f"{yaml_translated}\n{body_translated}"
        else:
            # 无 YAML，直接按正文处理
            if getattr(self.config, 'metadata_only', False):
                self.logger.warning("启用了 --metadata-only 但输入不含 YAML，跳过文件")
                return False
            
            # 如果是bilingual_simple模式，先预创建文件
            if self.config.bilingual_simple:
                self._create_prefilled_bilingual_file(content, output_path)
            
            translated_content = self._translate_text(content)
        
        if not translated_content:
            self.logger.error("翻译失败")
            return False
        
        # 保存结果
        return self._save_result(output_path, translated_content, yaml_data)
    
    def _log_config_info(self) -> None:
        """记录配置信息"""
        self.logger.info("🔧 翻译配置:")
        self.logger.info(f"   模型: {self.config.model}")
        self.logger.info(f"   模式: {self.config.mode}")
        self.logger.info(f"   对照模式: {self.config.bilingual}")
        self.logger.info(f"   流式输出: {self.config.stream}")
        self.logger.info(f"   实时日志: {self.config.realtime_log}")
        self.logger.info(f"   块大小: {self.config.chunk_size_chars} 字符")
        self.logger.info(f"   重叠大小: {self.config.overlap_chars} 字符")
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
            if self.config.bilingual or self.config.bilingual_simple:
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
        
        max_ctx = self.config.get_max_context_length()
        estimated_input_tokens = len(text_content) // 2
        margin = 2000
        # 在双语模式下更积极地分块，避免输出被截断
        bilingual_long = self.config.bilingual and len(text_content) > 8000
        need_chunk = (
            self.config.mode == "chunked"
            or estimated_input_tokens > (max_ctx - margin)
            or len(text_content) > self.config.chunk_size_chars
            or bilingual_long
        ) or (self.config.bilingual and len(text_content) > 6000)

        # 优先使用行级固定分块（若配置指定）
        if need_chunk or (self.config.line_chunk_size_lines and self.config.line_chunk_size_lines > 0):
            self.logger.info("输入较长，启用分块翻译（按行+行重叠）…")
            # 行级分块，避免拆断行导致双语错位
            lines = text_content.splitlines(keepends=True)

            # 估算平均行长用于从字符配置推导行数
            total_len = sum(len(l) for l in lines) or 1
            avg_line_len = max(30, min(120, total_len // max(1, len(lines))))
            # 目标每块行数
            if self.config.line_chunk_size_lines and self.config.line_chunk_size_lines > 0:
                target_chunk_lines = max(1, self.config.line_chunk_size_lines)
                # 重叠
                overlap_lines = max(0, self.config.line_overlap_lines or 0)
            else:
                target_chunk_lines = max(200, min(self.config.chunk_size_chars // avg_line_len, 360))
                base_overlap = 30
                extra_overlap = 12 if self.config.bilingual else 0
                overlap_lines = base_overlap + extra_overlap

            # 避免在 YAML front matter 中间断开：若存在 YAML，仅让其出现在第一个分块
            yaml_end_idx = -1
            if lines and lines[0].strip() == '---':
                for i, ln in enumerate(lines[1:], start=1):
                    if ln.strip() == '---':
                        yaml_end_idx = i
                        break

            chunks: list[str] = []
            start_line = 0
            total_lines = len(lines)
            while start_line < total_lines:
                end_line = min(total_lines, start_line + target_chunk_lines)
                # 若起点在YAML内，则强制扩展到 YAML 结束行
                if yaml_end_idx >= 0 and start_line <= yaml_end_idx and end_line <= yaml_end_idx:
                    end_line = min(total_lines, yaml_end_idx + 1 + target_chunk_lines)
                chunk_text = ''.join(lines[start_line:end_line])
                chunks.append(chunk_text)
                if end_line >= total_lines:
                    break
                # 下一块起点：行级重叠
                start_line = max(0, end_line - overlap_lines)

            results: list[str] = []
            for idx, chunk in enumerate(chunks, 1):
                line_count = chunk.count("\n") + 1
                self.logger.info(f"翻译分块 {idx}/{len(chunks)}，行数: {line_count}")

                # 降级重试策略：若整块质量不佳/失败，则按更小行块重试，最多降级3次
                degrade_ratios = [1.0, 0.7, 0.5, 0.35]
                translated_ok = False
                final_piece = ""

                for attempt_i, ratio in enumerate(degrade_ratios, 1):
                    if ratio >= 0.99:
                        # 直接整块尝试
                        if use_body_prompt:
                            result, prompt, success, token_meta = self.translator.translate_body_text(chunk, chunk_index=idx)
                        else:
                            result, prompt, success, token_meta = self.translator.translate_text(chunk, chunk_index=idx)
                        if success and result:
                            self.logger.info(f"分块 {idx} 直接翻译成功（尝试 {attempt_i}/{len(degrade_ratios)}）")
                            translated_ok = True
                            final_piece = result
                            break
                        else:
                            self.logger.warning(f"分块 {idx} 直接翻译质量不佳/失败（尝试 {attempt_i}/{len(degrade_ratios)}），降级重试…")
                    else:
                        # 将当前分块再细分为更小的行块进行翻译
                        sub_lines = chunk.splitlines(keepends=True)
                        per_lines = max(60, int(target_chunk_lines * ratio))
                        sub_overlap = max(10, overlap_lines // 2)
                        sub_results: list[str] = []
                        sub_ok_all = True
                        pos = 0
                        total = len(sub_lines)
                        sub_idx = 0
                        while pos < total:
                            sub_idx += 1
                            sub_end = min(total, pos + per_lines)
                            sub_text = ''.join(sub_lines[pos:sub_end])
                            sub_line_count = sub_text.count("\n") + 1
                            self.logger.info(f"分块 {idx} 降级子块 {sub_idx} 行数: {sub_line_count}")
                            if use_body_prompt:
                                r, p, s, t = self.translator.translate_body_text(sub_text, chunk_index=f"{idx}.{sub_idx}")
                            else:
                                r, p, s, t = self.translator.translate_text(sub_text, chunk_index=f"{idx}.{sub_idx}")
                            if not s or not r:
                                sub_ok_all = False
                                self.logger.warning(f"分块 {idx} 降级子块 {sub_idx} 翻译失败")
                                # 该降级方案失败，跳出等待下一轮更小的降级
                                break
                            sub_results.append(r)
                            if sub_end >= total:
                                break
                            pos = max(0, sub_end - sub_overlap)

                        if sub_ok_all and sub_results:
                            translated_ok = True
                            final_piece = "\n".join(sub_results)
                            self.logger.info(f"分块 {idx} 降级方案 ratio={ratio:.2f} 成功（尝试 {attempt_i}/{len(degrade_ratios)}）")
                            break

                if not translated_ok:
                    if self.config.debug:
                        self.logger.error(f"调试模式下分块 {idx} 降级三次仍失败，保留原文继续处理")
                        final_piece = chunk_text  # 保留原文而不是返回空字符串
                else:
                        self.logger.warning(f"分块 {idx} 多次降级仍失败，返回空字符串以继续拼接")
                        final_piece = ""

                results.append(final_piece)
            return "\n".join(results)

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

    def _update_bilingual_file_batch(self, output_path: Path, batch_start_idx: int, batch_end_idx: int, 
                                    bilingual_lines: list) -> None:
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
        
        # 更新文件内容
        bilingual_lines_split = []
        for line in bilingual_lines:
            bilingual_lines_split.extend(line.split('\n'))
        
        for i, bilingual_line in enumerate(bilingual_lines_split):
            file_idx = file_start_idx + i
            if file_idx < len(lines):
                # 替换对应的行
                lines[file_idx] = bilingual_line + '\n'
        
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
        
        translated_lines = []
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
                batch_content_lines, previous_io=previous_io
            )
            
            if success and len(chinese_lines) == len(batch_content_lines):
                # 使用统一的bilingual工具函数拼接原文和译文
                from ..utils.format import create_bilingual_output
                
                # 准备原文和译文行
                orig_lines = batch_content_lines
                bilingual_result = create_bilingual_output(orig_lines, chinese_lines)
                
                # 记录对照版结果到日志
                self.logger.debug(f"批次对照结果（有内容行 {content_i+1}-{content_end_idx}）:\n{bilingual_result}")
                
                # 将对照结果按行添加到翻译结果中
                translated_lines.extend(bilingual_result.split('\n'))
                
                # 更新预创建的双语文件
                current_output_path = self._get_output_path(self.current_file_path)
                self._update_bilingual_file_batch(current_output_path, content_i, content_end_idx, 
                                                bilingual_result.split('\n'))
                
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
                        # 翻译有内容的行
                        chinese_lines, _, success, _, current_io = self.translator.translate_lines_simple(fallback_content_lines, previous_io=previous_io)
                        
                        if success and len(chinese_lines) == len(fallback_content_lines):
                            # 使用统一的bilingual工具函数拼接
                            from ..utils.format import create_bilingual_output
                            
                            bilingual_result = create_bilingual_output(fallback_content_lines, chinese_lines)
                            
                            # 记录小批次对照结果到日志
                            self.logger.debug(f"小批次对照结果（有内容行 {content_i+1}-{content_i+len(fallback_content_lines)}）:\n{bilingual_result}")
                            
                            # 将对照结果按行添加到翻译结果中
                            translated_lines.extend(bilingual_result.split('\n'))
                            
                            # 更新前一次的输入输出（使用翻译器返回的 current_io）
                            previous_io = current_io
                            
                            # 跳过已处理的行
                            content_i = content_i + len(fallback_content_lines)
                            # fallback成功：保持当前较小批量，后续通过连续成功逐步回升
                            self.logger.info("fallback成功，保持当前较小批量，后续根据成功次数逐步回升")
                        else:
                            # 小批次也失败，根据模式决定处理方式
                            if self.config.debug:
                                # debug模式：逐行处理有内容的行
                                self.logger.warning(f"小批次翻译失败，逐行处理有内容的行")
                                for idx, orig_line in enumerate(fallback_content_lines):
                                    single_line = [orig_line]
                                    chinese_lines, _, success, _, current_io = self.translator.translate_lines_simple(single_line, previous_io=previous_io)
                                
                                if success and len(chinese_lines) == 1:
                                    # 使用统一的bilingual工具函数拼接单行
                                    from ..utils.format import create_bilingual_output
                                    
                                    bilingual_result = create_bilingual_output([orig_line], chinese_lines)
                                    
                                    # 记录单行对照结果到日志
                                    self.logger.debug(f"单行对照结果（第 {content_i+idx+1} 行）:\n{bilingual_result}")
                                    
                                    # 将对照结果按行添加到翻译结果中
                                    translated_lines.extend(bilingual_result.split('\n'))
                                    
                                    # 更新前一次的输入输出
                                    previous_io = current_io
                                else:
                                    # 完全失败，保留原文
                                    self.logger.error(f"第 {content_i+idx+1} 行翻译完全失败，保留原文")
                                    
                                    # 使用统一的bilingual工具函数处理失败情况
                                    from ..utils.format import create_bilingual_output
                                    
                                    # 非debug模式下，在译文部分标明"翻译失败"
                                    if self.config.debug:
                                        # debug模式：译文部分也是原文
                                        bilingual_result = create_bilingual_output([orig_line], [orig_line])
                                    else:
                                        # 非debug模式：译文部分标明"翻译失败"
                                        bilingual_result = create_bilingual_output([orig_line], ["[翻译失败]"])
                                    
                                    # 记录失败对照结果到日志
                                    self.logger.debug(f"失败对照结果（第 {content_i+idx+1} 行）:\n{bilingual_result}")
                                    
                                    # 将对照结果按行添加到翻译结果中
                                    translated_lines.extend(bilingual_result.split('\n'))
                            
                                # 跳过已处理的行
                                content_i = content_i + len(fallback_content_lines)
                                # 逐行处理完成：保持当前较小批量，后续逐步回升
                                self.logger.info("逐行处理完成，保持当前较小批量，后续根据成功次数逐步回升")
                            else:
                                # 非debug模式：直接标记所有行为"翻译失败"
                                self.logger.warning(f"小批次翻译失败，非debug模式下标记所有行为翻译失败")
                                from ..utils.format import create_bilingual_output
                                
                                for idx, orig_line in enumerate(fallback_content_lines):
                                    bilingual_result = create_bilingual_output([orig_line], ["[翻译失败]"])
                                    translated_lines.extend(bilingual_result.split('\n'))
                                
                                # 跳过已处理的行
                                content_i = content_i + len(fallback_content_lines)
                                # 非debug失败标记处理完成：保持当前较小批量，后续逐步回升
                                self.logger.info("非debug模式失败处理完成，保持当前较小批量，后续根据成功次数逐步回升")
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
        full_translated_lines = []
        content_idx = 0
        
        for i, line in enumerate(body_lines):
            if line.strip():  # 有内容的行
                if content_idx < len(translated_lines):
                    # 添加原文和译文
                    full_translated_lines.append(translated_lines[content_idx])
                    if content_idx + 1 < len(translated_lines):
                        full_translated_lines.append(translated_lines[content_idx + 1])
                    content_idx += 2
                else:
                    # 未翻译的行，按要求标记译文为[翻译失败]
                    full_translated_lines.append(line.rstrip())
                    full_translated_lines.append("[翻译失败]")
            else:  # 空白行
                full_translated_lines.append("")
        
        # 添加翻译后的正文
        result_lines.extend(full_translated_lines)
        
        # 统计翻译情况
        total_content_lines = len(content_lines)
        translated_count = len(translated_lines) // 2  # 每行原文+译文
        remaining_content_lines = total_content_lines - content_i  # 未处理的有内容行数
        
        if self.config.debug and content_i < total_content_lines:
            self.logger.warning(f"调试模式：翻译中断，剩余 {remaining_content_lines} 行有内容行未处理")
        
        self.logger.info(f"翻译完成：总计 {total_content_lines} 行有内容行，已翻译 {translated_count} 行")
        
        return '\n'.join(result_lines)
