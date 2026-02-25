#!/usr/bin/env python3
"""
批量将双语文件中的译文行标准化为简体中文。

默认 backend 为 opencc（确定性转换）。
若本地没有 opencc，可使用 --backend llm 走 OpenRouter/OpenAI 进行批量字符级转换。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

from openai import OpenAI


RE_HAN = re.compile(r"[\u3400-\u9fff]")
RE_KANA = re.compile(r"[\u3040-\u30ff]")
RE_KEY_LINE = re.compile(r"^(\s*)([A-Za-z_.-]+):\s*(.*)$")

PLACEHOLDERS = {"[翻译未完成]", "[翻译失败]"}
TRANSLATABLE_KEYS = {"title", "caption", "excerpt", "tags"}


def collect_files(inputs: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_file():
            files.append(path.resolve())
            continue
        if path.is_dir():
            files.extend(sorted(p.resolve() for p in path.glob("*.txt")))
            continue
        for matched in glob.glob(raw):
            mpath = Path(matched).expanduser()
            if mpath.is_file():
                files.append(mpath.resolve())
    uniq = sorted(set(files))
    return uniq


def split_front_matter(lines: List[str]) -> Tuple[List[str], List[str]]:
    if not lines:
        return [], []
    if lines[0].strip() != "---":
        return [], lines
    markers = [idx for idx, line in enumerate(lines) if line.strip() == "---"]
    if len(markers) < 2:
        return [], lines
    end = markers[1]
    return lines[: end + 1], lines[end + 1 :]


def find_yaml_translation_line_indices(yaml_lines: List[str]) -> List[int]:
    indices: List[int] = []
    if len(yaml_lines) < 3:
        return indices

    for i in range(1, len(yaml_lines) - 1):
        m1 = RE_KEY_LINE.match(yaml_lines[i])
        m2 = RE_KEY_LINE.match(yaml_lines[i + 1])
        if not m1 or not m2:
            continue
        indent1, key1, _ = m1.groups()
        indent2, key2, _ = m2.groups()
        if indent1 == indent2 and key1 == key2 and key1 in TRANSLATABLE_KEYS:
            indices.append(i + 1)
    return indices


def find_body_translation_line_indices(body_lines: List[str]) -> List[int]:
    indices: List[int] = []
    i = 0
    total = len(body_lines)
    while i < total:
        original = body_lines[i]
        if not original.strip():
            i += 1
            continue
        if i + 1 < total:
            indices.append(i + 1)
            i += 2
        else:
            i += 1
    return indices


def should_convert_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped or stripped in PLACEHOLDERS:
        return False
    if not RE_HAN.search(stripped):
        return False
    # 仅做繁转简，不处理含假名的行（这类通常属于修复/重译问题）
    if RE_KANA.search(stripped):
        return False
    return True


@dataclass
class LineTarget:
    section: str  # "yaml" | "body"
    index: int
    original: str


class BaseConverter:
    def convert_lines(self, lines: Sequence[str]) -> List[str]:
        raise NotImplementedError


class OpenCCConverter(BaseConverter):
    def __init__(self) -> None:
        self._py_converter = None
        self._opencc_bin = None
        try:
            from opencc import OpenCC

            self._py_converter = OpenCC("t2s")
        except ImportError as exc:
            self._opencc_bin = shutil.which("opencc")
            if not self._opencc_bin:
                raise RuntimeError(
                    "未找到 opencc。请安装 opencc-python-reimplemented（Python 包）"
                    "或安装 opencc 命令行（如 `brew install opencc`），"
                    "或改用 --backend llm。"
                ) from exc

    def convert_lines(self, lines: Sequence[str]) -> List[str]:
        if self._py_converter is not None:
            return [self._py_converter.convert(line) for line in lines]

        assert self._opencc_bin is not None
        payload = "\n".join(lines)
        proc = subprocess.run(
            [self._opencc_bin, "-c", "t2s.json"],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"opencc CLI 转换失败: rc={proc.returncode}, stderr={proc.stderr.strip()}"
            )
        converted = proc.stdout.splitlines()
        if len(converted) == len(lines):
            return converted

        # 兜底：极少数情况下按行切分数不一致，退化为逐行调用保证对齐安全。
        safe_lines: List[str] = []
        for line in lines:
            one = subprocess.run(
                [self._opencc_bin, "-c", "t2s.json"],
                input=line,
                text=True,
                capture_output=True,
                check=False,
            )
            if one.returncode != 0:
                raise RuntimeError(
                    f"opencc CLI 转换失败: rc={one.returncode}, stderr={one.stderr.strip()}"
                )
            safe_lines.append(one.stdout.rstrip("\n"))
        return safe_lines


class LLMConverter(BaseConverter):
    def __init__(
        self,
        model: str,
        llm_provider: str,
        llm_base_url: str | None,
        llm_api_key: str | None,
        batch_size: int = 40,
    ) -> None:
        provider = (llm_provider or "openrouter").lower()
        api_key = llm_api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("LLM backend 需要 API key（OPENROUTER_API_KEY/OPENAI_API_KEY）。")

        if llm_base_url:
            base_url = llm_base_url
        elif provider == "openrouter":
            base_url = "https://openrouter.ai/api/v1"
        else:
            base_url = None

        headers = None
        if provider == "openrouter":
            headers = {
                "HTTP-Referer": "https://github.com/houxinli/genai-playground",
                "X-Title": "Simplified Normalizer",
            }

        self.model = model
        self.batch_size = max(1, int(batch_size))
        self.client = OpenAI(base_url=base_url, api_key=api_key, default_headers=headers, timeout=60)

    def convert_lines(self, lines: Sequence[str]) -> List[str]:
        out: List[str] = []
        for i in range(0, len(lines), self.batch_size):
            chunk = list(lines[i : i + self.batch_size])
            out.extend(self._convert_chunk(chunk))
        return out

    def _convert_chunk(self, lines: List[str]) -> List[str]:
        payload = json.dumps(lines, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是文本标准化工具。只做繁体中文->简体中文的字符转换。"
                    "禁止改写语义、禁止增删内容、禁止替换标点与空格。"
                    "输出必须是 JSON 数组，长度与输入完全一致。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请把下面 JSON 数组中的每个字符串转换为简体中文。"
                    "仅转换字形，不改动其它内容。只返回 JSON 数组：\n"
                    f"{payload}"
                ),
            },
        ]
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            stream=False,
        )
        text = (resp.choices[0].message.content or "").strip()
        converted = self._extract_json_array(text)
        if len(converted) != len(lines):
            raise RuntimeError(f"LLM 返回行数不匹配：期望 {len(lines)}，实际 {len(converted)}")
        return converted

    @staticmethod
    def _extract_json_array(text: str) -> List[str]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)

        start = cleaned.find("[")
        if start < 0:
            raise RuntimeError("LLM 返回中未找到 JSON 数组。")
        decoder = json.JSONDecoder()
        arr, _ = decoder.raw_decode(cleaned[start:])
        if not isinstance(arr, list):
            raise RuntimeError("LLM 返回不是 JSON 数组。")
        return [str(item) for item in arr]


def build_targets(yaml_lines: List[str], body_lines: List[str]) -> List[LineTarget]:
    targets: List[LineTarget] = []
    for idx in find_yaml_translation_line_indices(yaml_lines):
        line = yaml_lines[idx]
        if should_convert_line(line):
            targets.append(LineTarget(section="yaml", index=idx, original=line))
    for idx in find_body_translation_line_indices(body_lines):
        line = body_lines[idx]
        if should_convert_line(line):
            targets.append(LineTarget(section="body", index=idx, original=line))
    return targets


def resolve_output_path(input_path: Path, output_dir: Path | None, in_place: bool) -> Path:
    if in_place:
        return input_path
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / input_path.name
    default_dir = input_path.parent.with_name(f"{input_path.parent.name}_simp")
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir / input_path.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量将双语文件译文行统一为简体中文")
    parser.add_argument("inputs", nargs="+", help="输入文件/目录/通配符")
    parser.add_argument("--backend", choices=["opencc", "llm"], default="opencc", help="转换后端")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="输出目录（默认生成 <原目录>_simp/同名文件）",
    )
    parser.add_argument("--in-place", action="store_true", help="原地覆盖输入文件")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已存在输出文件")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写文件")

    # LLM backend options
    parser.add_argument("--model", default="x-ai/grok-4.1-fast", help="LLM 模型名（仅 llm backend）")
    parser.add_argument("--llm-provider", choices=["openrouter", "openai"], default="openrouter")
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--batch-size", type=int, default=40, help="llm backend 每批行数")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = collect_files(args.inputs)
    if not files:
        raise SystemExit("未找到任何 .txt 文件。")
    if args.in_place and args.output_dir:
        raise SystemExit("--in-place 与 --output-dir 不能同时使用。")

    if args.backend == "opencc":
        converter: BaseConverter = OpenCCConverter()
    else:
        converter = LLMConverter(
            model=args.model,
            llm_provider=args.llm_provider,
            llm_base_url=args.llm_base_url,
            llm_api_key=args.llm_api_key,
            batch_size=args.batch_size,
        )

    total_changed_lines = 0
    changed_files = 0

    for i, path in enumerate(files, 1):
        output_path = resolve_output_path(path, args.output_dir, args.in_place)
        if output_path.exists() and not args.overwrite and output_path != path and not args.dry_run:
            print(f"[{i}/{len(files)}] SKIP exists: {output_path}")
            continue

        content = path.read_text(encoding="utf-8", errors="ignore")
        all_lines = content.splitlines()
        yaml_lines, body_lines = split_front_matter(all_lines)
        targets = build_targets(yaml_lines, body_lines)

        if not targets:
            if not args.dry_run and output_path != path:
                output_path.write_text(content, encoding="utf-8")
            print(f"[{i}/{len(files)}] {path.name}: no convertible lines")
            continue

        source_lines = [t.original for t in targets]
        converted_lines = converter.convert_lines(source_lines)

        changed = 0
        for target, converted in zip(targets, converted_lines):
            if converted != target.original:
                changed += 1
                if target.section == "yaml":
                    yaml_lines[target.index] = converted
                else:
                    body_lines[target.index] = converted

        total_changed_lines += changed
        if changed > 0:
            changed_files += 1

        print(
            f"[{i}/{len(files)}] {path.name}: targets={len(targets)} changed={changed}"
            + (" (dry-run)" if args.dry_run else "")
        )

        if args.dry_run:
            continue

        out_lines = (yaml_lines + body_lines) if yaml_lines else body_lines
        out_text = "\n".join(out_lines) + "\n"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(out_text, encoding="utf-8")

    print(f"完成：files_changed={changed_files}/{len(files)}, lines_changed={total_changed_lines}")


if __name__ == "__main__":
    main()
