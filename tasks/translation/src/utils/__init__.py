#!/usr/bin/env python3
"""
工具模块
"""

import re
from pathlib import Path
from typing import List, Tuple, Optional


def parse_yaml_front_matter(content: str) -> Tuple[Optional[dict], str]:
    """
    解析YAML front matter
    
    Args:
        content: 文件内容
        
    Returns:
        (YAML数据, 文本内容)
    """
    if not content.startswith('---'):
        return None, content
    
    try:
        import yaml
        parts = content.split('---', 2)
        if len(parts) < 3:
            return None, content
        
        yaml_content = parts[1].strip()
        text_content = parts[2].strip()
        
        yaml_data = yaml.safe_load(yaml_content)
        return yaml_data, text_content
    except Exception:
        return None, content


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


def split_text_into_chunks(text: str, chunk_size: int, overlap: int = 0) -> List[str]:
    """
    将文本分割成块
    
    Args:
        text: 要分割的文本
        chunk_size: 块大小
        overlap: 重叠大小
        
    Returns:
        文本块列表
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        if end >= len(text):
            chunks.append(text[start:])
            break
        
        # 尝试在句号、换行符等处分割
        split_point = end
        for i in range(end, max(start, end - 100), -1):
            if text[i] in ['。', '\n', '！', '？']:
                split_point = i + 1
                break
        
        chunks.append(text[start:split_point])
        start = split_point - overlap
        
        if start >= len(text):
            break
    
    return chunks


def estimate_tokens(text: str) -> int:
    """
    估算文本的token数量
    
    Args:
        text: 文本内容
        
    Returns:
        估算的token数量
    """
    # 简单估算：平均4个字符 = 1个token
    return len(text) // 4


def clean_filename(filename: str) -> str:
    """
    清理文件名，移除非法字符
    
    Args:
        filename: 原始文件名
        
    Returns:
        清理后的文件名
    """
    # 移除或替换非法字符
    illegal_chars = r'[<>:"/\\|?*]'
    cleaned = re.sub(illegal_chars, '_', filename)
    
    # 限制长度
    if len(cleaned) > 200:
        cleaned = cleaned[:200]
    
    return cleaned
