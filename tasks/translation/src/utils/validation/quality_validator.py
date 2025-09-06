#!/usr/bin/env python3
"""
质量验证工具
"""

import re
from typing import Tuple


def validate_translation_quality(original: str, translated: str) -> Tuple[bool, str]:
    """
    验证翻译质量
    
    Args:
        original: 原文
        translated: 译文
        
    Returns:
        (是否通过, 错误信息)
    """
    if not translated or not translated.strip():
        return False, "译文为空"
    
    # 检查是否有明显的错误标记
    error_patterns = [
        r'（以下省略）',
        r'（省略）',
        r'\[ERROR\]',
        r'\[FAILED\]',
        r'翻译失败',
    ]
    
    for pattern in error_patterns:
        if re.search(pattern, translated):
            return False, f"包含错误标记: {pattern}"
    
    # 检查长度是否合理
    if len(translated) < len(original) * 0.3:
        return False, "译文过短"
    
    if len(translated) > len(original) * 3:
        return False, "译文过长"
    
    return True, ""
