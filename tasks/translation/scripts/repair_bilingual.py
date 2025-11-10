#!/usr/bin/env python3
"""
部分翻译修复工具（增量写盘版）
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys
from typing import Dict, List, Tuple, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
TRANSLATION_DIR = SCRIPT_DIR.parent
if str(TRANSLATION_DIR) not in sys.path:
    sys.path.insert(0, str(TRANSLATION_DIR))

from src.cli import create_argument_parser, validate_args, setup_default_paths
from src.core.config import TranslationConfig
from src.core.pipeline import TranslationPipeline
from src.core.partial_translator import PartialTranslationHelper
from src.core.bilingual_writer import BilingualWriter
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


def parse_bilingual_components(path: Path) -> Tuple[List[str], List[str], List[str]]:
    yaml_lines, merged_body = parse_body_lines(path.read_text(encoding="utf-8", errors="ignore"))
    originals: List[str] = []
    translations: List[str] = []
    i = 0
    n = len(merged_body)
    while i < n:
        orig = merged_body[i]
        originals.append(orig)
        i += 1
        if not orig.strip():
            translations.append("")
            continue
        if i < n:
            translations.append(merged_body[i])
            i += 1
        else:
            translations.append("")
    return yaml_lines, merged_body, originals, translations


def extract_original_from_bilingual(originals: List[str], translations: List[str]) -> List[str]:
    # Originals already extracted; keep as-is
    return originals[:]


def collect_input_files(inputs: List[str]) -> List[Path]:
    files: List[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            files.extend(sorted(path.rglob("*.txt")))
        elif path.is_file():
            files.append(path)
    return sorted(set(files))


def is_bilingual_file(path: Path) -> bool:
    parts = [path.name] + [p.name for p in path.parents]
    return any("_bilingual" in part for part in parts)


def align_existing_translations(
    body_lines: List[str], bilingual_body: List[str]
) -> List[Optional[str]]:
    translations: List[Optional[str]] = [None] * len(body_lines)
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


def has_japanese(text: str) -> bool:
    if not text:
        return False
    normalized = text.replace("\u30fb", "").replace("\u30fc", "")
    if not normalized.strip():
        return False
    return bool(re.search(r"[\u3040-\u309f\u30a0-\u30ff]", normalized))


def needs_translation(orig: str, translation: Optional[str]) -> bool:
    if translation is None:
        return True
    stripped = translation.strip()
    if not stripped:
        return True
    if stripped in {"[翻译未完成]", "[翻译失败]"}:
        return True
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


def ensure_bilingual_path(original: Path, explicit: Optional[Path], dir_override: Optional[Path] = None) -> Path:
    if explicit:
        return explicit
    if dir_override:
        dir_override.mkdir(parents=True, exist_ok=True)
        return dir_override / original.name
    base_dir = original.parent.parent / f"{original.parent.name}_bilingual"
    return base_dir / f"{original.stem}.txt"


def ensure_output_path(original: Path, explicit: Optional[Path], dir_override: Optional[Path] = None) -> Path:
    if explicit:
        explicit.parent.mkdir(parents=True, exist_ok=True)
        return explicit
    if dir_override:
        dir_override.mkdir(parents=True, exist_ok=True)
        return dir_override / original.name
    out_dir = original.parent.parent / f"{original.parent.name}_bilingual_fixed"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{original.stem}.txt"


def format_line_spans(numbers: List[int]) -> str:
    if not numbers:
        return ""
    numbers = sorted(numbers)
    spans: List[str] = []
    start = prev = numbers[0]
    for num in numbers[1:]:
        if num == prev + 1:
            prev = num
            continue
        spans.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = num
    spans.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(spans)


def parse_args() -> argparse.Namespace:
    raw_argv = sys.argv[1:]
    preset_parser = argparse.ArgumentParser(add_help=False)
    preset_parser.add_argument("--preset")
    preset_parser.add_argument("--presets-file")
    preset_args, _ = preset_parser.parse_known_args(raw_argv)

    parser = create_argument_parser()
    parser.description = "仅翻译缺失段落并增量更新双语文件"
    parser.add_argument("--existing-bilingual", type=Path, help="单文件模式：已存在的双语文件路径")
    parser.add_argument("--existing-bilingual-dir", type=Path, help="批量模式：现有双语目录，按文件名匹配")
    parser.add_argument("--output", type=Path, help="单文件模式：修复后的输出文件路径")
    parser.add_argument("--output-dir", type=Path, help="批量模式：输出目录（默认 *_bilingual_fixed）")
    parser.add_argument("--max-lines", type=int, default=0, help="最多修复的行数（0 表示不限）")
    parser.add_argument("--repair-context-lines", type=int, help="修复模式上下文行数覆盖值")
    presets_file = Path(preset_args.presets_file).expanduser() if preset_args.presets_file else None
    prepare_preset_defaults(parser, preset_args.preset, presets_file)
    args = parser.parse_args(raw_argv)
    return args


def main() -> None:
    args = parse_args()
    if not args.inputs:
        raise SystemExit("必须提供至少一个文件或目录")

    setup_default_paths(args)
    errors = validate_args(args)
    if errors:
        raise SystemExit("\n".join(errors))

    config = TranslationConfig.from_args(args)
    if args.repair_context_lines is not None:
        setattr(config, "repair_context_lines", args.repair_context_lines)

    targets = collect_input_files(args.inputs)
    if not targets:
        raise SystemExit("未在输入路径中找到任何 .txt 文件")

    if len(targets) > 1:
        if args.existing_bilingual:
            print("⚠️ 多文件模式下忽略 --existing-bilingual 参数")
            args.existing_bilingual = None
        if args.output:
            print("⚠️ 多文件模式下忽略 --output 参数")
            args.output = None

    pipeline = TranslationPipeline(config)
    helper = PartialTranslationHelper(config, pipeline.translator)

    success = 0
    for idx, path in enumerate(targets, 1):
        print(f"[{idx}/{len(targets)}] 修复 {path}")
        try:
            if process_single_file(path, args, config, helper):
                success += 1
        except Exception as exc:
            print(f"❌ {path} 修复失败: {exc}")

    print(f"完成：{success}/{len(targets)} 篇成功修复")


def process_single_file(
    input_path: Path,
    args: argparse.Namespace,
    config: TranslationConfig,
    helper: PartialTranslationHelper,
) -> bool:
    treating_bilingual = is_bilingual_file(input_path)
    original_path = None if treating_bilingual else input_path

    existing_path = input_path if treating_bilingual else ensure_bilingual_path(
        original_path,
        args.existing_bilingual,
        args.existing_bilingual_dir,
    )
    output_path = ensure_output_path(
        original_path or existing_path,
        args.output,
        args.output_dir,
    )

    if not existing_path.exists():
        print(f"⚠️ 缺少双语文件: {existing_path}")
        return False

    UnifiedLogger._debug_files_mode = getattr(config, "debug_files", False)
    UnifiedLogger._log_level = getattr(config, "log_level", "INFO")
    log_dir = Path(config.log_dir)
    log_target = original_path if original_path else existing_path
    repair_logger = UnifiedLogger.create_for_file(
        log_target,
        log_dir,
        stream_output=bool(config.realtime_log),
        custom_basename=f"{log_target.stem}_repair",
    )
    translator = helper.translator
    translator.logger = repair_logger
    if hasattr(translator, "streaming_handler"):
        translator.streaming_handler.logger = repair_logger

    helper.translator.current_output_path = str(output_path)
    repair_logger.info(f"🛠 修复目标: {log_target}")
    repair_logger.info(f"📄 输出文件: {output_path}")

    original_yaml: List[str] = []
    original_body: List[str] = []
    if original_path and original_path.exists():
        original_yaml, original_body = load_file_lines(original_path)

    existing_yaml, existing_body = parse_body_lines(existing_path.read_text(encoding="utf-8", errors="ignore"))
    if not original_body:
        # 从双语文件中提取原文
        extracted_originals: List[str] = []
        i = 0
        while i < len(existing_body):
            extracted_originals.append(existing_body[i])
            if existing_body[i].strip():
                i += 2
            else:
                i += 1
        original_body = extracted_originals
        original_yaml = existing_yaml

    base_yaml = existing_yaml if existing_yaml else original_yaml
    existing_trans = align_existing_translations(original_body, existing_body)

    missing_mask: List[bool] = []
    for orig_line, trans_line in zip(original_body, existing_trans):
        if not orig_line.strip():
            missing_mask.append(False)
            continue
        missing_mask.append(needs_translation(orig_line, trans_line))

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
        writer = BilingualWriter(base_yaml, original_body, existing_trans, output_path)
        writer.finalize()
        repair_logger.info("没有检测到需要修复的行，直接复制现有双语文件。")
        return True

    repair_logger.info(f"将翻译缺失行 {planned_missing}/{total_missing} 行")
    writer = BilingualWriter(base_yaml, original_body, existing_trans[:], output_path)
    updated_indices: List[int] = []

    def _on_segment_complete(updates: Dict[int, str]) -> None:
        writer.update(updates, flush=True)
        updated_indices.extend(idx + 1 for idx in updates.keys())

    new_translations = helper.translate_segments(
        original_body,
        segments,
        reference_translations=writer.translations,
        on_segment_complete=_on_segment_complete,
    )

    for idx, value in new_translations.items():
        writer.translations[idx] = value
    writer.finalize()

    unresolved = [
        idx + 1
        for idx in new_translations.keys()
        if needs_translation(original_body[idx], writer.translations[idx])
    ]
    if updated_indices:
        unique = sorted(set(updated_indices))
        repair_logger.info(
            f"本次修复 {len(unique)} 行: {format_line_spans(unique)}"
        )
    if unresolved:
        repair_logger.warning(
            f"仍有行需人工处理: {format_line_spans(unresolved)}"
        )
    return True


if __name__ == "__main__":
    main()
