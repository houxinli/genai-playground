#!/usr/bin/env python3
"""预设参数加载工具"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional


def _default_presets_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "presets.json"


def load_presets(presets_file: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    path = presets_file or _default_presets_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def prepare_preset_defaults(parser, preset_name: Optional[str], presets_file: Optional[Path]) -> None:
    """在解析命令前，将预设写入 parser 默认值中。"""
    if not preset_name:
        return
    presets = load_presets(presets_file)
    config = presets.get(preset_name)
    if not isinstance(config, dict):
        print(f"警告：未找到预设 {preset_name}，忽略 --preset 参数")
        return
    parser.set_defaults(**config)
