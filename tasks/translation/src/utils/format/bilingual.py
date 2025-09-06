#!/usr/bin/env python3
"""
双语对照格式化工具
"""

from typing import List


def create_bilingual_output(original_lines: List[str], translated_lines: List[str]) -> str:
    """
    创建双语对照输出
    
    Args:
        original_lines: 原文行列表
        translated_lines: 译文行列表
        
    Returns:
        双语对照文本
    """
    result = []
    
    # 确保两个列表长度相同
    max_lines = max(len(original_lines), len(translated_lines))
    
    for i in range(max_lines):
        original_line = original_lines[i] if i < len(original_lines) else ""
        translated_line = translated_lines[i] if i < len(translated_lines) else ""
        
        if original_line.strip():
            result.append(original_line)
        if translated_line.strip():
            result.append(translated_line)
        if not original_line.strip() and not translated_line.strip():
            result.append("")
    
    return "\n".join(result)
