#!/usr/bin/env python3
"""
文本分块工具
"""

from typing import List


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
