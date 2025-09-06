#!/usr/bin/env python3
"""
文件名处理工具
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional


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


def generate_output_filename(
    input_path: Path, 
    suffix: str, 
    debug_mode: bool = False,
    timestamp: Optional[str] = None
) -> str:
    """
    生成输出文件名
    
    Args:
        input_path: 输入文件路径
        suffix: 后缀
        debug_mode: 是否debug模式
        timestamp: 时间戳（可选）
        
    Returns:
        输出文件名
    """
    stem = input_path.stem
    
    if debug_mode:
        if timestamp is None:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        return f"{stem}_{timestamp}{suffix}.txt"
    else:
        return f"{stem}{suffix}.txt"
