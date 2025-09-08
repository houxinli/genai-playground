#!/usr/bin/env python3
"""
检测“中文译文是否直接复制了日语原文”的规则方法。
建议仅做轻量级启发式：
- 判定同位置原文与译文完全相同，且两侧都包含日语假名（避免把中文汉字误判为日文汉字）。
"""

import re
from typing import Tuple


_KANA_PATTERN = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9D]")


def has_chinese_copying_japanese(original_text: str, translated_text: str, bilingual: bool = True) -> bool:
    """若发现任意同位置行：原文==译文 且 两侧均含假名，则认为发生了复制。

    Args:
        original_text: 原文（可能多行）
        translated_text: 译文（可能多行）
        bilingual: 是否为对照模式（未使用，仅保留兼容参数）

    Returns:
        True 表示存在复制现象；False 表示未命中该启发式。
    """
    if not original_text or not translated_text:
        return False

    original_lines = [ln.strip() for ln in original_text.split("\n") if ln is not None]
    translated_lines = [ln.strip() for ln in translated_text.split("\n") if ln is not None]

    if len(original_lines) != len(translated_lines):
        # 行数不等时，不做该规则判定（交由其他规则/LLM处理）
        return False

    for orig, tran in zip(original_lines, translated_lines):
        if not orig or not tran:
            continue
        # 两侧都含假名，且文本完全一致 → 明确复制
        if _KANA_PATTERN.search(orig) and _KANA_PATTERN.search(tran) and (orig == tran):
            return True

    return False



