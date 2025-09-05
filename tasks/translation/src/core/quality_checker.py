#!/usr/bin/env python3
"""
翻译质量检测模块
"""

import re
from typing import Tuple, Optional
from openai import OpenAI
from openai import BadRequestError

from .config import TranslationConfig
from .streaming_handler import StreamingHandler


class QualityChecker:
    """翻译质量检测器"""
    
    def __init__(self, config: TranslationConfig, logger=None):
        """
        初始化质量检测器
        
        Args:
            config: 翻译配置
            logger: 日志器
        """
        self.config = config
        self.logger = logger
        self.client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")
        self.streaming_handler = StreamingHandler(self.client, logger)
    
    def check_translation_quality_basic(self, original_text: str, translated_text: str, bilingual: bool = False) -> Tuple[bool, str]:
        """
        基础质量检测（规则-based）
        
        Args:
            original_text: 原文
            translated_text: 译文
            bilingual: 是否为双语模式
            
        Returns:
            (是否通过, 失败原因)
        """
        if not translated_text or not translated_text.strip():
            return False, "翻译结果为空"
        
        # 检查长度比例
        if len(translated_text) < len(original_text) * 0.3:
            return False, "翻译结果过短"
        
        if len(translated_text) > len(original_text) * 3:
            return False, "翻译结果过长"
        
        # 检查错误模式
        error_patterns = [
            "（以下省略）",
            "（省略）",
            "翻译失败",
            "无法翻译",
            "ERROR",
            "error"
        ]
        
        for pattern in error_patterns:
            if pattern in translated_text:
                return False, f"包含错误模式: {pattern}"
        
        # 检查日语字符比例（双语模式更宽松）
        japanese_chars = len(re.findall(r'[ひらがなカタカナ一-龯]', translated_text))
        total_chars = len(translated_text)
        
        if bilingual:
            # 双语模式：允许更多日语字符（可能是原文）
            if japanese_chars / total_chars > 0.8:
                return False, "日语字符过多（双语模式）"
        else:
            # 单语模式：日语字符应该很少
            if japanese_chars / total_chars > 0.3:
                return False, "日语字符过多（单语模式）"
        
        # 检查重复字符
        if self._has_excessive_repetition(translated_text):
            return False, "包含过多重复字符"
        
        return True, "基础检测通过"
    
    def check_translation_quality_with_llm(self, original_text: str, translated_text: str, bilingual: bool = False) -> Tuple[bool, str]:
        """
        使用大模型进行质量检测
        
        Args:
            original_text: 原文
            translated_text: 译文
            bilingual: 是否为双语模式
            
        Returns:
            (是否通过, 失败原因)
        """
        if self.config.no_llm_check:
            return True, "跳过LLM检测"
        
        try:
            # 提取尾部片段（bilingual 模式下译文段取更长片段；强调关注中后段到结尾）
            if bilingual:
                orig_tail_len = 400
                tran_tail_len = 800
            else:
                orig_tail_len = 500
                tran_tail_len = 500

            original_tail = original_text[-orig_tail_len:] if len(original_text) > orig_tail_len else original_text
            translated_tail = translated_text[-tran_tail_len:] if len(translated_text) > tran_tail_len else translated_text

            prompt = self._build_quality_prompt(original_tail, translated_tail, bilingual)

            # 使用流式输出进行质量检测
            result = self._quality_check_with_stream(prompt)

            cleaned = self._clean_quality_output(result)
            verdict = self._extract_verdict(cleaned)

            mode_text = "bilingual对照模式" if bilingual else "单语模式"
            if verdict == "GOOD":
                return True, f"大模型评估：{mode_text}最后部分翻译质量良好"
            elif verdict == "BAD":
                return False, f"大模型评估：{mode_text}最后部分翻译质量不佳"
            else:
                # 回退：无法解析明确结论时，保守为不佳并附上简短截断说明
                short = (cleaned[:120] + '...') if len(cleaned) > 120 else cleaned
                return False, f"大模型评估：{mode_text}结论不明（{short}）"
                
        except Exception as e:
            return False, f"LLM质量检测失败: {str(e)}"
    
    def _quality_check_with_stream(self, prompt: str) -> str:
        """使用流式输出进行质量检测"""
        try:
            # 使用统一的流式输出处理器
            max_tokens = getattr(self.config, 'quality_max_tokens', 0)
            result, _ = self.streaming_handler.stream_completion(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens if max_tokens > 0 else 0,
                stop=None,
                log_prefix="质量检测输出"
            )
            
            return result.strip()
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"质量检测流式调用失败: {e}")
            raise

    def _build_quality_prompt(self, original_tail: str, translated_tail: str, bilingual: bool) -> str:
        """构建质量检测提示词：允许思考，但最终只输出 GOOD 或 BAD 一词作为最后输出。"""
        mode_text = "bilingual对照模式（原文-译文交替）" if bilingual else "单语模式"

        fewshot = (
            "示例1\n"
            "【判断重点】关注片段的中后段至结尾是否完整、对应、格式正确。\n"
            "【输出】GOOD\n\n"
            "示例2\n"
            "【判断重点】结尾中文与原文不对齐且有截断。\n"
            "【输出】BAD\n\n"
        )

        instruction = (
            f"你是严格的翻译质检员。输入是{mode_text}的尾段片段。\n"
            "- 片段开头可能是机械截断，判断重点放在片段的中后段直到结尾。\n"
            "- 先在心里完整思考原因与证据，然后只在最后一行输出结论：GOOD 或 BAD。\n"
            "- 最终输出必须是单独的一个词：GOOD 或 BAD（大写）。不要附加任何解释。\n"
        )

        if bilingual:
            body = (
                f"原文尾段（可能截断开头）：\n{original_tail}\n\n"
                f"对照译文尾段（可能截断开头）：\n{translated_tail}\n\n"
                "检查要点：\n"
                "1) 中后段是否行行对齐，是否存在缺行/乱序/错配\n"
                "2) 含义是否对应、是否出现明显误译\n"
                "3) 结尾是否完整，无异常截断\n"
            )
        else:
            body = (
                f"原文尾段（可能截断开头）：\n{original_tail}\n\n"
                f"译文尾段（可能截断开头）：\n{translated_tail}\n\n"
                "检查要点：\n"
                "1) 中后段是否完整对应\n"
                "2) 关键含义是否准确\n"
                "3) 结尾是否无截断\n"
            )

        return f"{instruction}\n{fewshot}{body}\n请在心中完成推理，最后一行只输出：GOOD 或 BAD。"

    def _clean_quality_output(self, text: str) -> str:
        """移除大模型的思维/标记等噪声，得到判定可读文本。"""
        import re
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        return cleaned.strip()

    def _extract_verdict(self, text: str) -> str:
        """从输出中提取最终结论（取最后一个 GOOD/BAD）。"""
        import re
        matches = re.findall(r"\b(GOOD|BAD)\b", text.upper())
        return matches[-1] if matches else ""
    
    def check_translation_quality(self, original_text: str, translated_text: str, bilingual: bool = False) -> Tuple[bool, str]:
        """
        综合质量检测
        
        Args:
            original_text: 原文
            translated_text: 译文
            bilingual: 是否为双语模式
            
        Returns:
            (是否通过, 失败原因)
        """
        # 先进行基础检测
        is_good, reason = self.check_translation_quality_basic(original_text, translated_text, bilingual)
        if not is_good:
            return False, reason
        
        # 如果基础检测通过，进行LLM检测
        return self.check_translation_quality_with_llm(original_text, translated_text, bilingual)
    
    def _has_excessive_repetition(self, text: str) -> bool:
        """检查是否有过多重复字符（更宽松的检测）"""
        if len(text) < 10:
            return False
        
        # 检查单字符重复（更宽松：连续12个相同字符）
        for char in set(text):
            if char * 12 in text:  # 从8个提高到12个
                return True
        
        # 检查短片段重复（更宽松：同一片段出现超过5次）
        for i in range(len(text) - 30):
            segment = text[i:i+15]  # 从10个字符提高到15个字符
            if text.count(segment) > 5:  # 从3次提高到5次
                return True
        
        return False
