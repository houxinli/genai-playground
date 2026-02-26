#!/usr/bin/env python3
"""
部分翻译辅助模块
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple


class PartialTranslationHelper:
    """根据缺失区间调用 Translator.translate_lines_simple 的辅助类。"""

    _chinese_pattern = re.compile(r"[\u4e00-\u9fff]")
    _japanese_pattern = re.compile(r"[\u3040-\u30ff]")
    _REPAIR_INSTRUCTION = (
        "【修复规范】仅输出地道的简体中文及必要标点；即使原句只有假名或拟声词，也要改写成中文拟声/语气表达，严禁出现任何假名或英文提示。"
        "人名/称谓/专有名词必须严格沿用前文既有译法，不得改名或切换译法。"
    )
    _SHORT_SEGMENT_HINT = (
        "【短句提示】以下行多为感叹或拟声，请直接用中文拟声词表达（如「嗯嗯」「啧」「噗咕咕」等），不要保留“っ”“ん”“あぁ”等假名。"
    )

    def __init__(self, config, translator):
        self.config = config
        self.translator = translator

    def _determine_context_size(self) -> int:
        override = getattr(self.config, "repair_context_lines", None)
        if override is not None:
            return max(0, int(override))
        base = max(0, getattr(self.config, "context_lines", 3))
        return max(base, 6)

    def _collect_context_indices(
        self,
        body_lines: List[str],
        start: int,
        end: int,
    ) -> List[int]:
        context_size = self._determine_context_size()
        if context_size == 0:
            return []

        before: List[int] = []
        idx = start - 1
        while idx >= 0 and len(before) < context_size:
            if body_lines[idx].strip():
                before.append(idx)
            idx -= 1
        before.reverse()

        after: List[int] = []
        idx = end + 1
        total = len(body_lines)
        while idx < total and len(after) < context_size:
            if body_lines[idx].strip():
                after.append(idx)
            idx += 1
        return before + after

    def _is_valid_reference(self, text: Optional[str]) -> bool:
        if not text:
            return False
        stripped = text.strip()
        if stripped in {"[翻译未完成]", "[翻译失败]"}:
            return False
        if not self._chinese_pattern.search(stripped):
            return False
        if self._japanese_pattern.search(stripped) and not self._chinese_pattern.search(stripped):
            return False
        return True

    @staticmethod
    @staticmethod
    def _count_non_empty(lines: List[str]) -> int:
        return sum(1 for line in lines if line.strip())

    def _build_context_payload(
        self,
        body_lines: List[str],
        reference_translations: Optional[List[Optional[str]]],
        start: int,
        end: int,
        target_lines: List[str],
    ) -> List[str]:
        payload: List[str] = [self._REPAIR_INSTRUCTION]
        if self._count_non_empty(target_lines) <= 2:
            payload.append(self._SHORT_SEGMENT_HINT)

        indices = self._collect_context_indices(body_lines, start, end)
        if indices:
            payload.append("【上下文示例】")
        for idx in indices:
            original = body_lines[idx].strip()
            if not original:
                continue
            payload.append(f"原文: {original}")
            if reference_translations and idx < len(reference_translations):
                ref_trans = reference_translations[idx]
                if self._is_valid_reference(ref_trans):
                    payload.append(f"译文: {ref_trans.strip()}")

        return payload

    def translate_segments(
        self,
        body_lines: List[str],
        segments: List[Tuple[int, int]],
        reference_translations: Optional[List[Optional[str]]] = None,
        on_segment_complete: Optional[Callable[[Dict[int, str]], None]] = None,
    ) -> Dict[int, str]:
        """逐段翻译缺失文本，返回 {行索引: 译文}"""
        translations: Dict[int, str] = {}
        previous_io = None
        for start, end in segments:
            target_lines = body_lines[start : end + 1]
            context_lines = self._build_context_payload(
                body_lines,
                reference_translations,
                start,
                end,
                target_lines,
            )
            if self.translator.logger:
                try:
                    current_idx = start + 1
                    dest_info = getattr(self.translator, "current_output_path", None)
                    self.translator.logger.info(
                        f"🔁 翻译批次行 {current_idx}-{end + 1}"
                        + (f" -> {dest_info}" if dest_info else "")
                    )
                except Exception:
                    pass
            translated_lines, _, ok, _, previous_io = self.translator.translate_lines_simple(
                target_lines,
                previous_io=previous_io,
                start_line_number=start + 1,
                context_lines=context_lines,
            )
            if not ok or not translated_lines:
                segment_updates: Dict[int, str] = {}
                for idx in range(start, end + 1):
                    if body_lines[idx].strip():
                        translations[idx] = "[翻译未完成]"
                        segment_updates[idx] = "[翻译未完成]"
                        if reference_translations is not None:
                            reference_translations[idx] = "[翻译未完成]"
                if segment_updates and on_segment_complete:
                    on_segment_complete(segment_updates)
                previous_io = None
                continue
            cleaned_translations = [line for line in translated_lines if line.strip()]
            translated_idx = 0
            segment_updates: Dict[int, str] = {}
            for offset, line in enumerate(target_lines):
                global_idx = start + offset
                if not body_lines[global_idx].strip():
                    continue
                if translated_idx < len(cleaned_translations):
                    trans_line = cleaned_translations[translated_idx]
                    translated_idx += 1
                else:
                    trans_line = ""
                validated = self._validate_translation(body_lines[global_idx], trans_line)
                translations[global_idx] = validated
                segment_updates[global_idx] = validated
                if reference_translations is not None:
                    reference_translations[global_idx] = validated
            if segment_updates and on_segment_complete:
                on_segment_complete(segment_updates)

        return translations

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
