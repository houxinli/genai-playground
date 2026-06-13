#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Source adapter:把一个源目录里的 .txt 源文件转成 DocumentRevision 列表。

只做枚举 + 委托给 source_identity 构建身份;不写 candidate、不切主路径(那是 P0.6/P1)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from .source_identity import build_document_revision
except ImportError:  # core/ 在 sys.path 上
    from source_identity import build_document_revision


def iter_source_files(root_dir: Path) -> List[Path]:
    """源目录下的正文 .txt(排除 .meta.json 边车),自然排序。"""
    root = Path(root_dir)
    files = [p for p in root.glob("*.txt") if not p.name.endswith(".meta.json")]
    return sorted(files, key=lambda p: p.name)


def adapt_directory(provider: str, root_dir: Path) -> List[Dict[str, Any]]:
    """把源目录转成 DocumentRevision 列表(每个 .txt 一个,schema 已校验)。"""
    return [build_document_revision(provider, path) for path in iter_source_files(root_dir)]
