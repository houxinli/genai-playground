#!/usr/bin/env python3
"""
文本清理工具
"""

import re


def clean_output_text(text: str) -> str:
    """
    清理输出文本，去除思考部分、行号等
    
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
    
    # 去除行号：匹配行首的数字+点号或数字+空格模式
    original_lines = text.split('\n')
    cleaned_lines = []
    line_number_removed = False
    
    for line in original_lines:
        # 匹配行首的数字+点号模式 (如 "1. 内容" 或 "123. 内容")
        if re.match(r'^\d+\.\s*', line):
            cleaned_line = re.sub(r'^\d+\.\s*', '', line)
            cleaned_lines.append(cleaned_line)
            line_number_removed = True
        # 匹配行首的数字+空格模式 (如 "1 内容" 或 "123 内容")
        elif re.match(r'^\d+\s+', line):
            cleaned_line = re.sub(r'^\d+\s+', '', line)
            cleaned_lines.append(cleaned_line)
            line_number_removed = True
        else:
            cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # 记录行号清理日志
    if line_number_removed:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("文本清理: 检测到并移除了行号标记")
    
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
