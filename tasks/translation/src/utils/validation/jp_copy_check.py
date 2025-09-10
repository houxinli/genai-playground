#!/usr/bin/env python3
"""
检测“中文译文是否直接复制了日语原文”的规则方法。
建议仅做轻量级启发式：
- 判定同位置原文与译文完全相同，且两侧都包含日语假名（避免把中文汉字误判为日文汉字）。
"""

import re
from typing import Tuple


_KANA_PATTERN = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9D]")


def has_chinese_copying_japanese_lines(original_lines: list[str], translated_lines: list[str], bilingual: bool = True) -> list[str]:
    """逐行检测中文译文是否直接复制了日语原文，返回每行的判定结果。
    
    Args:
        original_lines: 原文行列表
        translated_lines: 译文行列表
        bilingual: 是否为对照模式（未使用，仅保留兼容参数）
    
    Returns:
        list[str]: 每行的判定结果，'GOOD'或'BAD'
    """
    verdicts = []
    n = min(len(original_lines), len(translated_lines))
    
    for i in range(n):
        orig = original_lines[i]
        tran = translated_lines[i]
        
        if not orig or not tran:
            verdicts.append('GOOD')
            continue
            
        # 检查是否完全相同且都包含假名
        if orig == tran and _KANA_PATTERN.search(orig) and _KANA_PATTERN.search(tran):
            verdicts.append('BAD')
        else:
            verdicts.append('GOOD')
    
    # 补齐长度
    while len(verdicts) < len(original_lines):
        verdicts.append('BAD')
    
    return verdicts



