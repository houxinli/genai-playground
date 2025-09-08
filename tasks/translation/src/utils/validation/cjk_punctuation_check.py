#!/usr/bin/env python3
"""
中文标点基本性检查：
- 粗查中文长串是否缺少常见分隔标点。
"""
import re
from typing import Tuple


_CJK_RUN = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]{80,}")
_CJK_SEPS = re.compile(r"[，、；。！？……]")


def validate_cjk_separators(text: str, sample_tail: int = 1200) -> Tuple[bool, str]:
    tail = text[-sample_tail:] if text and len(text) > sample_tail else (text or "")
    runs = _CJK_RUN.findall(tail)
    if not runs:
        return True, "标点检查通过"
    if not _CJK_SEPS.search(''.join(runs)):
        return False, "中文句中疑似缺少分隔标点"
    return True, "标点检查通过"



