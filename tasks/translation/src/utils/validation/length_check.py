#!/usr/bin/env python3
"""
长度比例校验：用于粗略筛查译文过短/过长问题。
"""
from typing import Tuple


def validate_length_ratio(original: str, translated: str, min_ratio: float = 0.3, max_ratio: float = 3.0) -> Tuple[bool, str]:
    """校验译文与原文长度比例是否在[min_ratio, max_ratio]内。

    Returns:
        (ok, reason)
    """
    if not translated or not translated.strip():
        return False, "译文为空"

    o = len(original or "")
    t = len(translated or "")
    if o <= 0:
        # 无原文时不做该规则判断
        return True, "跳过：原文为空"

    ratio = t / max(1, o)
    if ratio < min_ratio:
        return False, "译文过短"
    if ratio > max_ratio:
        return False, "译文过长"
    return True, "长度比例正常"



