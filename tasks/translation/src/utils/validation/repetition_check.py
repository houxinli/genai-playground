#!/usr/bin/env python3
"""
重复字符/片段检测（宽松阈值）。
"""
from typing import Tuple


def has_excessive_repetition_lines(translated_lines: list[str],
                                   char_repeat_threshold: int = 12,
                                   segment_len: int = 15,
                                   segment_count_threshold: int = 5) -> list[str]:
    """逐行检测重复字符/片段，返回每行的判定结果。
    
    Args:
        translated_lines: 译文行列表
        char_repeat_threshold: 单字符重复阈值
        segment_len: 片段长度
        segment_count_threshold: 片段重复次数阈值
    
    Returns:
        list[str]: 每行的判定结果，'GOOD'或'BAD'
    """
    verdicts = []
    
    for line in translated_lines:
        if not line or len(line) < 10:
            verdicts.append('GOOD')
            continue
            
        # 单字符重复
        uniq = set(line)
        has_char_repeat = False
        for ch in uniq:
            if ch * char_repeat_threshold in line:
                has_char_repeat = True
                break
        
        if has_char_repeat:
            verdicts.append('BAD')
            continue
            
        # 片段重复
        n = len(line)
        has_segment_repeat = False
        for i in range(0, max(0, n - segment_len)):
            seg = line[i:i+segment_len]
            if line.count(seg) > segment_count_threshold:
                has_segment_repeat = True
                break
        
        if has_segment_repeat:
            verdicts.append('BAD')
        else:
            verdicts.append('GOOD')
    
    return verdicts



