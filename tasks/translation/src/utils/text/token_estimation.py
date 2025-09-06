#!/usr/bin/env python3
"""
Token估算工具
使用准确的tokenizer进行token计算
"""

from typing import List, Union, Optional, Dict
from .token_analyzer import get_token_analyzer
from .token_utils import calculate_safe_max_tokens, estimate_translation_max_tokens, log_model_call_params


def estimate_tokens(text: str, model_name: str = "Qwen/Qwen3-32B") -> int:
    """
    估算文本的token数量（使用准确tokenizer）
    
    Args:
        text: 文本内容
        model_name: 模型名称
        
    Returns:
        估算的token数量
    """
    if not text:
        return 0
    
    analyzer = get_token_analyzer(model_name)
    return analyzer.count_tokens(text)


def estimate_prompt_tokens(messages: Union[List, str], model_name: str = "Qwen/Qwen3-32B") -> int:
    """
    估算prompt的token数量（使用准确tokenizer）
    
    Args:
        messages: 消息列表或文本
        model_name: 模型名称
        
    Returns:
        估算的token数量
    """
    try:
        if isinstance(messages, list):
            text = str(messages)
        else:
            text = messages
        return estimate_tokens(text, model_name)
    except Exception:
        return 0


def estimate_max_tokens_for_translation(input_text: str, model_name: str = "Qwen/Qwen3-32B") -> int:
    """
    为翻译任务估算max_tokens
    
    Args:
        input_text: 输入文本
        model_name: 模型名称
        
    Returns:
        建议的max_tokens值
    """
    return estimate_translation_max_tokens(input_text, model_name)


def calculate_max_tokens_for_messages(
    messages: List[Dict[str, str]], 
    model_name: str = "Qwen/Qwen3-32B",
    context_limit: int = 32000,
    requested_max_tokens: int = 0,
    cap: Optional[int] = None
) -> int:
    """
    为消息列表计算安全的max_tokens
    
    Args:
        messages: 消息列表
        model_name: 模型名称
        context_limit: 上下文限制
        requested_max_tokens: 请求的max_tokens
        cap: 上限值
        
    Returns:
        安全的max_tokens值
    """
    return calculate_safe_max_tokens(
        messages, model_name, context_limit, requested_max_tokens, cap
    )


def log_model_call(
    logger,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float,
    top_p: Optional[float],
    frequency_penalty: float,
    presence_penalty: float,
    call_type: str = "流式"
) -> None:
    """
    记录模型调用参数
    
    Args:
        logger: 日志器
        model: 模型名称
        messages: 消息列表
        max_tokens: max_tokens值
        temperature: 温度
        top_p: top_p值
        frequency_penalty: 频率惩罚
        presence_penalty: 存在惩罚
        call_type: 调用类型
    """
    log_model_call_params(
        logger, model, messages, max_tokens, temperature, top_p, 
        frequency_penalty, presence_penalty, call_type
    )
