#!/usr/bin/env python3
"""
中文标点基本性检查：
- 粗查中文长串是否缺少常见分隔标点。
"""
import re
from typing import Tuple


_CJK_RUN = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]{80,}")
_CJK_SEPS = re.compile(r"[，、；。！？……]")


def validate_cjk_separators_lines(translated_lines: list[str], sample_tail: int = 1200) -> list[str]:
    """逐行检查中文标点分隔符，返回每行的判定结果。
    
    Args:
        translated_lines: 译文行列表
        sample_tail: 检查尾部字符数
    
    Returns:
        list[str]: 每行的判定结果，'GOOD'或'BAD'
    """
    verdicts = []
    
    for line in translated_lines:
        if not line:
            verdicts.append('GOOD')
            continue
            
        # 检查是否有长串中文字符
        runs = _CJK_RUN.findall(line)
        if not runs:
            verdicts.append('GOOD')
            continue
            
        # 检查是否包含分隔标点
        if not _CJK_SEPS.search(''.join(runs)):
            verdicts.append('BAD')
        else:
            verdicts.append('GOOD')
    
    return verdicts



