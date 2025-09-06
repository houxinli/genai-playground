#!/usr/bin/env python3
"""
内容验证工具
"""

from typing import Tuple


def validate_content_format(content: str) -> Tuple[bool, str]:
    """
    验证内容格式
    
    Args:
        content: 内容
        
    Returns:
        (是否有效, 错误信息)
    """
    if not content:
        return False, "内容为空"
    
    # 检查编码问题
    try:
        content.encode('utf-8')
    except UnicodeEncodeError:
        return False, "编码错误"
    
    # 检查是否有异常字符
    if '\x00' in content:
        return False, "包含空字符"
    
    return True, ""
