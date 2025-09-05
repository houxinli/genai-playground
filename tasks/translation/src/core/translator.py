#!/usr/bin/env python3
"""
翻译核心模块
"""

import time
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from openai import OpenAI
from openai import BadRequestError

from .config import TranslationConfig
from .logger import UnifiedLogger
from .quality_checker import QualityChecker
from .streaming_handler import StreamingHandler


class Translator:
    """翻译核心类"""
    
    def __init__(self, config: TranslationConfig, logger: UnifiedLogger, quality_checker: QualityChecker):
        """
        初始化翻译器
        
        Args:
            config: 翻译配置
            logger: 日志器
            quality_checker: 质量检测器
        """
        self.config = config
        self.logger = logger
        self.quality_checker = quality_checker
        # 确保质量检测器也有logger
        if hasattr(self.quality_checker, 'logger'):
            self.quality_checker.logger = logger
        # 确保质量检测器的StreamingHandler也有logger
        if hasattr(self.quality_checker, 'streaming_handler'):
            self.quality_checker.streaming_handler.logger = logger
        self.client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")
        self.streaming_handler = StreamingHandler(self.client, logger)
    
    def translate_text(self, text: str, chunk_index: Optional[int] = None) -> Tuple[str, str, bool, Dict[str, int]]:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            chunk_index: 分块索引（用于日志）
            
        Returns:
            (翻译结果, 完整prompt, 是否成功, token统计)
        """
        chunk_info = f"块 {chunk_index}" if chunk_index is not None else "块"
        
        for attempt in range(1, self.config.retries + 1):
            try:
                self.logger.info(f"调用模型，prompt长度: {len(text)}")
                
                # 计算token统计 - 使用更保守的估算方法
                # 对于包含日语和中文的文本，token密度更高
                estimated_input_tokens = len(text) // 2  # 更保守的估算
                max_context_length = self.config.get_max_context_length()
                
                # 动态计算 max_tokens - 充分利用模型context window
                if self.config.max_tokens > 0:
                    max_tokens = self.config.max_tokens
                else:
                    # 大幅减少安全余量，充分利用context window
                    safety_margin = 1024
                    remain = max_context_length - estimated_input_tokens - safety_margin
                    if remain < 500:
                        remain = 500
                    # 设置合理的上限，避免超出context限制
                    max_tokens = min(remain, 25000)  # 设置25000的上限
                
                self.logger.info(f"动态计算 max_tokens: {max_tokens} (基于输入长度 {len(text)}, 估算输入tokens: {estimated_input_tokens}, 模型上下文长度: {max_context_length})")
                
                # 调用模型
                if self.config.stream:
                    result, prompt, token_meta = self._translate_with_stream(text, max_tokens)
                else:
                    result, prompt, token_meta = self._translate_without_stream(text, max_tokens)
                
                if result and result.strip():
                    # 进行质量检测
                    self.logger.info(f"对{chunk_info}进行质量检测...")
                    is_good, reason = self.quality_checker.check_translation_quality(
                        text, result, self.config.bilingual
                    )
                    
                    if is_good:
                        self.logger.info(f"{chunk_info}质量检测通过: {reason}")
                        return result, prompt, True, token_meta
                    else:
                        self.logger.warning(f"{chunk_info}质量检测失败: {reason}")
                        if attempt < self.config.retries:
                            self.logger.warning(f"质量不佳，重试{chunk_info} (尝试 {attempt + 1}/{self.config.retries})")
                            time.sleep(self.config.retry_wait)
                            continue
                        else:
                            self.logger.warning(f"{chunk_info}质量不佳但已达到最大重试次数，返回结果")
                            return result, prompt, True, token_meta
                else:
                    self.logger.warning(f"{chunk_info}翻译结果为空，重试 (尝试 {attempt + 1}/{self.config.retries})")
                    if attempt < self.config.retries:
                        time.sleep(self.config.retry_wait)
                        continue
                    else:
                        return "", "", False, {"input_tokens": estimated_input_tokens, "output_tokens": 0, "total_tokens": estimated_input_tokens}
                        
            except Exception as e:
                self.logger.error(f"{chunk_info}重试 {attempt}/{self.config.retries}: Exception: {e}")
                if attempt < self.config.retries:
                    time.sleep(self.config.retry_wait)
                    continue
                else:
                    self.logger.error(f"{chunk_info}所有重试都失败了，最后错误: {e}")
                    return "", "", False, {"input_tokens": estimated_input_tokens, "output_tokens": 0, "total_tokens": estimated_input_tokens}
        
        return "", "", False, {"input_tokens": estimated_input_tokens, "output_tokens": 0, "total_tokens": estimated_input_tokens}
    
    def _translate_with_stream(self, text: str, max_tokens: int) -> Tuple[str, str, Dict[str, int]]:
        """流式翻译"""
        prompt = self._build_prompt(text)
        
        try:
            # 使用统一的流式输出处理器
            result, token_stats = self.streaming_handler.stream_completion(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=max_tokens,
                stop=None,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                log_prefix="模型输出"
            )
            
            return self._process_translation_result(result, prompt, max_tokens)
            
        except Exception as e:
            self.logger.error(f"模型调用失败: {e}")
            raise
    
    def _translate_without_stream(self, text: str, max_tokens: int) -> Tuple[str, str, Dict[str, int]]:
        """非流式翻译"""
        prompt = self._build_prompt(text)
        
        try:
            resp = self.client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=max_tokens,
                stop=None,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                stream=False,
            )
            
            result = resp.choices[0].message.content
            
            return self._process_translation_result(result, prompt, max_tokens)
            
        except Exception as e:
            self.logger.error(f"模型调用失败: {e}")
            raise
    
    def _process_translation_result(self, result: str, prompt: str, max_tokens: int) -> Tuple[str, str, Dict[str, int]]:
        """处理翻译结果的通用逻辑"""
        # 清理输出
        cleaned_result = self._clean_output_text(result)
        
        self.logger.info(f"翻译完成，结果长度: {len(result)}")
        self.logger.info(f"清理后长度: {len(cleaned_result)}")
        
        # 估算token使用量
        token_meta = {
            "input_tokens": len(prompt) // 4,
            "output_tokens": len(result) // 4,
            "total_tokens": (len(prompt) + len(result)) // 4,
            "max_tokens": max_tokens
        }
        
        return cleaned_result, prompt, token_meta
    
    def _build_prompt(self, text: str) -> str:
        """构建翻译prompt"""
        # 获取preface
        if self.config.preface_file and self.config.preface_file.exists():
            with open(self.config.preface_file, 'r', encoding='utf-8') as f:
                preface = f.read().strip() + "\n"
        else:
            # 如果preface文件不存在，使用最基本的指令
            preface = "请将以下日语文本翻译为中文：\n\n"
        
        # 添加术语表
        if self.config.terminology_file and self.config.terminology_file.exists():
            with open(self.config.terminology_file, 'r', encoding='utf-8') as f:
                terminology = f.read().strip()
            preface += "以下是术语对照表，请严格参照：\n" + terminology + "\n\n"
        
        # 添加few-shot示例
        if self.config.sample_file and self.config.sample_file.exists():
            with open(self.config.sample_file, 'r', encoding='utf-8') as f:
                sample = f.read().strip()
            preface += "以下是翻译示例：\n" + sample + "\n\n"
        
        prompt = preface + "原文：\n\n" + text + "\n\n翻译结果："
        
        # 记录完整prompt到日志
        self.logger.debug(f"完整prompt:\n{prompt}")
        
        return prompt
    
    def _clean_output_text(self, text: str) -> str:
        """清理输出文本，去除思考部分等"""
        if not text or not text.strip():
            return text
        
        # 检测和截断重复模式
        text = self._detect_and_truncate_repetition(text)
        
        # 去除 <think>...</think> 部分
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # 去除其他思考标记
        text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
        text = re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL)
        
        # 去除多余的空白行
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        
        return text.strip()
    
    def _detect_and_truncate_repetition(self, text: str, max_repeat_chars: int = 10, max_repeat_segments: int = 5) -> str:
        """检测并截断重复模式"""
        if not text or len(text) < 10:
            return text
        
        # 检测单字符重复
        result = []
        i = 0
        
        while i < len(text):
            char = text[i]
            count = 1
            j = i + 1
            
            while j < len(text) and text[j] == char:
                count += 1
                j += 1
            
            if count > max_repeat_chars:
                result.append(char * max_repeat_chars)
                if count > max_repeat_chars * 3:
                    return ''.join(result)
            else:
                result.append(char * count)
            
            i = j
        
        text = ''.join(result)
        
        # 检测短片段重复
        if len(text) > 20:
            tail = text[-min(1000, len(text)):]
            
            for segment_len in range(5, min(101, len(tail) // 2 + 1), 5):
                if segment_len > len(tail) // 2:
                    continue
                    
                segment = tail[-segment_len:]
                if not segment.strip():
                    continue
                
                repeat_count = tail.count(segment)
                
                if repeat_count > max_repeat_segments:
                    repeat_start = len(text) - (repeat_count * segment_len)
                    truncated_text = text[:repeat_start + (max_repeat_segments * segment_len)]
                    return truncated_text
        
        return text
