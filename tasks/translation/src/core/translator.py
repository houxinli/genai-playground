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
from ..utils.text import clean_output_text, detect_and_truncate_repetition, calculate_max_tokens_for_messages, log_model_call
from .streaming_handler import StreamingHandler
from .profile_manager import ProfileManager, GenerationParams


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
        self.profile_manager = ProfileManager(config.profiles_file)
        self.streaming_handler = StreamingHandler(self.client, logger, config, self.profile_manager)
    
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
                            # 在debug模式下，质量检测失败应该被视为失败
                            success = not self.config.debug
                            return result, prompt, success, token_meta
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
        messages = self._build_messages(text)
        
        try:
            # 基于消息计算生成上限
            allowed = self._calculate_max_tokens(messages, requested_max_tokens=max_tokens, cap=None)
            max_tokens = allowed
            # 使用统一的流式输出处理器
            try:
                # bilingual 时提高频率惩罚，降低连写与口癖
                from .streaming_handler import StreamingHandler
                freq_penalty = max(self.config.frequency_penalty, 0.5) if self.config.bilingual else self.config.frequency_penalty
                params = self.profile_manager.get_generation_params(
                    "body",
                    max_tokens=max_tokens,
                    frequency_penalty=freq_penalty
                )
                result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                    messages=messages,
                    params=params,
                )
            except BadRequestError as e:
                # 针对 max_tokens 上限错误降档重试一次
                msg = str(e)
                if "max_tokens" in msg or "max_completion_tokens" in msg:
                    # 降档到更保守上限
                    safe_allowed = self._calculate_max_tokens(messages, requested_max_tokens=max_tokens, cap=int(max_tokens * 0.6))
                    max_tokens = safe_allowed
                    self.logger.warning(f"max_tokens 调整为保守值: {max_tokens} 后重试流式调用")
                    from .streaming_handler import StreamingHandler
                    retry_params = self.profile_manager.get_generation_params(
                        "body",
                max_tokens=max_tokens,
                frequency_penalty=self.config.frequency_penalty,
                        presence_penalty=self.config.presence_penalty
                    )
                    result, token_stats = self.streaming_handler.stream_with_params(
                        model=self.config.model,
                        messages=messages,
                        params=retry_params,
                    )
                else:
                    raise
            
            return self._process_translation_result(result, str(messages), max_tokens)
            
        except Exception as e:
            self.logger.error(f"模型调用失败: {e}")
            raise
    
    def _translate_without_stream(self, text: str, max_tokens: int) -> Tuple[str, str, Dict[str, int]]:
        """非流式翻译"""
        messages = self._build_messages(text)
        
        try:
            # 基于消息计算生成上限
            max_tokens = self._calculate_max_tokens(messages, requested_max_tokens=max_tokens, cap=None)
            # 记录调用参数
            log_model_call(
                self.logger,
                self.config.model,
                messages,
                max_tokens,
                self.config.temperature,
                self.config.top_p,
                self.config.frequency_penalty,
                self.config.presence_penalty,
                "非流式"
            )
            try:
                resp = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=self.config.temperature,
                    max_tokens=max_tokens,
                    stop=None,
                    frequency_penalty=self.config.frequency_penalty,
                    presence_penalty=self.config.presence_penalty,
                    stream=False,
                )
            except BadRequestError as e:
                msg = str(e)
                if "max_tokens" in msg or "max_completion_tokens" in msg:
                    # 重新估算更保守上限
                    safe_allowed = self._calculate_max_tokens(messages, requested_max_tokens=max_tokens, cap=int(max_tokens * 0.6))
                    max_tokens = safe_allowed
                    self.logger.warning(f"max_tokens 调整为保守值: {max_tokens} 后重试非流式调用")
            resp = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=max_tokens,
                stop=None,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                stream=False,
            )
            
            result = resp.choices[0].message.content
            
            return self._process_translation_result(result, str(messages), max_tokens)
            
        except Exception as e:
            self.logger.error(f"模型调用失败: {e}")
            raise
    
    def _process_translation_result(self, result: str, prompt: str, max_tokens: int) -> Tuple[str, str, Dict[str, int]]:
        """处理翻译结果的通用逻辑"""
        # 清理输出
        cleaned_result = clean_output_text(result)
        
        # self.logger.info(f"翻译完成，结果长度: {len(result)}")
        # self.logger.info(f"清理后长度: {len(cleaned_result)}")
        
        # 估算token使用量（streaming_handler已记录详细统计）
        token_meta = {
            "input_tokens": len(prompt) // 4,
            "output_tokens": len(result) // 4,
            "total_tokens": (len(prompt) + len(result)) // 4,
            "max_tokens": max_tokens
        }
        
        return cleaned_result, prompt, token_meta
    
    

    def _build_messages(self, text: str) -> list:
        """构建通用正文消息（对话包装）。"""
        return self._build_messages_generic(
            text=text,
            preface_path=self.config.preface_file,
            sample_path=self.config.sample_file,
            add_samples=True,
            default_preface="请将以下日语文本翻译为中文，严格逐行对照，不新增或删除换行。",
            log_label="Prompt (single user)"
        )

    def _extract_yaml_block_only(self, text: str) -> str:
        """提取首个完整的 YAML block（含 --- 分隔），避免多余内容污染。"""
        try:
            if not text:
                return text
            start = text.find("---")
            if start < 0:
                return text.strip()
            end = text.find("---", start + 3)
            if end < 0:
                # 只有起始分隔线：取到文本末尾
                return text[start:].strip()
            return text[start:end+3].strip()
        except Exception:
            return text.strip()

    def _build_messages_yaml(self, text: str) -> list:
        """构建 YAML 消息（对话包装）。"""
        return self._build_messages_generic(
            text=text,
            preface_path=(self.config.preface_yaml_file or self.config.preface_file),
            sample_path=self.config.sample_yaml_file,
            add_samples=True,
            default_preface="YAML 特例：仅翻译 title/caption/tags/series.title 的 value，并按双行输出；其他行仅保留原文一行（含 ---）。tags 译文行保留 [] 与逗号，元素用 原词 / 中文。缩进/层级/key/冒号空格必须完全一致。",
            log_label="YAML Prompt (single user)"
        )

    def _build_messages_body(self, text: str) -> list:
        """构建正文消息（对话包装）。"""
        return self._build_messages_generic(
            text=text,
            preface_path=(self.config.preface_body_file or self.config.preface_file),
            sample_path=None,
            add_samples=False,
            default_preface="请将以下日语文本翻译为中文，严格逐行对照（原文行后紧跟译文），禁止省略，沿用原文引号样式，中文需使用恰当标点，不合并/不拆分/不调序。",
            log_label="Body Prompt (single user)"
        )

    def _build_messages_generic(self, text: str, preface_path: Optional[Path], sample_path: Optional[Path], add_samples: bool, default_preface: str, log_label: str) -> list:
        parts: list[str] = []
        # preface
        if preface_path and Path(preface_path).exists():
            with open(preface_path, 'r', encoding='utf-8') as f:
                parts.append(f.read().strip())
        else:
            parts.append(default_preface)
        # terminology
        if self.config.terminology_file and self.config.terminology_file.exists():
            with open(self.config.terminology_file, 'r', encoding='utf-8') as f:
                parts.append("术语对照表：\n" + f.read().strip())
        # samples (optional)
        if add_samples and sample_path and Path(sample_path).exists():
            with open(sample_path, 'r', encoding='utf-8') as f:
                parts.append("示例（Few-shot）：\n" + f.read().strip())
        # wrap input
        parts.append(f"User:\n{text}\n\nAssistant:")
        content = "\n\n".join(parts)
        messages = [{"role": "user", "content": content}]
        self.logger.debug(f"{log_label}:\n" + content)
        return messages

    def translate_yaml_text(self, text: str) -> Tuple[str, str, bool, Dict[str, int]]:
        """针对 YAML 段的翻译（不分块）。"""
        messages = self._build_messages_yaml(text)
        try:
            yaml_prof = self.profile_manager.get_profile("yaml")
            # 固定参数：T=0.0, top_p=1.0, freq=0.0, presence=0.0, 无重复惩罚，max_tokens=800，stop=None
            allowed = self._calculate_max_tokens(messages, requested_max_tokens=800, cap=800)
            from .streaming_handler import StreamingHandler
            params = self.profile_manager.get_generation_params(
                "yaml",
                max_tokens=allowed,
                watchdog_timeout_s=int(yaml_prof.get("watchdog_timeout_s", 180))
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            # 先从原始结果中提取首个 YAML 块，避免清洗时误删
            yaml_block = self._extract_yaml_block_only(result or "")
            # 再对提取后的 YAML 块进行温和清洗（去掉 think/围栏等）
            yaml_block_cleaned = clean_output_text(yaml_block)
            prompt = str(messages)
            meta = {
                "input_tokens": len(prompt) // 4,
                "output_tokens": len(result or "") // 4,
                "total_tokens": (len(prompt) + len(result or "")) // 4,
                "max_tokens": allowed,
            }
            return yaml_block_cleaned, prompt, True, meta
        except Exception as e:
            self.logger.error(f"YAML 翻译失败: {e}")
            return "", "", False, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def translate_yaml_kv_batch(self, kv: Dict[str, object]) -> Tuple[Dict[str, object], str, bool, Dict[str, int]]:
        """批量翻译 YAML 目标字段：仅提供四个键的原值，不给整段 YAML。
        输入 kv 包含可选键：'title': str, 'caption': str, 'series.title': str, 'tags': List[str]
        返回同键的译值（tags 返回 List[str]）。
        """
        # 构建最小上下文
        yaml_prof = self.profile_manager.get_profile("yaml")
        parts: list[str] = []
        # 前言
        preface_path = self.config.preface_yaml_file or self.config.preface_file
        if preface_path and Path(preface_path).exists():
            with open(preface_path, 'r', encoding='utf-8') as f:
                parts.append(f.read().strip())
        # 术语
        if self.config.terminology_file and self.config.terminology_file.exists():
            with open(self.config.terminology_file, 'r', encoding='utf-8') as f:
                parts.append("术语对照表：\n" + f.read().strip())
        # 构造用户段
        def render_tags(items: list[str]) -> str:
            return "[" + ", ".join([x for x in items]) + "]"
        lines: list[str] = []
        if isinstance(kv.get('title'), str) and kv['title'].strip():
            lines.append(f"title: {kv['title']}")
        if isinstance(kv.get('caption'), str) and kv['caption'].strip():
            lines.append(f"caption: {kv['caption']}")
        if isinstance(kv.get('series.title'), str) and kv['series.title'].strip():
            lines.append(f"series.title: {kv['series.title']}")
        if isinstance(kv.get('tags'), list):
            try:
                lines.append("tags: " + render_tags([str(x) for x in kv['tags']]))
            except Exception:
                pass
        parts.append("User:\n" + "\n".join(lines) + "\n\nAssistant:")
        content = "\n\n".join(parts)
        messages = [{"role": "user", "content": content}]
        # 调用
        try:
            # 固定参数：T=0.0, top_p=1.0, freq=0.0, presence=0.0, 无重复惩罚，max_tokens=800，stop=None
            allowed = self._calculate_max_tokens(messages, requested_max_tokens=800, cap=800)
            from .streaming_handler import StreamingHandler
            params = self.profile_manager.get_generation_params(
                "yaml",
                max_tokens=allowed,
                watchdog_timeout_s=int(yaml_prof.get("watchdog_timeout_s", 180))
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            cleaned = clean_output_text(result or "")
            # 解析：按行找 key: value / tags: [..]
            out: Dict[str, object] = {}
            for raw in cleaned.splitlines():
                line = raw.strip()
                if not line or ':' not in line:
                    continue
                k, v = line.split(':', 1)
                k = k.strip()
                v = v.strip()
                if k == 'tags' and v.startswith('[') and v.endswith(']'):
                    items = [x.strip().strip('"').strip("'") for x in v[1:-1].split(',') if x.strip()]
                    out['tags'] = items
                elif k in ('title', 'caption', 'series.title'):
                    out[k] = v.strip().strip('"').strip("'")
            prompt = str(messages)
            meta = {
                "input_tokens": len(prompt) // 4,
                "output_tokens": len(result or "") // 4,
                "total_tokens": (len(prompt) + len(result or "")) // 4,
                "max_tokens": allowed,
            }
            return out, prompt, True, meta
        except Exception as e:
            self.logger.error(f"YAML 批量翻译失败: {e}")
            return {}, "", False, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def translate_body_text(self, text: str, chunk_index: Optional[int] = None) -> Tuple[str, str, bool, Dict[str, int]]:
        """正文翻译（使用 Body 专用提示；流式）。"""
        messages = self._build_messages_body(text)
        try:
            body_prof = self.profile_manager.get_profile("body")
            # 生成上限
            cap_tokens = int(body_prof.get("cap_tokens", 2000))
            allowed = self._calculate_max_tokens(messages, requested_max_tokens=cap_tokens, cap=cap_tokens)
            # 采样参数（从 profile 应用）
            temperature = float(body_prof.get("temperature", self.config.temperature))
            top_p = float(body_prof.get("top_p", self.config.top_p))
            freq_penalty = float(body_prof.get("frequency_penalty_min", self.config.frequency_penalty))
            presence_penalty = float(body_prof.get("presence_penalty", self.config.presence_penalty))
            repetition_penalty = float(body_prof.get("repetition_penalty", self.config.repetition_penalty))
            no_repeat_ngram_size = int(body_prof.get("no_repeat_ngram_size", self.config.no_repeat_ngram_size))
            stop_list = body_prof.get("stop", None)
            stop_list = None if (stop_list is None or stop_list == "" or str(stop_list).lower() == "null") else stop_list
            from .streaming_handler import StreamingHandler
            params = self.profile_manager.get_generation_params(
                "body",
                max_tokens=allowed,
                temperature=temperature,
                top_p=top_p,
                stop=stop_list,
                frequency_penalty=freq_penalty,
                presence_penalty=presence_penalty,
                repetition_penalty=repetition_penalty,
                no_repeat_ngram_size=no_repeat_ngram_size
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            cleaned, prompt, meta = self._process_translation_result(result, str(messages), allowed)
            return cleaned, prompt, True, meta
        except Exception as e:
            self.logger.error(f"正文翻译失败: {e}")
            return "", "", False, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    
    # ===== 工具方法 =====
    def _calculate_max_tokens(self, messages: list, requested_max_tokens: int = 0, cap: Optional[int] = None) -> int:
        """计算安全的max_tokens值"""
        return calculate_max_tokens_for_messages(
            messages, 
            self.config.model,
            self.config.get_max_context_length(),
            requested_max_tokens,
            cap
        )
    
    def translate_lines_simple(self, target_lines: List[str], previous_io: Tuple[List[str], List[str]] = None) -> Tuple[List[str], str, bool, Dict[str, int], Tuple[List[str], List[str]]]:
        """
        简化的行级翻译方法
        输入：目标行列表 + 前一次的输入输出
        输出：中文行列表 + prompt + 成功标志 + token统计 + 本次的previous_io
        """
        try:
            # 预处理：记录空白行位置，移除空白行
            non_empty_lines = []
            empty_line_positions = []
            
            for i, line in enumerate(target_lines):
                if line.strip():  # 非空白行
                    # 保存原始行（包含缩进）和去除缩进的行
                    non_empty_lines.append((line, line.strip()))
                else:  # 空白行
                    empty_line_positions.append(i)
            
            if self.logger:
                self.logger.debug(f"预处理结果：总行数{len(target_lines)}，非空白行{len(non_empty_lines)}，空白行位置{empty_line_positions}")
            
            # 构建最小化的prompt（只使用非空白行，去除缩进）
            stripped_lines = [line_stripped for _, line_stripped in non_empty_lines]
            messages = self._build_simple_messages(stripped_lines, previous_io)
            
            # 使用ProfileManager获取bilingual_simple参数
            max_tokens = self._estimate_simple_max_tokens(stripped_lines)
            # 为小批/逐行提供生成下限，避免被思考阶段占满
            if max_tokens is None or max_tokens < 1024:
                max_tokens = 1024
            params = self.profile_manager.get_generation_params(
                "bilingual_simple",
                max_tokens=max_tokens
            )
            
            # 调用模型
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            
            # 记录完整的原始翻译结果（debug级别）
            # if self.logger:
            #     self.logger.debug(f"原始翻译结果（{len(result)}字符）:\n{result}")
            
            # 清理思考内容
            from ..utils.text import clean_output_text
            cleaned_result = clean_output_text(result)
            # 若末尾存在完成标记行，则移除
            cleaned_result = re.sub(r"(?:\n|\r|\r\n)*\[翻译完成\]\s*$", "", cleaned_result.strip())
            
            # 记录清理后的结果（debug级别）
            # if self.logger:
            #     self.logger.debug(f"清理后翻译结果（{len(cleaned_result)}字符）：\n{cleaned_result}")
            
            # 解析结果：按行分割，过滤空行，复制原文缩进
            chinese_lines = []
            for i, line in enumerate(cleaned_result.split('\n')):
                line = line.strip()
                if line:
                    # 复制对应原文的缩进
                    if i < len(non_empty_lines):
                        original_line, _ = non_empty_lines[i]
                        # 计算原文的行首缩进（包括全角空格等）
                        leading_indent = original_line[:len(original_line) - len(original_line.lstrip())]
                        # 为翻译结果添加相同的缩进
                        indented_line = leading_indent + line
                        chinese_lines.append(indented_line)
                    else:
                        chinese_lines.append(line)
            
            # 记录解析后的行数（debug级别）
            # if self.logger:
            #     self.logger.debug(f"解析后中文行数: {len(chinese_lines)}")
            #     for i, line in enumerate(chinese_lines, 1):
            #         self.logger.debug(f"  第{i}行: {line}")
            
            # 检查行数是否匹配（只检查非空白行）
            if len(chinese_lines) != len(non_empty_lines):
                self.logger.warning(f"翻译行数不匹配：期望{len(non_empty_lines)}行（非空白），实际{len(chinese_lines)}行")
                return [], str(messages), False, token_stats, None
            
            # 后处理：在正确位置插入空白行
            final_chinese_lines = []
            chinese_index = 0
            
            for i in range(len(target_lines)):
                if i in empty_line_positions:
                    # 插入空白行
                    final_chinese_lines.append("")
                else:
                    # 插入翻译行
                    if chinese_index < len(chinese_lines):
                        final_chinese_lines.append(chinese_lines[chinese_index])
                        chinese_index += 1
                    else:
                        self.logger.error(f"翻译行数不足：期望{len(non_empty_lines)}行，实际{len(chinese_lines)}行")
                        return [], str(messages), False, token_stats, None
            
            
            # 进行质量检测（规则 + LLM），不通过则让上层走降级/重试
            try:
                original_text_for_qc = "\n".join(stripped_lines)
                translated_text_for_qc = cleaned_result
                self.logger.info("对本批次进行QC LLM检测（整块+二分降级）…")
                qc_ok, qc_reason = self.quality_checker.check_translation_quality_block_with_bisect(
                    original_text_for_qc,
                    translated_text_for_qc,
                    bilingual=True,
                )
                if not qc_ok:
                    self.logger.warning(f"QC判定不通过：{qc_reason}")
                    return [], str(messages), False, token_stats, None
                else:
                    self.logger.info(f"QC通过：{qc_reason}")
            except Exception as _e:
                self.logger.warning(f"QC 调用异常，视为失败：{_e}")
                return [], str(messages), False, token_stats, None

            # 记录对照版的target_lines+final_chinese_lines
            if self.logger:
                self.logger.debug(f"对照版翻译结果：")
                for i, (orig, trans) in enumerate(zip(target_lines, final_chinese_lines)):
                    if orig.strip():  # 只记录非空白行
                        self.logger.debug(f"  第{i+1}行: {orig} -> {trans}")
                    else:
                        self.logger.debug(f"  第{i+1}行: [空白行] -> {trans}")
            
            # 构建本次的 current_io（用于下一批次的上下文）
            # 注意：input 使用 stripped_lines（字符串），output 使用 cleaned_result
            current_io = (
                stripped_lines,  # 输入行（字符串列表）
                cleaned_result.split('\n')  # 输出行（清理后的结果按行分割）
            )
            
            return final_chinese_lines, str(messages), True, token_stats, current_io
            
        except Exception as e:
            self.logger.error(f"简化翻译失败: {e}")
            return [], "", False, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, None
    
    def _build_simple_messages(self, target_lines: List[str], previous_io: Tuple[List[str], List[str]] = None) -> List[Dict[str, str]]:
        """
        构建简化的翻译消息（使用多轮对话格式）
        
        Args:
            target_lines: 要翻译的行列表
            previous_io: 前一次的输入输出 (input_lines, output_lines)
        """
        messages = []
        
        # 系统消息：前言（极简）
        preface_path = Path(__file__).parent.parent.parent / "data" / "preface_simple.txt"
        if preface_path.exists():
            with open(preface_path, 'r', encoding='utf-8') as f:
                system_content = f.read().strip()
        else:
            system_content = "将下列日语逐行翻译为中文，仅输出对应中文行；不要解释、不要添加标点以外的额外内容。严格按照行数输出，每行一个翻译结果。不要输出行号或序号。"
        
        # 术语表（可选）
        if self.config.terminology_file and self.config.terminology_file.exists():
            with open(self.config.terminology_file, 'r', encoding='utf-8') as f:
                terminology = f.read().strip()
                system_content += f"\n\n术语对照表：\n{terminology}"
        
        messages.append({"role": "system", "content": system_content})
        
        # 添加few-shot示例（多轮对话格式，按角色分别累计行号）
        sample_path = Path(__file__).parent.parent.parent / "data" / "samples" / "sample_simple.txt"
        if sample_path.exists():
            with open(sample_path, 'r', encoding='utf-8') as f:
                sample_content = f.read().strip()
            
            # 解析sample_simple.txt中的多轮对话，维护 user_no 与 assistant_no 两个计数器
            lines = sample_content.split('\n')
            current_role = None
            current_content: list[str] = []
            user_no = 1
            assistant_no = 1
            last_user_block_start = 1

            def flush_current():
                nonlocal user_no, assistant_no, last_user_block_start, current_role, current_content
                if current_role and current_content:
                    numbered: list[str] = []
                    if current_role.lower() == 'user':
                        start_no = user_no
                        last_user_block_start = start_no
                        for ln in current_content:
                            numbered.append(f"{start_no}. {ln}")
                            start_no += 1
                        user_no = start_no
                    else:
                        # assistant 与上一用户块对齐编号
                        start_no = last_user_block_start
                        for ln in current_content:
                            numbered.append(f"{start_no}. {ln}")
                            start_no += 1
                        assistant_no = start_no
                    content_block = '\n'.join(numbered).strip()
                    if current_role.lower() == 'assistant':
                        content_block = content_block + "\n[翻译完成]"
                    messages.append({"role": current_role.lower(), "content": content_block})
                current_content = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('User:'):
                    flush_current()
                    current_role = "user"
                    continue
                if line.startswith('Assistant:'):
                    flush_current()
                    current_role = "assistant"
                    continue
                # 普通内容行
                if current_role is None:
                    current_role = "user"
                current_content.append(line)

            flush_current()
        
        # 添加上一次的输入输出作为上下文（如果有的话）
        # 行号策略：分别维护 user_no / assistant_no，从few-shot延续
        # 若无few-shot，则从1开始
        # 下面追加 previous_io 与当前 target_lines
        # 初始化计数器（若上面分支未定义，则定义为1）
        try:
            user_no  # type: ignore
        except NameError:
            user_no = 1  # type: ignore
            last_user_block_start = 1  # type: ignore
        try:
            assistant_no  # type: ignore
        except NameError:
            assistant_no = 1  # type: ignore

        prev_input_lines_norm: List[str] = []
        if previous_io and previous_io[0] and previous_io[1]:
            prev_input_lines, prev_output_lines = previous_io
            # 将 previous_io 统一为字符串列表
            if prev_input_lines and isinstance(prev_input_lines[0], tuple):
                prev_input_lines_norm = [
                    p[1] if isinstance(p, tuple) and len(p) > 1 else (p[0] if isinstance(p, tuple) else str(p))
                    for p in prev_input_lines
                ]
            else:
                prev_input_lines_norm = [str(x) for x in prev_input_lines]
            prev_output_lines_norm = [str(x) for x in prev_output_lines]

            # 依据累计编号，顺序追加 previous_io 用户与助手
            user_buf: list[str] = []
            start_no = user_no
            last_user_block_start = start_no
            for ln in prev_input_lines_norm:
                user_buf.append(f"{start_no}. {ln}")
                start_no += 1
            messages.append({"role": "user", "content": "\n".join(user_buf)})
            user_no = start_no

            assist_buf: list[str] = []
            start_no_assist = last_user_block_start
            for ln in prev_output_lines_norm:
                assist_buf.append(f"{start_no_assist}. {ln}")
                start_no_assist += 1
            messages.append({"role": "assistant", "content": "\n".join(assist_buf) + "\n[翻译完成]"})
            assistant_no = start_no_assist
        
        # 构建当前翻译任务
        user_content = []
        
        # 目标行（要翻译，带累计行号）——起点为（few-shot + previous_io）累计之后
        # 当前要翻译的用户行：从 user_no 继续编号
        curr_no = user_no
        for line in target_lines:
            user_content.append(f"{curr_no}. {line}")
            curr_no += 1
        user_no = curr_no
        
        messages.append({
            "role": "user", 
            "content": "\n".join(user_content)
        })
        
        return messages
    
    def _estimate_simple_max_tokens(self, target_lines: List[str]) -> int:
        """估算简化翻译的max_tokens（使用准确tokenizer）"""
        from ..utils.text.token_analyzer import get_token_analyzer
        
        try:
            analyzer = get_token_analyzer(self.config.model)
            estimation = analyzer.estimate_batch_tokens(target_lines)
            
            # 使用建议的max_tokens，但不超过6000
            suggested_max = estimation["suggested_max_tokens"]
            return min(suggested_max, 6000)
            
        except Exception as e:
            self.logger.warning(f"Token估算失败，使用回退方法: {e}")
            # 回退到简单估算
            estimated_output = len(target_lines) * 150
            return min(estimated_output + 1000, 6000)
