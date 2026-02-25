#!/usr/bin/env python3
"""
简易错位修复工具：将双语文件中的译文整体按行偏移，再补齐空缺。

用法示例：
  python shift_bilingual.py INPUT.txt --shift 3 --output OUTPUT.txt

定义：
  - shift > 0：译文整体向前挪（新第 i 行译文 = 旧第 i+shift 行译文）
  - shift < 0：译文整体向后挪
  - 超出范围或缺失的译文会写入 "[翻译未完成]"
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple, Optional

PLACEHOLDER = "[翻译未完成]"


def split_yaml_body(lines: List[str]) -> Tuple[List[str], List[str]]:
    """将文件按 YAML front matter 与正文拆分。"""
    if lines and lines[0].strip() == "---":
        for idx, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return lines[: idx + 1], lines[idx + 1 :]
    return [], lines


def load_bilingual_body(body_lines: List[str]) -> Tuple[List[str], List[Optional[str]]]:
    """
    解析正文：返回原文行列表与对应译文。
    约定：非空原文行应紧跟一个译文行；空白行不带译文。
    """
    originals: List[str] = []
    translations: List[Optional[str]] = []
    idx = 0
    total = len(body_lines)
    while idx < total:
        original = body_lines[idx]
        originals.append(original)
        idx += 1
        if original.strip():
            if idx < total:
                translations.append(body_lines[idx])
                idx += 1
            else:
                translations.append(None)
        else:
            translations.append(None)
    return originals, translations


def apply_shift(
    originals: List[str],
    translations: List[Optional[str]],
    shift: int,
) -> List[Optional[str]]:
    """根据 shift 计算新的译文列表（仅对非空原文行偏移）。"""
    shifted = list(translations)
    content_positions = [idx for idx, line in enumerate(originals) if line.strip()]
    content_count = len(content_positions)
    for rank, pos in enumerate(content_positions):
        src_rank = rank + shift
        if 0 <= src_rank < content_count:
            src_idx = content_positions[src_rank]
            candidate = translations[src_idx]
        else:
            candidate = None
        shifted[pos] = candidate if candidate is not None else PLACEHOLDER
    return shifted


def rebuild_lines(yaml_lines: List[str], originals: List[str], translations: List[Optional[str]]) -> List[str]:
    """组合 YAML 与正文，生成新的行列表。"""
    result: List[str] = []
    if yaml_lines:
        result.extend(yaml_lines)
        # YAML 末尾已包含 '---'，补一个空行与正文分隔
        result.append("")
    for original, translation in zip(originals, translations):
        result.append(original)
        if original.strip():
            result.append(translation or PLACEHOLDER)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="按行整体偏移译文的修复脚本")
    parser.add_argument("input", type=Path, help="输入的 *_bilingual.txt 文件")
    parser.add_argument("--shift", type=int, required=True, help="译文偏移量（>0 向前，<0 向后）")
    parser.add_argument("--output", type=Path, required=True, help="输出文件路径")
    args = parser.parse_args()

    input_path: Path = args.input
    output_path: Path = args.output
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在: {input_path}")

    raw_text = input_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    yaml_lines, body_lines = split_yaml_body(raw_text)
    originals, translations = load_bilingual_body(body_lines)
    shifted_translations = apply_shift(originals, translations, args.shift)
    output_lines = rebuild_lines(yaml_lines, originals, shifted_translations)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    total_pairs = sum(1 for line in originals if line.strip())
    print(
        f"完成：共处理 {total_pairs} 行原文，shift={args.shift}，输出 {output_path}"
    )


if __name__ == "__main__":
    main()
