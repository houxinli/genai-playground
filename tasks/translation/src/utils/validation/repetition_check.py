#!/usr/bin/env python3
"""
重复字符/片段检测（宽松阈值）。
"""
from typing import Tuple


def has_excessive_repetition(text: str,
                             char_repeat_threshold: int = 12,
                             segment_len: int = 15,
                             segment_count_threshold: int = 5) -> bool:
    if not text or len(text) < 10:
        return False
    # 单字符重复
    uniq = set(text)
    for ch in uniq:
        if ch * char_repeat_threshold in text:
            return True
    # 片段重复
    n = len(text)
    for i in range(0, max(0, n - segment_len)):
        seg = text[i:i+segment_len]
        if text.count(seg) > segment_count_threshold:
            return True
    return False



