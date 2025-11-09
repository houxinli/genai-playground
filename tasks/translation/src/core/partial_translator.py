#!/usr/bin/env python3
"""
部分翻译辅助模块
"""

from __future__ import annotations

import re
from typing import List, Tuple, Dict


class PartialTranslationHelper:
    """根据缺失区间调用 Translator.translate_lines_simple 的辅助类。"""

    def __init__(self, config, translator):
        self.config = config
        self.translator = translator

    def _collect_context(self, body_lines: List[str], start: int, end: int) -> List[str]:
        context_size = max(0, getattr(self.config, "context_lines", 3))
        if context_size == 0:
            return []
        before: List[str] = []
        idx = start - 1
        while idx >= 0 and len(before) < context_size:
            line = body_lines[idx].strip()
            if line:
                before.append(line)
            idx -= 1
        before.reverse()

        after: List[str] = []
        idx = end + 1
        total = len(body_lines)
        while idx < total and len(after) < context_size:
            line = body_lines[idx].strip()
            if line:
                after.append(line)
            idx += 1
        return before + after

    def translate_segments(
        self,
        body_lines: List[str],
        segments: List[Tuple[int, int]],
    ) -> Dict[int, str]:
        """逐段翻译缺失文本，返回 {行索引: 译文}"""
        translations: Dict[int, str] = {}
        previous_io = None
        for start, end in segments:
            target_lines = body_lines[start : end + 1]
            context_lines = self._collect_context(body_lines, start, end)
            translated_lines, _, ok, _, previous_io = self.translator.translate_lines_simple(
                target_lines,
                previous_io=previous_io,
                start_line_number=start + 1,
                context_lines=context_lines,
            )
            if not ok or not translated_lines:
                for idx in range(start, end + 1):
                    if body_lines[idx].strip():
                        translations[idx] = "[翻译未完成]"
                previous_io = None
                continue
            cleaned_translations = [line for line in translated_lines if line.strip()]
            translated_idx = 0
            for offset, line in enumerate(target_lines):
                global_idx = start + offset
                if not body_lines[global_idx].strip():
                    continue
                if translated_idx < len(cleaned_translations):
                    trans_line = cleaned_translations[translated_idx]
                    translated_idx += 1
                else:
                    trans_line = ""
                translations[global_idx] = self._validate_translation(body_lines[global_idx], trans_line)

        return translations

    _chinese_pattern = re.compile(r"[\u4e00-\u9fff]")
    _japanese_pattern = re.compile(r"[\u3040-\u30ff]")

    def _validate_translation(self, original: str, translation: str) -> str:
        stripped_orig = original.strip()
        stripped_trans = translation.strip()
        if not stripped_trans:
            return "[翻译未完成]"
        if stripped_trans == stripped_orig:
            return "[翻译未完成]"
        if not self._chinese_pattern.search(stripped_trans) and self._japanese_pattern.search(stripped_trans):
            return "[翻译未完成]"
        return translation or "[翻译未完成]"
