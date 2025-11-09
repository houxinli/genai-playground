#!/usr/bin/env python3
"""根据指定日志重建单个 fanbox/momizi813 双语文件。"""

import re
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "data" / "fanbox" / "momizi813"
OUT_DIR = ROOT / "data" / "fanbox" / "momizi813_bilingual_fixed"

number_re = re.compile(r'^([0-9０-９]+)[\.．、,，\)）]\s*')
pattern = re.compile(r"简化翻译[:：]\s*(.+)")
batch_re = re.compile(r"翻译批次\s+\d+.*共(\d+)行")
update_re = re.compile(r"更新双语文件批次")
CONTEXT_MARKERS = ("【最近上下文】",)
FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def to_int(num_str: str) -> int:
    return int(num_str.translate(FULLWIDTH_DIGITS))


def parse_translations(log_path: Path) -> list[str]:
    translations: list[str] = []
    skip_context = False
    expected_total = 0
    current_chunk: dict[int, str] = {}
    max_index_in_chunk = 0

    def finalize_chunk() -> None:
        nonlocal expected_total, current_chunk, max_index_in_chunk
        if not current_chunk and not expected_total:
            return
        total = expected_total if expected_total else max_index_in_chunk
        for idx in range(1, total + 1):
            translations.append(current_chunk.get(idx, '[翻译未完成]'))
        expected_total = 0
        current_chunk = {}
        max_index_in_chunk = 0

    with log_path.open('r', encoding='utf-8', errors='ignore') as f:
        for raw_line in f:
            if batch_re.search(raw_line):
                finalize_chunk()
                expected_total = int(batch_re.search(raw_line).group(1))
                continue
            if update_re.search(raw_line):
                finalize_chunk()
                continue
            if "[INFO]" not in raw_line:
                continue
            m = pattern.search(raw_line)
            if not m:
                continue
            raw_text = m.group(1).strip()
            if not raw_text:
                if skip_context:
                    skip_context = False
                continue
            if any(raw_text.startswith(marker) for marker in CONTEXT_MARKERS):
                skip_context = True
                continue
            if skip_context:
                continue
            cleaned = raw_text.replace('[翻译完成]', '').strip()
            match = number_re.match(cleaned)
            number_value = None
            remainder = cleaned
            if match:
                number_value = to_int(match.group(1))
                remainder = cleaned[match.end():].strip()
                if number_value < 1:
                    number_value = 1
            else:
                number_value = max_index_in_chunk + 1

            if expected_total and number_value > expected_total:
                number_value = expected_total

            value = remainder if remainder else '[翻译未完成]'
            previous = current_chunk.get(number_value)
            if previous is None or (previous == '[翻译未完成]' and value != '[翻译未完成]'):
                current_chunk[number_value] = value
                if number_value > max_index_in_chunk:
                    max_index_in_chunk = number_value
            elif number_value not in current_chunk:
                current_chunk[number_value] = value
                if number_value > max_index_in_chunk:
                    max_index_in_chunk = number_value

    finalize_chunk()
    return translations


def split_yaml_body(lines: list[str]) -> tuple[list[str], list[str]]:
    idx = [i for i, line in enumerate(lines) if line.strip() == '---']
    if len(idx) < 2:
        raise ValueError('原文缺少 YAML 分隔符')
    return lines[: idx[1] + 1], lines[idx[1] + 1 :]


def is_media(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith('[image]') or stripped.startswith('[link]') or stripped.startswith('[attachment]')


def rebuild(log_path: Path, file_id: str) -> None:
    src_path = SRC_DIR / f"{file_id}.txt"
    if not src_path.exists():
        raise FileNotFoundError(f"原文不存在: {src_path}")
    translations = parse_translations(log_path)
    if not translations:
        raise RuntimeError(f"日志中没有解析到译文: {log_path}")
    yaml_lines, body_lines = split_yaml_body(src_path.read_text(encoding='utf-8', errors='ignore').splitlines())
    out_lines = yaml_lines + ['']
    trans_idx = 0
    for line in body_lines:
        out_lines.append(line)
        if not line.strip():
            continue
        if is_media(line):
            out_lines.append(line)
            continue
        if trans_idx < len(translations):
            out_lines.append(translations[trans_idx])
            trans_idx += 1
        else:
            out_lines.append('[翻译未完成]')
    print(f"使用译文 {trans_idx}/{len(translations)} 条")
    out_path = OUT_DIR / f"{file_id}.txt"
    out_path.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')
    print(f"已写入 {out_path}")


def main():
    parser = argparse.ArgumentParser(description="根据日志重建单个 fanbox 双语文件")
    parser.add_argument('--log', required=True, help='翻译日志路径')
    parser.add_argument('--file-id', required=True, help='原文文件 ID，例如 2580952')
    args = parser.parse_args()
    rebuild(Path(args.log).resolve(), args.file_id)


if __name__ == '__main__':
    main()
