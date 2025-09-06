#!/usr/bin/env python3
"""
文本清理工具
"""

import re


def clean_output_text(text: str) -> str:
    """
    清理输出文本，去除思考部分等
    
    Args:
        text: 原始文本
        
    Returns:
        清理后的文本
    """
    if not text or not text.strip():
        return text
    
    # 检测和截断重复模式
    text = detect_and_truncate_repetition(text)
    
    # 去除 <think>...</think> 部分
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    # 去除其他可能的思考标记
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
    text = re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL)
    
    # 去除多余的空白行
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()


def detect_and_truncate_repetition(text: str, max_repeat: int = 20) -> str:
    """
    检测并截断重复的文本模式
    
    Args:
        text: 要检查的文本
        max_repeat: 最大重复次数
        
    Returns:
        处理后的文本
    """
    if not text:
        return text
    
    lines = text.split('\n')
    if len(lines) < 3:
        return text
    
    # 检查是否有重复的短行
    for i in range(len(lines) - max_repeat):
        if len(lines[i].strip()) <= 1:
            repeat_count = 1
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == lines[i].strip():
                    repeat_count += 1
                else:
                    break
            
            if repeat_count > max_repeat:
                # 截断重复部分
                return '\n'.join(lines[:i + 1])
    
    return text
