#!/usr/bin/env python3
"""
准确的Token分析工具
使用Qwen3 tokenizer进行精确的token计数和估算
"""

from typing import Optional, Dict, Any
from pathlib import Path
from transformers import AutoTokenizer
import logging

logger = logging.getLogger(__name__)


class TokenAnalyzer:
    """准确的Token分析器"""
    
    def __init__(self, model_name: str = "Qwen/Qwen3-32B"):
        """初始化tokenizer"""
        self.model_name = model_name
        self.tokenizer = None
        self._load_tokenizer()
    
    def _load_tokenizer(self):
        """加载tokenizer"""
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, 
                trust_remote_code=True
            )
            logger.debug(f"✅ 成功加载tokenizer: {self.model_name}")
        except Exception as e:
            logger.warning(f"⚠️ 加载tokenizer失败: {e}, 将使用简单估算")
            self.tokenizer = None
    
    def count_tokens(self, text: str) -> int:
        """
        计算文本的准确token数量
        
        Args:
            text: 要计算的文本
            
        Returns:
            token数量
        """
        if not text:
            return 0
        
        if self.tokenizer:
            try:
                tokens = self.tokenizer.encode(text, add_special_tokens=False)
                return len(tokens)
            except Exception as e:
                logger.warning(f"⚠️ Token计算失败: {e}")
        
        # 回退到简单估算
        return len(text) // 3
    
    def estimate_max_tokens(self, input_text: str, output_ratio: float = 1.2) -> int:
        """
        基于输入文本估算所需的max_tokens
        
        Args:
            input_text: 输入文本
            output_ratio: 输出/输入比例，默认1.2（输出通常比输入稍长）
            
        Returns:
            建议的max_tokens值
        """
        input_tokens = self.count_tokens(input_text)
        estimated_output_tokens = int(input_tokens * output_ratio)
        
        # 添加一些缓冲
        buffer = max(100, int(input_tokens * 0.1))
        max_tokens = input_tokens + estimated_output_tokens + buffer
        
        logger.debug(f"Token估算: 输入{input_tokens}, 预计输出{estimated_output_tokens}, 建议max_tokens={max_tokens}")
        
        return max_tokens
    
    def estimate_batch_tokens(self, lines: list, context_lines: int = 0) -> Dict[str, int]:
        """
        估算批次翻译的token使用情况
        
        Args:
            lines: 要翻译的行列表
            context_lines: 上下文行数
            
        Returns:
            包含各种token估算的字典
        """
        # 构建完整的prompt
        batch_text = '\n'.join(lines)
        
        # 基础prompt模板
        prompt_template = """将下列日语逐行翻译为中文，仅输出对应中文行；不要解释、不要添加标点以外的额外内容。严格按照行数输出，每行一个翻译结果。不要输出行号或序号。

示例：
日语：
1. こんにちは
2. 世界
3. これはテストです

中文：
你好
世界
这是测试

日语：
{batch_text}

中文："""
        
        full_prompt = prompt_template.format(batch_text=batch_text)
        
        input_tokens = self.count_tokens(full_prompt)
        
        # 对于逐行翻译任务，输出tokens至少是输入的3倍
        estimated_output_tokens = max(int(input_tokens * 3.0), int(input_tokens * 1.1))
        
        # 建议的max_tokens（包含缓冲）
        suggested_max_tokens = input_tokens + estimated_output_tokens + 200
        
        return {
            "input_tokens": input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "suggested_max_tokens": suggested_max_tokens,
            "total_estimated": input_tokens + estimated_output_tokens
        }
    
    def is_safe_for_context(self, estimated_tokens: int, context_limit: int = 32000, safety_margin: float = 0.8) -> bool:
        """
        检查估算的token数量是否在安全范围内
        
        Args:
            estimated_tokens: 估算的token数量
            context_limit: 上下文限制
            safety_margin: 安全边际
            
        Returns:
            是否安全
        """
        safe_limit = int(context_limit * safety_margin)
        return estimated_tokens <= safe_limit
    
    def get_safe_batch_size(self, lines: list, context_limit: int = 32000, safety_margin: float = 0.8) -> int:
        """
        计算安全的批次大小
        
        Args:
            lines: 所有行
            context_limit: 上下文限制
            safety_margin: 安全边际
            
        Returns:
            建议的批次大小
        """
        if not lines:
            return 0
        
        # 从单行开始测试
        for batch_size in range(1, len(lines) + 1):
            batch_lines = lines[:batch_size]
            estimation = self.estimate_batch_tokens(batch_lines)
            
            if not self.is_safe_for_context(estimation["suggested_max_tokens"], context_limit, safety_margin):
                return max(1, batch_size - 1)
        
        return len(lines)


# 全局实例，避免重复加载tokenizer
_global_analyzer: Optional[TokenAnalyzer] = None


def get_token_analyzer(model_name: str = "Qwen/Qwen3-32B") -> TokenAnalyzer:
    """获取全局token分析器实例"""
    global _global_analyzer
    if _global_analyzer is None or _global_analyzer.model_name != model_name:
        _global_analyzer = TokenAnalyzer(model_name)
    return _global_analyzer


def count_tokens(text: str, model_name: str = "Qwen/Qwen3-32B") -> int:
    """便捷函数：计算token数量"""
    analyzer = get_token_analyzer(model_name)
    return analyzer.count_tokens(text)


def estimate_max_tokens(input_text: str, model_name: str = "Qwen/Qwen3-32B", output_ratio: float = 1.2) -> int:
    """便捷函数：估算max_tokens"""
    analyzer = get_token_analyzer(model_name)
    return analyzer.estimate_max_tokens(input_text, output_ratio)
