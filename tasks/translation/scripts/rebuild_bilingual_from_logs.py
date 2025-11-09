#!/usr/bin/env python3
"""根据翻译日志重建 fanbox/momizi813 双语文本，输出到新的目录。"""
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
SRC_DIR = ROOT / "data" / "fanbox" / "momizi813"
OLD_BI_DIR = ROOT / "data" / "fanbox" / "momizi813_bilingual"
OUT_DIR = ROOT / "data" / "fanbox" / "momizi813_bilingual_fixed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

target_prefix = str(Path("data/fanbox/momizi813/"))

log_file_pattern = re.compile(r"开始处理文件:\s*(.+)")
success_pattern = re.compile(r"翻译完成：总计|处理完成:\s*1/1")

def build_log_mapping() -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for log_path in sorted(LOG_DIR.glob("translation_*.log")):
        target_path = None
        success = False
        try:
            with log_path.open('r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if target_path is None:
                        m = log_file_pattern.search(line)
                        if m:
                            candidate = m.group(1).strip()
                            if candidate.startswith(target_prefix):
                                target_path = candidate
                    if not success and success_pattern.search(line):
                        success = True
        except Exception as exc:  # pragma: no cover
            print(f"[WARN] 无法读取日志 {log_path}: {exc}")
            continue
        if not target_path or not success:
            continue
        file_id = Path(target_path).stem
        prev = mapping.get(file_id)
        if prev is None or log_path.name > prev.name:
            mapping[file_id] = log_path
    return mapping

number_prefix = re.compile(r'^[0-9０-９]+[\.．、\)]\s*')
context_markers = (
    "【最近上下文",
    "【上一批",
)
timestamp_re = re.compile(r'^\d{4}-\d{2}-\d{2}')
chinese_re = re.compile(r'[\u4e00-\u9fff]')
japanese_re = re.compile(r'[\u3040-\u30ff]')

def is_media_line(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith('[image]') or stripped.startswith('[link]') or stripped.startswith('[attachment]')

def has_chinese(text: str) -> bool:
    return bool(chinese_re.search(text))

def has_japanese(text: str) -> bool:
    return bool(japanese_re.search(text))

def parse_translations(log_path: Path) -> list[str]:
    translations: list[str] = []
    pattern = re.compile(r"简化翻译[:：]\s*(.+)")
    collecting_output = False
    awaiting_output = False
    with log_path.open('r', encoding='utf-8', errors='ignore') as f:
        for raw_line in f:
            line = raw_line.rstrip('\n')
            m = pattern.search(line)
            if m:
                text = m.group(1).strip()
                if not text:
                    continue
                if any(text.startswith(marker) for marker in context_markers):
                    continue
                text = text.replace('[翻译完成]', '').strip()
                text = number_prefix.sub('', text)
                translations.append(text)
                continue
            if '开始简化翻译流式调用' in line:
                collecting_output = False
                awaiting_output = True
                continue
            if awaiting_output and 'OpenRouter headers' in line:
                collecting_output = True
                awaiting_output = False
                continue
            if collecting_output:
                if timestamp_re.match(line):
                    collecting_output = False
                    awaiting_output = False
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped == '[翻译完成]':
                    continue
                if any(stripped.startswith(marker) for marker in context_markers):
                    continue
                text = number_prefix.sub('', stripped)
                translations.append(text)
    return translations

def read_yaml_block(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
    except Exception:
        return []
    idx = [i for i, line in enumerate(lines) if line.strip() == '---']
    if len(idx) < 2:
        return []
    return lines[: idx[1] + 1]

def main() -> None:
    log_mapping = build_log_mapping()
    if not log_mapping:
        print("[INFO] 未找到可用的日志")
        return
    print(f"找到 {len(log_mapping)} 篇对应日志")
    count_written = 0
    for file_id, log_path in sorted(log_mapping.items()):
        src_path = SRC_DIR / f"{file_id}.txt"
        if not src_path.exists():
            print(f"[WARN] 原文不存在: {src_path}")
            continue
        translations = parse_translations(log_path)
        if not translations:
            print(f"[WARN] 日志中没有翻译内容: {log_path}")
            continue
        yaml_lines = read_yaml_block(OLD_BI_DIR / f"{file_id}.txt")
        if not yaml_lines:
            yaml_lines = read_yaml_block(src_path)
        body_lines = src_path.read_text(encoding='utf-8', errors='ignore').splitlines()
        idx = [i for i, line in enumerate(body_lines) if line.strip() == '---']
        if len(idx) < 2:
            print(f"[WARN] 原文缺少YAML分隔: {src_path}")
            continue
        body = body_lines[idx[1] + 1 :]
        output_body: list[str] = []
        trans_idx = 0
        for line in body:
            output_body.append(line)
        if not line.strip():
            continue
        if is_media_line(line):
            output_body.append(line)
            continue
        if trans_idx >= len(translations):
            output_body.append('[翻译未完成]')
            continue
        translation = translations[trans_idx]
        trans_idx += 1
        if (not has_chinese(translation) and has_japanese(translation)) or translation == line:
            translation = '[翻译未完成]'
        output_body.append(translation)
        if trans_idx != len(translations):
            unused = len(translations) - trans_idx
            print(f"[WARN] {file_id}: 未使用的译文 {unused} 条")
        out_path = OUT_DIR / f"{file_id}.txt"
        with out_path.open('w', encoding='utf-8') as f:
            if yaml_lines:
                f.write("\n".join(yaml_lines) + "\n")
            f.write("\n")
            f.write("\n".join(output_body))
            f.write("\n")
        count_written += 1
        print(f"[OK] 写入 {out_path} (译文 {trans_idx} 条)")

    print(f"完成，写入 {count_written} 篇。输出目录: {OUT_DIR}")

if __name__ == '__main__':
    main()
