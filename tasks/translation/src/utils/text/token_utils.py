#!/usr/bin/env python3
"""
Token计算工具
提供准确的token计算和max_tokens估算功能
"""

from typing import List, Optional, Dict, Any
from .token_analyzer import get_token_analyzer


def calculate_safe_max_tokens(
    messages: List[Dict[str, str]], 
    model_name: str = "Qwen/Qwen3-32B",
    context_limit: int = 32000,
    requested_max_tokens: int = 0,
    cap: Optional[int] = None,
    safety_margin: float = 0.95
) -> int:
    """
    计算安全的max_tokens值
    
    Args:
        messages: 消息列表
        model_name: 模型名称
        context_limit: 上下文限制
        requested_max_tokens: 请求的max_tokens
        cap: 上限值
        safety_margin: 安全边际
        
    Returns:
        安全的max_tokens值
    """
    try:
        analyzer = get_token_analyzer(model_name)
        
        # 计算输入tokens
        prompt_text = str(messages)
        input_tokens = analyzer.count_tokens(prompt_text)
        
        # 计算可用的输出tokens
        available_tokens = int((context_limit - input_tokens) * safety_margin) - 128
        
        # 确保最小值为256
        if available_tokens < 256:
            available_tokens = 256
        
        # 应用请求的max_tokens限制
        if requested_max_tokens > 0:
            available_tokens = min(available_tokens, requested_max_tokens)
        
        # 应用cap限制
        if cap is not None and cap > 0:
            available_tokens = min(available_tokens, cap)
        
        return available_tokens
        
    except Exception as e:
        # 回退到简单估算
        prompt_text = str(messages)
        estimated_input_tokens = len(prompt_text) // 4
        available_tokens = int((context_limit - estimated_input_tokens) * safety_margin) - 128
        
        if available_tokens < 256:
            available_tokens = 256
            
        if requested_max_tokens > 0:
            available_tokens = min(available_tokens, requested_max_tokens)
            
        if cap is not None and cap > 0:
            available_tokens = min(available_tokens, cap)
            
        return available_tokens


def estimate_translation_max_tokens(
    input_text: str,
    model_name: str = "Qwen/Qwen3-32B",
    output_ratio: float = 1.2,
    max_cap: int = 6000
) -> int:
    """
    为翻译任务估算max_tokens
    
    Args:
        input_text: 输入文本
        model_name: 模型名称
        output_ratio: 输出/输入比例
        max_cap: 最大上限
        
    Returns:
        建议的max_tokens值
    """
    try:
        analyzer = get_token_analyzer(model_name)
        return min(analyzer.estimate_max_tokens(input_text, output_ratio), max_cap)
    except Exception:
        # 回退到简单估算
        estimated_output = len(input_text) * 0.3  # 简单估算
        return min(int(estimated_output * output_ratio) + 200, max_cap)


def log_model_call_params(
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
    try:
        messages_len = len(str(messages))
        messages_cnt = len(messages)
        
        logger.info(
            f"调用参数({call_type}): model={model}, messages={messages_cnt} (chars={messages_len}), "
            f"temperature={temperature:.3f}, top_p={top_p if top_p is not None else 'None'}, max_tokens={max_tokens}, "
            f"freq_penalty={frequency_penalty:.2f}, presence_penalty={presence_penalty:.2f}"
        )
    except Exception:
        pass
