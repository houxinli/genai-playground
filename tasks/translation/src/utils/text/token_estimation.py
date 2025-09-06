#!/usr/bin/env python3
"""
Token估算工具
"""

from typing import List, Union


def estimate_tokens(text: str) -> int:
    """
    估算文本的token数量
    
    Args:
        text: 文本内容
        
    Returns:
        估算的token数量
    """
    if not text:
        return 0
    
    # 简单估算：平均4个字符 = 1个token
    return len(text) // 4


def estimate_prompt_tokens(messages: Union[List, str]) -> int:
    """
    估算prompt的token数量
    
    Args:
        messages: 消息列表或文本
        
    Returns:
        估算的token数量
    """
    try:
        if isinstance(messages, list):
            text = str(messages)
        else:
            text = messages
        return len(text) // 4
    except Exception:
        return 0
