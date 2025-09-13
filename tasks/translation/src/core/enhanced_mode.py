#!/usr/bin/env python3
"""
增强模式处理模块
实现QC检测 + 重新翻译功能
"""

import re
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

from .config import TranslationConfig
from .streaming_handler import StreamingHandler
from .logger import UnifiedLogger
from .prompt import PromptBuilder, create_config


@dataclass
class QCResult:
    """QC检测结果"""
    line_index: int
    original_text: str
    translated_text: str
    quality_score: float
    needs_retranslation: bool
    reason: str = ""


class EnhancedModeHandler:
    """增强模式处理器"""
    
    def __init__(self, config: TranslationConfig, logger: UnifiedLogger):
        self.config = config
        self.logger = logger
        
        # 初始化OpenAI客户端
        from openai import OpenAI
        self.client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")
        
        self.streaming_handler = StreamingHandler(self.client, logger, config)
        self.previous_improvements = {}  # 跟踪之前的改进
        
        # 初始化PromptBuilder
        prompt_data_dir = Path(__file__).parent.parent.parent / "data" / "prompt"
        qc_config = create_config("qc", prompt_data_dir)
        # 手动设置正确的文件路径
        qc_config.preface_file = "preface_qc.txt"
        qc_config.sample_file = "sample_qc.txt"
        self.qc_prompt_builder = PromptBuilder(qc_config)
        
        enhancement_config = create_config("enhancement", prompt_data_dir)
        # 手动设置正确的文件路径
        enhancement_config.preface_file = "preface_enhanced.txt"
        enhancement_config.sample_file = "sample_enhanced.txt"
        enhancement_config.terminology_file = "terminology.txt"
        self.enhancement_prompt_builder = PromptBuilder(enhancement_config)
    
    def process_bilingual_file(self, file_path: Path) -> bool:
        """
        处理双语文件，进行QC检测和重新翻译
        
        Args:
            file_path: 双语文件路径
            
        Returns:
            bool: 处理是否成功
        """
        try:
            self.logger.info(f"开始增强模式处理: {file_path}")
            # 记录当前处理文件，便于批次打印
            self.current_processing_file = file_path
            # 进入时即确定输出路径并在 copy 策略下预创建目标文件，打印路径（对齐 bilingual_simple 行为）
            target_path = self._resolve_output_path(file_path)
            # 若未指定覆盖且输出已存在，则直接跳过（与普通流程一致）
            try:
                if not getattr(self.config, 'overwrite', False) and target_path.exists():
                    self.logger.info(f"输出文件已存在，跳过: {target_path}")
                    return True
            except Exception:
                # 容错：目标路径检查异常时继续后续流程
                pass
            try:
                # 读取原文行（用于可能的预创建）
                lines_peek = self._read_bilingual_file(file_path)
                if self.config.enhanced_output == 'copy':
                    # 预创建（复制原文件，不做占位填充）
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(''.join(lines_peek), encoding='utf-8')
                # 打印输出与日志位置（debug 下与目标同目录；非 debug 日志在 logs/）
                log_file = self.logger.get_log_file_path() if hasattr(self.logger, 'get_log_file_path') else None
                self.logger.info(f"📄 输出文件: {target_path}", mode=UnifiedLogger.LogMode.BOTH)
                if log_file:
                    self.logger.info(f"📝 日志文件路径: {log_file}", mode=UnifiedLogger.LogMode.BOTH)
            except Exception as e:
                self.logger.warning(f"预创建/打印增强输出文件路径失败: {e}")
            
            # 读取双语文件
            lines = self._read_bilingual_file(file_path)
            if not lines:
                self.logger.error(f"无法读取文件: {file_path}")
                return False
            
            # 解析双语内容
            content_lines = self._parse_bilingual_content(lines)
            if not content_lines:
                self.logger.error(f"无法解析双语内容: {file_path}")
                return False
            
            # 直接使用增强模型处理所有行（跳过QC检测）
            self.logger.info(f"开始增强模式处理: 总行数={len(content_lines)}")
            retranslated_lines = self._enhance_all_lines_batch(content_lines, original_lines=lines, target_path=target_path)

            # 计算目标输出路径（默认复制输出）
            target_path = self._resolve_output_path(file_path)
            if target_path != file_path:
                # 目标文件应在进入时已复制；此处只做行级更新
                self._update_bilingual_file(target_path, lines, content_lines, retranslated_lines)
            else:
                # 原地改写
                self._update_bilingual_file(file_path, lines, content_lines, retranslated_lines)

            # 打印输出与日志位置
            log_file = self.logger.get_log_file_path() if hasattr(self.logger, 'get_log_file_path') else None
            self.logger.info(f"📄 输出文件: {target_path}", mode=UnifiedLogger.LogMode.BOTH)
            if log_file:
                self.logger.info(f"📝 日志文件路径: {log_file}", mode=UnifiedLogger.LogMode.BOTH)
            
            self.logger.info(f"增强模式处理完成: {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"增强模式处理失败: {file_path}, 错误: {e}")
            return False
    
    def _read_bilingual_file(self, file_path: Path) -> List[str]:
        """读取双语文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.readlines()
    
    def _parse_bilingual_content(self, lines: List[str]) -> List[Tuple[str, str]]:
        """
        解析双语内容，提取原文和译文对
        格式：原文行\n译文行\n（bilingual_simple模式）
        
        Returns:
            List[Tuple[str, str]]: [(原文, 译文), ...]
        """
        content_lines = []
        i = 0
        
        # 找到YAML结束位置：跳过所有YAML内容直到第二个---或实际内容开始
        yaml_started = False
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('---'):
                if not yaml_started:
                    yaml_started = True
                else:
                    # 找到第二个---，YAML结束
                    i += 1
                    break
            elif yaml_started and not line.startswith('---'):
                # 在YAML中，继续跳过
                pass
            elif not yaml_started and line and not line.startswith('---'):
                # 没有YAML，直接开始解析内容
                break
            i += 1
        
        # 解析双语内容：按照bilingual_simple格式（原文行\n译文行\n）
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # 检查是否是原文行（不包含[翻译未完成]标记）
            if not line.startswith('[') and not line.endswith(']'):
                original = line
                i += 1
                
                # 查找对应的译文行
                if i < len(lines):
                    translated = lines[i].strip()
                    # 检查是否是译文行（包括[翻译未完成]标记）
                    if translated == "[翻译未完成]":
                        # 找到[翻译未完成]标记，将其作为译文处理
                        content_lines.append((original, "[翻译未完成]"))
                        self.logger.debug(f"未翻译: 原文='{original}', 译文='[翻译未完成]'")
                    else:
                        # 正常译文
                        content_lines.append((original, translated))
                        self.logger.debug(f"解析成功: 原文='{original}', 译文='{translated}'")
                    i += 1
                else:
                    content_lines.append((original, "[翻译未完成]"))
                    self.logger.debug(f"文件结束: 原文='{original}', 译文='[翻译未完成]'")
            else:
                # 跳过其他行（如[翻译未完成]标记等）
                self.logger.debug(f"跳过标记行: '{line}'")
                i += 1
        
        self.logger.info(f"解析完成: 共{len(content_lines)}对双语内容")
        return content_lines
    
    def _contains_chinese(self, text: str) -> bool:
        """检查文本是否包含中文字符（排除日文）"""
        # 检查是否包含平假名、片假名或日文特有的标点符号
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff\u3000-\u303f]', text):
            return False  # 包含日文字符，不是中文
        
        # 检查是否包含中文字符
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        if not chinese_chars:
            return False
        
        # 如果包含中文字符，进一步检查是否主要是中文
        # 如果中文字符数量明显多于日文字符，则认为是中文
        japanese_chars = re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text)
        return len(chinese_chars) > len(japanese_chars)
    
    def _qc_detect_lines(self, content_lines: List[Tuple[str, str]]) -> List[QCResult]:
        """
        批量QC检测
        
        Args:
            content_lines: 双语内容列表
            
        Returns:
            List[QCResult]: QC检测结果列表
        """
        qc_results = []
        
        # 过滤出需要检测的行
        lines_to_check = []
        line_indices = []
        
        for i, (original, translated) in enumerate(content_lines):
            if self._contains_chinese(original):
                # 跳过纯中文行，直接给满分
                qc_results.append(QCResult(
                    line_index=i,
                    original_text=original,
                    translated_text=translated,
                    quality_score=1.0,
                    needs_retranslation=False,
                    reason="纯中文行"
                ))
                continue
            
            lines_to_check.append((original, translated))
            line_indices.append(i)
        
        if not lines_to_check:
            return qc_results
        
        # 批量QC检测
        try:
            scores = self._check_quality_batch_llm(lines_to_check)
            
            # 将分数映射回原始索引
            for i, score in enumerate(scores):
                original_idx = line_indices[i]
                original, translated = content_lines[original_idx]
                
                # 特殊处理[翻译未完成]标记
                if translated == "[翻译未完成]":
                    needs_retranslation = True
                    quality_score = 0.0
                    reason = "未翻译"
                else:
                    needs_retranslation = score < self.config.enhanced_qc_threshold
                    quality_score = score
                    reason = f"质量分数: {score:.2f}"
                
                qc_results.append(QCResult(
                    line_index=original_idx,
                    original_text=original,
                    translated_text=translated,
                    quality_score=quality_score,
                    needs_retranslation=needs_retranslation,
                    reason=reason
                ))
                
        except Exception as e:
            self.logger.error(f"批量QC检测失败: {e}")
            # 降级到逐行检测
            for i, (original, translated) in enumerate(lines_to_check):
                original_idx = line_indices[i]
                
                # 特殊处理[翻译未完成]标记
                if translated == "[翻译未完成]":
                    needs_retranslation = True
                    quality_score = 0.0
                    reason = "未翻译"
                else:
                    quality_score = self._llm_quality_check(original, translated)
                    needs_retranslation = quality_score < self.config.enhanced_qc_threshold
                    reason = f"质量分数: {quality_score:.2f}"
                
                qc_results.append(QCResult(
                    line_index=original_idx,
                    original_text=original,
                    translated_text=translated,
                    quality_score=quality_score,
                    needs_retranslation=needs_retranslation,
                    reason=reason
                ))
        
        return qc_results
    
    def _check_quality_batch_llm(self, lines_to_check: List[Tuple[str, str]]) -> List[float]:
        """
        使用LLM批量检测翻译质量
        
        Args:
            lines_to_check: 需要检测的原文和译文对列表
            
        Returns:
            List[float]: 质量分数列表
        """
        try:
            # 使用PromptBuilder构建QC消息
            target_lines = [original for original, _ in lines_to_check]
            translated_lines = [translated for _, translated in lines_to_check]
            
            messages = self.qc_prompt_builder.build_messages(
                target_lines=target_lines,
                translated_lines=translated_lines
            )
            
            # 动态计算max_tokens，参考translator.py的逻辑
            estimated_input_tokens = self._estimate_tokens(messages)
            max_context_length = self.config.get_max_context_length()
            
            if self.config.max_tokens > 0:
                max_tokens = self.config.max_tokens
            else:
                # 动态计算max_tokens
                safety_margin = 1024
                remain = max_context_length - estimated_input_tokens - safety_margin
                if remain < 500:
                    remain = 500
                max_tokens = min(remain, 25000)  # 设置25000的上限
            
            self.logger.info(f"QC检测动态计算 max_tokens: {max_tokens} (基于输入tokens: {estimated_input_tokens}, 模型上下文长度: {max_context_length})")
            
            result, token_stats = self.streaming_handler.stream_completion(
                model=self.config.model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens
            )
            
            # 解析分数
            scores = self._parse_qc_scores(result, len(lines_to_check))
            
            self.logger.info(f"批量QC检测完成: {len(lines_to_check)}行, 分数: {scores}")
            return scores
            
        except Exception as e:
            self.logger.error(f"批量QC检测失败: {e}")
            raise
    
    def _parse_qc_scores(self, result: str, expected_count: int) -> List[float]:
        """
        解析QC检测的分数结果
        
        Args:
            result: LLM输出结果
            expected_count: 期望的分数数量
            
        Returns:
            List[float]: 解析出的分数列表
        """
        # 提取纯净的分数（去除思考过程）
        clean_result = self._extract_clean_qc_scores(result)
        
        # 按行分割并提取数字
        lines = clean_result.split('\n')
        scores = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 尝试提取数字
            match = re.search(r'(\d+\.?\d*)', line)
            if match:
                try:
                    score = float(match.group(1))
                    # 确保分数在0-1范围内
                    score = max(0.0, min(1.0, score))
                    scores.append(score)
                except ValueError:
                    continue
        
        # 如果分数数量不够，用默认分数填充
        while len(scores) < expected_count:
            scores.append(0.5)  # 默认中等分数
        
        # 如果分数数量过多，截取前面的
        if len(scores) > expected_count:
            scores = scores[:expected_count]
        
        return scores
    
    def _extract_clean_qc_scores(self, result: str) -> str:
        """
        从LLM输出中提取纯净的QC分数
        
        Args:
            result: LLM原始输出
            
        Returns:
            str: 纯净的分数文本
        """
        # 移除思考标签
        clean_result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
        
        # 移除其他标签
        clean_result = re.sub(r'<[^>]+>', '', clean_result)
        
        # 移除常见的对话标记
        clean_result = re.sub(r'\[翻译完成\]', '', clean_result)
        clean_result = re.sub(r'\[END\]', '', clean_result)
        
        return clean_result.strip()
    
    def _estimate_tokens(self, messages: List[dict]) -> int:
        """
        估算消息的token数量
        
        Args:
            messages: 消息列表
            
        Returns:
            int: 估算的token数量
        """
        total_chars = 0
        for message in messages:
            if isinstance(message, dict) and 'content' in message:
                total_chars += len(message['content'])
        
        # 粗略估算：中文约1.5字符/token，英文约4字符/token
        # 这里使用保守估算：2字符/token
        estimated_tokens = total_chars // 2
        
        # 添加一些余量
        return int(estimated_tokens * 1.2)
    
    def _llm_quality_check(self, original: str, translated: str) -> float:
        """
        使用LLM进行质量检测（逐行）
        
        Args:
            original: 原文
            translated: 译文
            
        Returns:
            float: 质量分数 (0-1)
        """
        try:
            # 使用统一的prompt构建方法
            messages = self._build_qc_messages([(original, translated)])
            
            # 动态计算max_tokens
            estimated_input_tokens = self._estimate_tokens(messages)
            max_context_length = self.config.get_max_context_length()
            
            if self.config.max_tokens > 0:
                max_tokens = self.config.max_tokens
            else:
                safety_margin = 1024
                remain = max_context_length - estimated_input_tokens - safety_margin
                if remain < 500:
                    remain = 500
                max_tokens = min(remain, 25000)
            
            result, token_stats = self.streaming_handler.stream_completion(
                model=self.config.model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens
            )
            
            # 解析分数
            scores = self._parse_qc_scores(result, 1)
            return scores[0] if scores else 0.5
                
        except Exception as e:
            self.logger.error(f"LLM质量检测失败: {e}")
            return 0.5  # 默认中等分数
    
    def _retranslate_lines(self, content_lines: List[Tuple[str, str]], 
                          needs_retranslation: List[QCResult]) -> Dict[int, str]:
        """
        重新翻译质量不佳的行
        
        Args:
            content_lines: 所有双语内容
            needs_retranslation: 需要重新翻译的行
            
        Returns:
            Dict[int, str]: {行索引: 新译文}
        """
        retranslated = {}
        
        for qc_result in needs_retranslation:
            line_index = qc_result.line_index
            original = qc_result.original_text
            
            # 获取上下文
            context_lines = self._get_context_lines(content_lines, line_index)
            
            # 重新翻译
            new_translation = self._retranslate_single_line(original, context_lines)
            
            if new_translation:
                retranslated[line_index] = new_translation
                self.logger.info(f"重新翻译完成: 行{line_index+1}")
            else:
                self.logger.warning(f"重新翻译失败: 行{line_index+1}")
        
        return retranslated

    def _enhance_all_lines_batch(self, content_lines: List[Tuple[str, str]], original_lines: List[str], target_path: Path) -> Dict[int, str]:
        """直接增强所有行：让模型检查并改进所有行"""
        enhanced: Dict[int, str] = {}
        if not content_lines:
            return enhanced
        
        batch_size = max(1, int(getattr(self.config, 'enhanced_batch_size', 10)))
        
        # 组批处理所有行
        for start in range(0, len(content_lines), batch_size):
            end = min(start + batch_size, len(content_lines))
            batch_lines = content_lines[start:end]
            
            # 构建previous_io（除了第一批）
            previous_io = None
            if start > 0:
                # 获取前一批的输出作为previous_io
                prev_start = max(0, start - batch_size)
                prev_end = start
                prev_batch_lines = content_lines[prev_start:prev_end]
                prev_output_lines = [enhanced.get(prev_start + i, "") for i in range(len(prev_batch_lines))]
                # 只有当所有前一批的输出都存在时才构建previous_io
                if prev_output_lines and all(prev_output_lines):
                    previous_io = (
                        [original for original, _ in prev_batch_lines],  # input_lines
                        prev_output_lines  # output_lines
                    )
            
            # 构建增强消息
            messages = self._build_enhance_all_messages(batch_lines, previous_io)
            
            try:
                result, token_stats = self.streaming_handler.stream_completion(
                    model=self.config.model,
                    messages=messages,
                    temperature=0.0,
                    top_p=1.0,
                    frequency_penalty=0.0,
                    presence_penalty=0.0,
                    repetition_penalty=1.0,
                    no_repeat_ngram_size=0,
                    max_tokens=2048,
                    stop=["（未完待续）", "[END]", "<|im_end|>", "</s>"]
                )
                
                # 检查finish_reason，如果是length则降级处理
                finish_reason = token_stats.get('finish_reason', 'unknown')
                if finish_reason == 'length':
                    self.logger.warning(f"⚠️ 模型输出被截断 (length)，降级到逐行处理: 行 {start+1}-{end}")
                    # 降级到逐行处理
                    for i, (original, translated) in enumerate(batch_lines):
                        try:
                            enhanced[start + i] = self._enhance_single_line(original, translated)
                        except Exception as single_e:
                            self.logger.error(f"单行增强失败 (行{start + i}): {single_e}")
                            enhanced[start + i] = translated  # 保持原译文
                    continue
                
                # 解析多行输出
                cleaned = self._extract_clean_translation(result)
                out_lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
                
                # 将输出映射回原始索引
                for idx, line in enumerate(out_lines):
                    if idx < len(batch_lines):
                        enhanced[start + idx] = line
                
                self.logger.info(f"✅ 批次完成: 行 {start+1}-{end}，已处理{len(out_lines)}行")
                
                # 每批次写盘
                try:
                    self._update_bilingual_file(target_path, original_lines, content_lines, enhanced)
                    self.logger.info(f"文件更新完成: {target_path}, 更新了{len(enhanced)}行")
                    # 安全地获取日志文件路径
                    log_file_path = 'N/A'
                    if hasattr(self.logger, 'handlers') and self.logger.handlers:
                        try:
                            log_file_path = self.logger.handlers[0].baseFilename
                        except (AttributeError, IndexError):
                            pass
                    elif hasattr(self.logger, 'log_file_path'):
                        log_file_path = self.logger.log_file_path
                    self.logger.info(f"   📝 日志文件: {log_file_path}")
                    self.logger.info(f"   📄 输出文件: {target_path}")
                    self.logger.info(f"   🔢 Token使用: {token_stats}")
                except Exception as e:
                    self.logger.error(f"文件更新失败: {e}")
                
            except Exception as e:
                self.logger.error(f"批次增强失败: {e}")
                # 降级到逐行处理
                for i, (original, translated) in enumerate(batch_lines):
                    try:
                        enhanced[start + i] = self._enhance_single_line(original, translated)
                    except Exception as single_e:
                        self.logger.error(f"单行增强失败 (行{start + i}): {single_e}")
                        enhanced[start + i] = translated  # 保持原译文
        
        return enhanced
    
    def _build_enhance_all_messages(self, batch_lines: List[Tuple[str, str]], previous_io: Optional[Tuple[List[str], List[str]]] = None) -> List[Dict[str, str]]:
        """构建增强所有行的消息"""
        # 导入规则检测模块
        from .rule_detector import detect_translation_issues, format_issues_for_enhancement
        
        # 检测规则问题
        rule_issues = []
        for original, translated in batch_lines:
            issues = detect_translation_issues(original, translated)
            formatted_issues = format_issues_for_enhancement(issues)
            rule_issues.append(formatted_issues)
        
        messages = self.enhancement_prompt_builder.build_messages(
            target_lines=[original for original, _ in batch_lines],
            translated_lines=[translated for _, translated in batch_lines],
            previous_io=previous_io,
            rule_issues=rule_issues
        )
        return messages
    
    def _enhance_single_line(self, original: str, translated: str) -> str:
        """单行增强（降级处理）"""
        # 导入规则检测模块
        from .rule_detector import detect_translation_issues, format_issues_for_enhancement
        
        # 检测规则问题
        issues = detect_translation_issues(original, translated)
        formatted_issues = format_issues_for_enhancement(issues)
        
        messages = self.enhancement_prompt_builder.build_messages(
            target_lines=[original],
            translated_lines=[translated],
            rule_issues=[formatted_issues]
        )
        
        result, _ = self.streaming_handler.stream_completion(
            model=self.config.model,
            messages=messages,
            temperature=0.0,
            max_tokens=512
        )
        
        cleaned = self._extract_clean_translation(result)
        lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
        return lines[0] if lines else translated

    def _retranslate_lines_batch(self, content_lines: List[Tuple[str, str]], 
                          needs_retranslation: List[QCResult], original_lines: List[str], target_path: Path) -> Dict[int, str]:
        """批量重译：一次送入N个原/译对，让模型逐行返回改写后的中文"""
        retranslated: Dict[int, str] = {}
        if not needs_retranslation:
            return retranslated
        batch_size = max(1, int(getattr(self.config, 'enhanced_batch_size', 10)))
        # 组批
        for start in range(0, len(needs_retranslation), batch_size):
            batch = needs_retranslation[start:start+batch_size]
            # 构建批量提示：参考bilingual_simple的多轮对话格式
            messages = self._build_enhanced_messages(batch)
            indices = [item.line_index for item in batch]
            try:
                result, token_stats = self.streaming_handler.stream_completion(
                    model=self.config.model,
                    messages=messages,
                    temperature=0.0,
                    top_p=1.0,
                    frequency_penalty=0.0,
                    presence_penalty=0.0,
                    repetition_penalty=1.0,
                    no_repeat_ngram_size=0,
                    max_tokens=2048,
                    stop=["（未完待续）", "[END]", "<|im_end|>", "</s>"]
                )
                # 解析多行输出
                cleaned = self._extract_clean_translation(result)
                # 允许多行，按行拆分
                out_lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
                # 若行数不匹配，则尽量对齐较短部分
                for idx, line_index in enumerate(indices):
                    if idx < len(out_lines) and out_lines[idx]:
                        retranslated[line_index] = out_lines[idx]
                batch_first = indices[0] + 1
                batch_last = indices[0] + len(indices)
                self.logger.info(f"✅ 批次完成: 行 {batch_first}-{batch_last}，已改写{len(out_lines)}行")
                # 每批次写盘并打印路径（对齐 bilingual_simple 的行为）
                try:
                    self._update_bilingual_file(target_path, original_lines, content_lines, retranslated)
                except Exception as e:
                    self.logger.error(f"批次写盘失败: {e}")
                # 提示路径到控制台
                log_path = self.logger.get_log_file_path() if hasattr(self.logger, 'get_log_file_path') else None
                self.logger.info(f"   📝 日志文件: {log_path}", mode=UnifiedLogger.LogMode.BOTH)
                self.logger.info(f"   📄 输出文件: {target_path}", mode=UnifiedLogger.LogMode.BOTH)
                if token_stats:
                    self.logger.info(f"   🔢 Token使用: {token_stats}", mode=UnifiedLogger.LogMode.BOTH)
            except Exception as e:
                self.logger.error(f"批量重译失败: {e}")
                # 降级：逐行重译
                fallback = self._retranslate_lines(content_lines, batch)
                retranslated.update(fallback)
        return retranslated
    
    def _build_enhanced_messages(self, batch: List[QCResult]) -> List[Dict[str, str]]:
        """
        构建增强模式的多轮对话消息（参考bilingual_simple格式）
        
        Args:
            batch: 需要重新翻译的QC结果列表
            
        Returns:
            List[Dict[str, str]]: 多轮对话消息
        """
        # 使用PromptBuilder构建增强消息
        target_lines = [qc_result.original_text for qc_result in batch]
        translated_lines = [qc_result.translated_text for qc_result in batch]
        
        messages = self.enhancement_prompt_builder.build_messages(
            target_lines=target_lines,
            translated_lines=translated_lines
        )
        
        return messages
    def _get_context_lines(self, content_lines: List[Tuple[str, str]], 
                          target_index: int) -> List[Tuple[str, str]]:
        """获取目标行的上下文"""
        context_size = self.config.enhanced_context_lines
        start = max(0, target_index - context_size)
        end = min(len(content_lines), target_index + context_size + 1)
        
        return content_lines[start:end]
    
    def _retranslate_single_line(self, original: str, 
                                context_lines: List[Tuple[str, str]]) -> Optional[str]:
        """
        重新翻译单行
        
        Args:
            original: 原文
            context_lines: 上下文行
            
        Returns:
            Optional[str]: 新译文，失败时返回None
        """
        try:
            # 构建上下文
            context_text = ""
            for orig, trans in context_lines:
                context_text += f"原文: {orig}\n译文: {trans}\n"
            
            # 使用增强模式的系统提示词
            preface_path = Path(__file__).parent.parent.parent / "data" / "preface_enhanced.txt"
            if preface_path.exists():
                with open(preface_path, 'r', encoding='utf-8') as f:
                    system_content = f.read().strip()
            else:
                system_content = "你是专业的中日互译编辑。给定原文与当前译文，请改进质量，仅输出改进后的中文译文，不要任何解释。"
            
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": f"原文: {original}\n现译: {context_lines[0][1] if context_lines else '[翻译未完成]'}\n[翻译完成]"}
            ]
            
            result, token_stats = self.streaming_handler.stream_completion(
                model=self.config.model,
                messages=messages,
                temperature=0.0,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                repetition_penalty=1.0,
                no_repeat_ngram_size=0,
                max_tokens=1024,
                stop=["（未完待续）", "[END]", "<|im_end|>", "</s>"]
            )
            
            # 提取纯净的翻译结果（去除思考过程）
            clean_result = self._extract_clean_translation(result)
            self.logger.info(f"调试: 原始结果={repr(result[:100])}, 清理后结果={repr(clean_result)}")
            return clean_result
            
        except Exception as e:
            self.logger.error(f"重新翻译失败: {e}")
            return None
    
    def _extract_clean_translation(self, result: str) -> str:
        """
        从模型输出中提取纯净的翻译结果
        
        Args:
            result: 模型原始输出
            
        Returns:
            str: 纯净的翻译结果
        """
        # 去除首尾空白
        result = result.strip()
        
        # 如果结果为空，返回原结果
        if not result:
            return result
        
        import re
        
        # 去除<think>标签及其内容（处理没有闭合标签的情况）
        result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
        result = re.sub(r'<think>.*', '', result, flags=re.DOTALL)
        
        # 去除其他常见的思考标记
        result = re.sub(r'<thinking>.*?</thinking>', '', result, flags=re.DOTALL)
        result = re.sub(r'<reasoning>.*?</reasoning>', '', result, flags=re.DOTALL)
        
        # 去除首尾空白
        result = result.strip()
        
        # 如果清理后结果为空，返回空字符串
        if not result:
            return ""
        
        # 按行分割，处理带编号的多行输出
        lines = result.split('\n')
        clean_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 移除行号（如 "1. 译文内容" -> "译文内容"）
            if re.match(r'^\d+\.\s*', line):
                line = re.sub(r'^\d+\.\s*', '', line)
            
            # 处理增强模式的箭头格式（如 "→ 译文内容" -> "译文内容"）
            if line.startswith('→'):
                line = line[1:].strip()
            
            # 跳过[翻译完成]标记
            if line == "[翻译完成]":
                continue
            
            # 跳过其他标记
            if line.startswith('[') and line.endswith(']'):
                continue
            
            # 跳过明显的思考内容（但保留翻译内容）
            # 只有当整行都是思考内容时才跳过，不要跳过包含关键词的翻译
            if (line.startswith('好的') or line.startswith('用户') or 
                line.startswith('让我') or line.startswith('翻译') or
                line.startswith('首先') or line.startswith('需要') or
                line.startswith('确认') or line.startswith('接下来') or
                line.startswith('然后') or line.startswith('另外') or
                line.startswith('最后') or line.startswith('检查') or
                line.startswith('确保') or line.startswith('可能') or
                line.startswith('应该') or line.startswith('不过') or
                line.startswith('但是') or line.startswith('因为') or
                line.startswith('如果') or line.startswith('虽然') or
                line.startswith('根据') or line.startswith('考虑') or
                line.startswith('注意')):
                continue
            
            # 如果这行看起来像翻译结果，添加到结果中
            if len(line) > 0:
                clean_lines.append(line)
        
        # 返回所有有效行，用换行符连接
        if clean_lines:
            return '\n'.join(clean_lines)
        
        # 如果没有找到干净的行，尝试提取引号内的内容
        quoted_matches = re.findall(r'「([^」]+)」', result)
        if quoted_matches:
            return quoted_matches[-1]
        
        # 如果都没有，返回空字符串
        return ""
    
    def _update_bilingual_file(self, file_path: Path, original_lines: List[str],
                              content_lines: List[Tuple[str, str]], 
                              retranslated_lines: Dict[int, str]):
        """
        更新双语文件
        
        Args:
            file_path: 文件路径
            original_lines: 原始文件行
            content_lines: 双语内容
            retranslated_lines: 重新翻译的行
        """
        if not retranslated_lines:
            return
        
        self.logger.info(f"调试信息: content_lines={len(content_lines)}, retranslated_lines={retranslated_lines}")
        
        # 找到YAML结束位置：跳过所有YAML内容直到第二个---或实际内容开始
        yaml_end = 0
        yaml_started = False
        while yaml_end < len(original_lines):
            line = original_lines[yaml_end].strip()
            if line.startswith('---'):
                if not yaml_started:
                    yaml_started = True
                else:
                    # 找到第二个---，YAML结束
                    yaml_end += 1
                    break
            elif yaml_started and not line.startswith('---'):
                # 在YAML中，继续跳过
                pass
            elif not yaml_started and line and not line.startswith('---'):
                # 没有YAML，直接开始解析内容
                break
            yaml_end += 1
        
        # 重新构建文件内容
        new_lines = original_lines[:yaml_end]  # 保留YAML部分
        
        # 创建内容行索引映射
        content_index = 0
        
        # 从YAML结束后开始处理原始内容
        i = yaml_end
        while i < len(original_lines):
            line = original_lines[i].strip()
            
            # 如果是空行，保留
            if not line:
                new_lines.append('\n')
                i += 1
                continue
            
            # 检查是否是原文行（不包含中文）
            if not self._contains_chinese(line) and content_index < len(content_lines):
                original, translated = content_lines[content_index]
                
                # 如果这一行需要重新翻译，使用改进后的译文
                if content_index in retranslated_lines:
                    translated = retranslated_lines[content_index]
                # 否则，如果这一行之前已经被改进过，使用改进后的译文
                elif content_index in self.previous_improvements:
                    translated = self.previous_improvements[content_index]
                
                # 添加原文和译文
                new_lines.append(original + '\n')
                new_lines.append(translated + '\n')
                
                content_index += 1
                i += 2  # 跳过原文和译文行
            else:
                # 保留其他行（如空行、格式行等）
                new_lines.append(original_lines[i])
                i += 1
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        # 更新之前的改进记录
        self.previous_improvements.update(retranslated_lines)
        
        self.logger.info(f"文件更新完成: {file_path}, 更新了{len(retranslated_lines)}行")

    def _resolve_output_path(self, file_path: Path) -> Path:
        """根据配置与 debug 规则，解析增强输出文件路径"""
        if self.config.enhanced_output == 'inplace':
            return file_path
        # copy 模式
        if self.config.debug:
            # 同目录 {original}_enhanced.txt
            return file_path.with_name(f"{file_path.stem}_enhanced{file_path.suffix}")
        # 非 debug: {folder}_enhanced/{original}.txt
        enhanced_dir = file_path.parent.with_name(file_path.parent.name + "_enhanced")
        enhanced_dir.mkdir(parents=True, exist_ok=True)
        return enhanced_dir / file_path.name
