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
        
        # 初始化组件
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
        if self.config.realtime_log:
            # 设置debug模式标志
            UnifiedLogger._debug_mode = self.config.debug
            
            # 在debug模式下，日志文件也放到输入文件同一目录
            if self.config.debug:
                log_dir = path.parent
            else:
                log_dir = self.config.log_dir
            
            # 文件日志 + 控制台输出由自定义 _emit 打印，避免 handler 再次打印导致重复
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
        else:
            self.logger.info(f"开始处理文件: {path}")
        
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
        
        # 检查是否需要处理
        if not self.config.overwrite and output_path.exists():
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
        
        # 在debug模式下，输出文件使用stem + timestamp格式
        if self.config.debug:
            from datetime import datetime
            ts = datetime.now().strftime('%Y%m%d-%H%M%S')
            return input_path.parent / f"{stem}_{ts}{suffix}.txt"
        else:
            return input_path.parent / f"{stem}{suffix}.txt"
    
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
                        self.logger.error(f"调试模式下分块 {idx} 降级三次仍失败，停止处理")
                        return ""
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
            self.logger.error("翻译失败")
            return ""
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
        i = 0
        
        while i < len(body_lines):
            # 确定当前批次
            end_idx = min(i + batch_size, len(body_lines))
            batch_lines = body_lines[i:end_idx]
            
            # 获取上下文
            context_before = []
            context_after = []
            
            if context_size > 0:
                # 前文上下文
                context_start = max(0, i - context_size)
                context_before = body_lines[context_start:i]
                
                # 后文上下文
                context_end = min(len(body_lines), end_idx + context_size)
                context_after = body_lines[end_idx:context_end]
            
            # 合并上下文
            context_lines = context_before + context_after
            
            self.logger.info(f"翻译批次 {i//batch_size + 1}: 行 {i+1}-{end_idx} (共{len(batch_lines)}行)")
            
            # 调用简化翻译
            chinese_lines, prompt, success, token_stats = self.translator.translate_lines_simple(
                target_lines=[line.rstrip() for line in batch_lines],
                context_lines=[line.rstrip() for line in context_lines]
            )
            
            if success and len(chinese_lines) == len(batch_lines):
                # 拼接原文和译文
                for j, (orig_line, chinese_line) in enumerate(zip(batch_lines, chinese_lines)):
                    orig_stripped = orig_line.rstrip()
                    # 避免空行重复：如果原文是空行，只添加一个空行
                    if orig_stripped == "" and chinese_line == "":
                        translated_lines.append("")
                    else:
                        translated_lines.append(orig_stripped)
                        translated_lines.append(chinese_line)
                
                self.logger.info(f"批次翻译成功，Token使用: {token_stats}")
                i = end_idx
            else:
                # 翻译失败
                if self.config.debug:
                    # debug模式下直接报错返回
                    self.logger.error(f"调试模式：批次翻译失败，行数不匹配（期望{len(batch_lines)}行，实际{len(chinese_lines)}行），停止处理")
                    return ""
                else:
                    # 非debug模式下尝试降级处理
                    self.logger.warning(f"批次翻译失败，尝试降级处理")
                    
                    if batch_size > 1:
                        # 减小批次大小
                        batch_size = max(1, batch_size // 2)
                        self.logger.info(f"降级批次大小到 {batch_size}")
                        continue
                    else:
                        # 逐行处理
                        self.logger.warning(f"逐行处理第 {i+1} 行")
                        single_line = [body_lines[i].rstrip()]
                        chinese_lines, _, success, _ = self.translator.translate_lines_simple(single_line)
                        
                        if success and len(chinese_lines) == 1:
                            translated_lines.append(body_lines[i].rstrip())
                            translated_lines.append(chinese_lines[0])
                            i += 1
                        else:
                            # 完全失败，保留原文
                            self.logger.error(f"第 {i+1} 行翻译完全失败，保留原文")
                            translated_lines.append(body_lines[i].rstrip())
                            translated_lines.append(body_lines[i].rstrip())  # 原文作为译文
                            i += 1
        
        # 重新组装完整文本
        result_lines = []
        
        # 保留YAML部分
        if start_idx > 0:
            result_lines.extend(lines[:start_idx])
        
        # 添加翻译后的正文
        result_lines.extend(translated_lines)
        
        return '\n'.join(result_lines)
