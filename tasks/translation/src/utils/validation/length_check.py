#!/usr/bin/env python3
"""
长度比例校验：用于粗略筛查译文过短/过长问题。
"""
from typing import Tuple


def validate_length_ratio_lines(original_lines: list[str], translated_lines: list[str], min_ratio: float = 0.3, max_ratio: float = 3.0) -> list[str]:
    """逐行校验译文与原文长度比例，返回每行的判定结果。
    
    Args:
        original_lines: 原文行列表
        translated_lines: 译文行列表
        min_ratio: 最小长度比例
        max_ratio: 最大长度比例
    
    Returns:
        list[str]: 每行的判定结果，'GOOD'或'BAD'
    """
    verdicts = []
    n = min(len(original_lines), len(translated_lines))
    
    for i in range(n):
        orig = original_lines[i]
        tran = translated_lines[i]
        
        if not tran or not tran.strip():
            verdicts.append('BAD')
            continue
            
        o = len(orig or "")
        t = len(tran or "")
        if o <= 0:
            # 无原文时不做该规则判断
            verdicts.append('GOOD')
            continue
            
        ratio = t / max(1, o)
        if ratio < min_ratio or ratio > max_ratio:
            verdicts.append('BAD')
        else:
            verdicts.append('GOOD')
    
    # 补齐长度
    while len(verdicts) < len(original_lines):
        verdicts.append('BAD')
    
    return verdicts



