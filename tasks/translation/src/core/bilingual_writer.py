#!/usr/bin/env python3
"""
双语写入工具：支持增量更新与安全落盘。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional


class BilingualWriter:
    """负责管理原文/译文对齐与写盘的工具类。"""

    def __init__(
        self,
        yaml_lines: List[str],
        body_lines: List[str],
        translations: List[Optional[str]],
        output_path: Path,
        temp_suffix: str = ".tmp",
    ):
        if len(body_lines) != len(translations):
            raise ValueError("body_lines 与 translations 长度不一致")
        self.yaml_lines = list(yaml_lines) if yaml_lines else []
        self.body_lines = body_lines
        self.translations = translations
        self.output_path = output_path
        self.temp_path = output_path.with_suffix(output_path.suffix + temp_suffix)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def update(self, updates: Dict[int, str], flush: bool = True) -> None:
        """更新指定行的译文并选择性写盘。"""
        for idx, value in updates.items():
            if idx < 0 or idx >= len(self.translations):
                raise IndexError(f"译文索引越界: {idx}")
            self.translations[idx] = value
        if flush:
            self.flush()

    def flush(self) -> None:
        """将当前译文状态写入临时文件后原子替换目标文件。"""
        content = self._build_text()
        self.temp_path.write_text(content, encoding="utf-8")
        self.temp_path.replace(self.output_path)

    def finalize(self) -> None:
        """最终写盘（与 flush 相同，语义更清晰）。"""
        self.flush()

    def _build_text(self) -> str:
        lines = list(self.yaml_lines)
        for idx, line in enumerate(self.body_lines):
            lines.append(line)
            if not line.strip():
                continue
            translation = self.translations[idx] or "[翻译未完成]"
            lines.append(translation)
        return "\n".join(lines) + "\n"
