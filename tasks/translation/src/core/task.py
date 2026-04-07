#!/usr/bin/env python3
"""统一的翻译/修复任务描述。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal


@dataclass(frozen=True)
class TranslationTask:
    """描述一篇文章在流水线中的处理方式。"""

    original_path: Optional[Path]
    existing_bilingual_path: Optional[Path]
    output_path: Path
    mode: Literal["translate", "repair"] = "translate"
    output_status: Literal["missing", "partial", "complete", "failed", "running"] = "missing"
    output_reason: str = ""
    run_id: str = ""
