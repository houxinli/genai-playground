#!/usr/bin/env python3
"""
部分翻译修复工具

用法示例：
    cd tasks/translation &&
    python scripts/repair_bilingual.py \
        data/fanbox/momizi813/2580952.txt \
        --existing-bilingual data/fanbox/momizi813_bilingual/2580952.txt \
        --output data/fanbox/momizi813_bilingual_fixed/2580952.txt \
        --preset fanbox_grok4_fast --overwrite
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys
from typing import List, Dict, Tuple

from src.cli import create_argument_parser, validate_args, setup_default_paths
from src.core.config import TranslationConfig
from src.core.pipeline import TranslationPipeline
from src.core.partial_translator import PartialTranslationHelper
from src.core.logger import UnifiedLogger
from src.utils.file import parse_yaml_front_matter
from src.utils.presets import prepare_preset_defaults


def parse_body_lines(text: str) -> Tuple[List[str], List[str]]:
    lines = text.splitlines()
    idx = [i for i, line in enumerate(lines) if line.strip() == '---']
    if len(idx) < 2:
        raise ValueError("输入不包含完整的 YAML front matter")
    return lines[: idx[1] + 1], lines[idx[1] + 1 :]


def load_file_lines(path: Path) -> Tuple[List[str], List[str]]:
    content = path.read_text(encoding="utf-8", errors="ignore")
    return parse_body_lines(content)


def align_existing_translations(
    body_lines: List[str], bilingual_body: List[str]
) -> List[str | None]:
    translations: List[str | None] = [None] * len(body_lines)
    b_idx = 0
    total = len(bilingual_body)
    for idx, line in enumerate(body_lines):
        if not line.strip():
            continue
        while b_idx < total and bilingual_body[b_idx] != line:
            b_idx += 1
        if b_idx >= total:
            break
        b_idx += 1
        while b_idx < total and not bilingual_body[b_idx].strip():
            b_idx += 1
        if b_idx < total:
            translations[idx] = bilingual_body[b_idx]
            b_idx += 1
    return translations


def has_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def has_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff]", text))


def needs_translation(orig: str, translation: str | None) -> bool:
    if translation is None:
        return True
    stripped = translation.strip()
    if not stripped:
        return True
    if stripped in {"[翻译未完成]", "[翻译失败]"}:
        return True
    # 译文中出现任何假名都视为未完全修复，避免混入残留的日文字符
    if has_japanese(stripped):
        return True
    return False


def build_segments(body_lines: List[str], missing_mask: List[bool]) -> List[Tuple[int, int]]:
    segments = []
    i = 0
    n = len(body_lines)
    while i < n:
        if not missing_mask[i]:
            i += 1
            continue
        start = i
        end = i
        i += 1
        while i < n:
            if missing_mask[i]:
                end = i
                i += 1
            elif not body_lines[i].strip():
                end = i
                i += 1
            else:
                break
        segments.append((start, end))
    return segments


def rebuild_bilingual_output(
    body_lines: List[str],
    translations: List[str | None],
    yaml_lines: List[str],
) -> List[str]:
    output_lines = list(yaml_lines) + [""]
    for idx, line in enumerate(body_lines):
        output_lines.append(line)
        if not line.strip():
            continue
        translation = translations[idx]
        if not translation:
            translation = "[翻译未完成]"
        output_lines.append(translation)
    return output_lines


def ensure_bilingual_path(original: Path, explicit: Path | None) -> Path:
    if explicit:
        return explicit
    base_dir = original.parent.parent / f"{original.parent.name}_bilingual"
    return base_dir / f"{original.stem}.txt"


def ensure_output_path(original: Path, explicit: Path | None) -> Path:
    if explicit:
        explicit.parent.mkdir(parents=True, exist_ok=True)
        return explicit
    out_dir = original.parent.parent / f"{original.parent.name}_bilingual_fixed"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{original.stem}.txt"


def parse_args() -> argparse.Namespace:
    raw_argv = sys.argv[1:]
    preset_parser = argparse.ArgumentParser(add_help=False)
    preset_parser.add_argument("--preset")
    preset_parser.add_argument("--presets-file")
    preset_args, _ = preset_parser.parse_known_args(raw_argv)

    parser = create_argument_parser()
    parser.description = "仅翻译缺失段落并生成双语文件"
    parser.add_argument("--existing-bilingual", type=Path, help="已存在的双语文件路径")
    parser.add_argument("--output", type=Path, help="修复后的输出文件路径")
    parser.add_argument("--max-lines", type=int, default=0, help="最多修复的行数（0 表示不限）")
    presets_file = Path(preset_args.presets_file).expanduser() if preset_args.presets_file else None
    prepare_preset_defaults(parser, preset_args.preset, presets_file)
    args = parser.parse_args(raw_argv)
    return args


def main() -> None:
    args = parse_args()
    if not args.inputs:
        raise SystemExit("必须提供原文文件路径")
    original_path = Path(args.inputs[0]).resolve()
    args.inputs[0] = str(original_path)
    existing_path = ensure_bilingual_path(original_path, args.existing_bilingual)
    output_path = ensure_output_path(original_path, args.output)

    setup_default_paths(args)
    errors = validate_args(args)
    if errors:
        raise SystemExit("\n".join(errors))

    config = TranslationConfig.from_args(args)
    UnifiedLogger._debug_files_mode = getattr(config, "debug_files", False)
    UnifiedLogger._log_level = getattr(config, "log_level", "INFO")
    log_dir = Path(config.log_dir)
    repair_logger = UnifiedLogger.create_for_file(
        original_path,
        log_dir,
        stream_output=bool(config.realtime_log),
        custom_basename=f"{original_path.stem}_repair",
    )
    repair_logger.info(f"🛠 修复目标: {original_path}")
    repair_logger.info(f"📄 输出文件: {output_path}")
    if repair_logger.get_log_file_path():
        repair_logger.info(f"📝 日志文件: {repair_logger.get_log_file_path()}")

    pipeline = TranslationPipeline(config)
    pipeline.logger = repair_logger
    pipeline.file_handler.logger = repair_logger
    pipeline.quality_checker.logger = repair_logger
    pipeline.translator.logger = repair_logger
    if hasattr(pipeline.translator, "streaming_handler"):
        pipeline.translator.streaming_handler.logger = repair_logger
    if hasattr(pipeline.quality_checker, "streaming_handler"):
        pipeline.quality_checker.streaming_handler.logger = repair_logger
    helper = PartialTranslationHelper(config, pipeline.translator)

    original_yaml, original_body = load_file_lines(original_path)
    existing_yaml, existing_body = load_file_lines(existing_path)

    existing_trans = align_existing_translations(original_body, existing_body)
    missing_mask: List[bool] = []
    for orig_line, trans_line in zip(original_body, existing_trans):
        if not orig_line.strip():
            missing_mask.append(False)
            continue
        missing_mask.append(needs_translation(orig_line, trans_line))

    # 如果原文不包含假名且译文缺失，直接复制原文以避免重复送模
    for idx, (orig_line, is_missing) in enumerate(zip(original_body, missing_mask)):
        if not is_missing:
            continue
        if has_japanese(orig_line):
            continue
        existing_trans[idx] = orig_line
        missing_mask[idx] = False

    segments = build_segments(original_body, missing_mask)
    if args.max_lines > 0:
        total_needed = sum(1 for flag in missing_mask if flag)
        if total_needed > args.max_lines:
            print(f"⚠️ 检测到 {total_needed} 行缺失翻译，已限制为 {args.max_lines} 行")
            allowed = args.max_lines
            limited_segments = []
            for start, end in segments:
                needed_in_segment = sum(
                    1 for idx in range(start, end + 1) if missing_mask[idx]
                )
                if needed_in_segment <= allowed:
                    limited_segments.append((start, end))
                    allowed -= needed_in_segment
                else:
                    # 截断 segment
                    count = 0
                    new_end = end
                    for idx in range(start, end + 1):
                        if missing_mask[idx]:
                            count += 1
                        if count > allowed:
                            new_end = idx - 1
                            break
                    limited_segments.append((start, new_end))
                    break
            segments = limited_segments

    total_missing = sum(1 for flag in missing_mask if flag)
    planned_missing = sum(
        1
        for start, end in segments
        for idx in range(start, end + 1)
        if missing_mask[idx]
    )
    if not segments:
        print("没有检测到需要修复的行，直接复制现有双语文件。")
        output_lines = rebuild_bilingual_output(
            original_body,
            existing_trans,
            existing_yaml if existing_yaml else original_yaml,
        )
        output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
        print(f"✅ 输出未修改原译文: {output_path}")
        return

    print(f"将翻译缺失行 {planned_missing}/{total_missing} 行")
    new_translations = helper.translate_segments(original_body, segments)

    final_translations: List[str | None] = existing_trans[:]
    for idx, value in new_translations.items():
        final_translations[idx] = value

    output_lines = rebuild_bilingual_output(original_body, final_translations, existing_yaml if existing_yaml else original_yaml)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    print(f"✅ 修复完成，输出: {output_path}")


if __name__ == "__main__":
    main()
