#!/usr/bin/env python3
"""
批量对双语文件“译文行”应用替换规则（例如统一人名译法）。

说明：
- 仅修改译文行，不动原文行。
- 支持 YAML 双行键（title/caption/excerpt/tags）的译文行。
- 支持目录/文件/通配符输入。
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


RE_TRANSLATABLE_KEYS = {"title", "caption", "excerpt", "tags"}


def collect_files(inputs: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for raw in inputs:
        p = Path(raw).expanduser()
        if p.is_file():
            files.append(p.resolve())
            continue
        if p.is_dir():
            files.extend(sorted(x.resolve() for x in p.glob("*.txt")))
            continue
        for matched in glob.glob(raw):
            m = Path(matched).expanduser()
            if m.is_file():
                files.append(m.resolve())
    return sorted(set(files))


def split_front_matter(lines: List[str]) -> Tuple[List[str], List[str]]:
    if not lines or lines[0].strip() != "---":
        return [], lines
    idx = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if len(idx) < 2:
        return [], lines
    end = idx[1]
    return lines[: end + 1], lines[end + 1 :]


def find_yaml_translation_line_indices(yaml_lines: List[str]) -> List[int]:
    out: List[int] = []
    if len(yaml_lines) < 3:
        return out

    def parse_key(line: str) -> Tuple[str, str] | None:
        if ":" not in line:
            return None
        left = line.split(":", 1)[0]
        return left.lstrip(" "), left[: len(left) - len(left.lstrip(" "))]

    for i in range(1, len(yaml_lines) - 1):
        p1 = parse_key(yaml_lines[i])
        p2 = parse_key(yaml_lines[i + 1])
        if not p1 or not p2:
            continue
        key1, indent1 = p1
        key2, indent2 = p2
        if key1 == key2 and indent1 == indent2 and key1 in RE_TRANSLATABLE_KEYS:
            out.append(i + 1)
    return out


def find_body_translation_line_indices(body_lines: List[str]) -> List[int]:
    out: List[int] = []
    i = 0
    total = len(body_lines)
    while i < total:
        orig = body_lines[i]
        if not orig.strip():
            i += 1
            continue
        if i + 1 < total:
            out.append(i + 1)
            i += 2
        else:
            i += 1
    return out


def resolve_output_path(input_path: Path, output_dir: Path | None, in_place: bool) -> Path:
    if in_place:
        return input_path
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / input_path.name
    out_dir = input_path.parent.with_name(f"{input_path.parent.name}_replaced")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / input_path.name


def parse_rule(line: str) -> Tuple[str, str]:
    if "=" not in line:
        raise ValueError(f"规则格式错误（缺少=）：{line}")
    src, dst = line.split("=", 1)
    src = src.strip()
    dst = dst.strip()
    if not src:
        raise ValueError(f"规则格式错误（左侧为空）：{line}")
    return src, dst


def load_rules(rule_args: Sequence[str], rules_file: Path | None) -> List[Tuple[str, str]]:
    rules: List[Tuple[str, str]] = []
    for raw in rule_args:
        rules.append(parse_rule(raw))
    if rules_file:
        for raw in rules_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            rules.append(parse_rule(line))
    # 长的优先，避免短词先替换导致连锁污染
    rules.sort(key=lambda x: len(x[0]), reverse=True)
    return rules


def apply_rules(text: str, rules: Sequence[Tuple[str, str]]) -> Tuple[str, int]:
    out = text
    count = 0
    for src, dst in rules:
        n = out.count(src)
        if n > 0:
            out = out.replace(src, dst)
            count += n
    return out, count


def main() -> None:
    parser = argparse.ArgumentParser(description="批量对双语文件译文行应用替换规则")
    parser.add_argument("inputs", nargs="+", help="输入文件/目录/通配符")
    parser.add_argument("--replace", action="append", default=[], help="替换规则：OLD=NEW，可重复传入")
    parser.add_argument("--rules-file", type=Path, default=None, help="规则文件，每行 OLD=NEW")
    parser.add_argument("--output-dir", type=Path, default=None, help="输出目录（默认 <原目录>_replaced）")
    parser.add_argument("--in-place", action="store_true", help="原地改写")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖输出文件")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写文件")
    args = parser.parse_args()

    if args.in_place and args.output_dir:
        raise SystemExit("--in-place 与 --output-dir 不能同时使用")

    rules = load_rules(args.replace, args.rules_file)
    if not rules:
        raise SystemExit("至少提供一条规则（--replace 或 --rules-file）")

    files = collect_files(args.inputs)
    if not files:
        raise SystemExit("未找到任何 .txt 文件")

    files_changed = 0
    total_repl = 0

    for i, path in enumerate(files, 1):
        out_path = resolve_output_path(path, args.output_dir, args.in_place)
        if out_path.exists() and not args.overwrite and out_path != path and not args.dry_run:
            print(f"[{i}/{len(files)}] SKIP exists: {out_path}")
            continue

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        yaml_lines, body_lines = split_front_matter(lines)

        changed = 0
        repl_count = 0

        for idx in find_yaml_translation_line_indices(yaml_lines):
            new_line, c = apply_rules(yaml_lines[idx], rules)
            if c > 0:
                yaml_lines[idx] = new_line
                changed += 1
                repl_count += c

        for idx in find_body_translation_line_indices(body_lines):
            new_line, c = apply_rules(body_lines[idx], rules)
            if c > 0:
                body_lines[idx] = new_line
                changed += 1
                repl_count += c

        if repl_count > 0:
            files_changed += 1
            total_repl += repl_count

        print(
            f"[{i}/{len(files)}] {path.name}: line_changed={changed}, repl={repl_count}"
            + (" (dry-run)" if args.dry_run else "")
        )

        if args.dry_run:
            continue

        out_lines = (yaml_lines + body_lines) if yaml_lines else body_lines
        out_text = "\n".join(out_lines) + "\n"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_text, encoding="utf-8")

    print(f"完成：files_changed={files_changed}/{len(files)}, replacements={total_repl}")


if __name__ == "__main__":
    main()
