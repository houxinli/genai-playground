#!/usr/bin/env python3
"""
基于“日文名 -> 中文标准名”映射，批量统一双语文件中的人名译法。

设计目标：
- 仅修改正文译文行，不改原文行。
- 按原文行里的人名位置，对齐到译文里的候选中文名字后再替换，避免全局误伤。
- 支持 dry-run、批量目录、输出报告（便于扩展到整库）。
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


JP_NAME_RE = re.compile(r"[\u30A1-\u30FF]{2,}")
CN_TOKEN_RE = re.compile(r"[\u4E00-\u9FFF]{1,3}(?:君|酱|醬)?")
CN_SUFFIX_RE = re.compile(r"(君|酱|醬)$")

# 过滤明显不是人名的日文片段（常见名词/拟声）
JP_BLOCKLIST = {
    "クラス",
    "ペニス",
    "チンポ",
    "ブラジャー",
    "カップ",
    "デカブラ",
    "ルール",
    "チャンス",
    "プライド",
    "スイカ",
    "バカ",
    "ビク",
    "ザコ",
    "マゾザコ",
    "カリ",
    "アレ",
    "アピール",
    "ハンデ",
    "カウントダウン",
    "ゼロ",
    "カメラ",
    "キモ",
    "パイズリ",
    "ドン",
    "ホック",
    "ピンチ",
}

CN_STOPWORDS = {
    "我们",
    "你们",
    "她们",
    "他们",
    "少女",
    "少女们",
    "男生",
    "女生",
    "同学",
    "老师",
    "学校",
    "乳房",
    "胸部",
    "阴茎",
    "精液",
    "快感",
    "高潮",
    "胜利",
    "规则",
    "机会",
    "身体",
    "过程",
    "照片",
    "这场",
    "这个",
    "那个",
    "这样",
    "现在",
    "开始",
    "然后",
    "因为",
    "所以",
    "一刻",
    "瞬间",
}

PUNCT_LEFT = set("「『《〈（([\"' \t\r\n，。！？：；、,.!?…♡—─-")
PUNCT_RIGHT = set("」』）》〉）)]\"' \t\r\n，。！？：；、,.!?…♡—─-")
LEFT_PARTICLES = set("把将向对與与和给让令使被从在叫是名那这该由朝跟同帮替为比及了")
RIGHT_PARTICLES = set("的在将就正仍被向对與与和从令使让把给了著着过嘛呢吧啊哦呀喔哇啦")
LEADING_NOISE = set("把将向对與与和给让令使被从在叫是名那这该由朝跟同帮替为比及了就并还都又才可会能要")
TRAILING_NOISE = set("的在将就正仍被向对與与和从令使让把给了著着过嘛呢吧啊哦呀喔哇啦是会能要可还都又并才")


@dataclass(frozen=True)
class NameHit:
    base: str
    suffix: str
    base_start: int
    base_end: int
    token_start: int
    token_end: int

    @property
    def center(self) -> float:
        return (self.base_start + self.base_end - 1) / 2.0


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
    return sorted(set(files))


def split_front_matter(lines: List[str]) -> Tuple[List[str], List[str]]:
    if not lines or lines[0].strip() != "---":
        return [], lines
    idx = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if len(idx) < 2:
        return [], lines
    end = idx[1]
    return lines[: end + 1], lines[end + 1 :]


def normalize_jp_name(name: str) -> str:
    # 去掉常见敬称后缀（片假名写法）
    return re.sub(r"(?:クン|チャン|サン|センパイ|センセイ)$", "", name)


def extract_jp_occurrences(line: str, target_names: Sequence[str]) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for name in target_names:
        for m in re.finditer(re.escape(name), line):
            out.append((m.start(), name))
    out.sort(key=lambda x: x[0])
    return out


def _left_ok(line: str, start: int) -> bool:
    if start <= 0:
        return True
    ch = line[start - 1]
    return ch in PUNCT_LEFT or ch in LEFT_PARTICLES


def _right_ok(line: str, end: int) -> bool:
    if end >= len(line):
        return True
    ch = line[end]
    return ch in PUNCT_RIGHT or ch in RIGHT_PARTICLES


def extract_cn_hits(line: str) -> List[NameHit]:
    hits: List[NameHit] = []
    for m in CN_TOKEN_RE.finditer(line):
        token = m.group(0)
        suffix_m = CN_SUFFIX_RE.search(token)
        suffix = suffix_m.group(1) if suffix_m else ""
        base = token[: -len(suffix)] if suffix else token
        base_start = m.start()
        base_end = base_start + len(base)
        while base and base[0] in LEADING_NOISE:
            base = base[1:]
            base_start += 1
        while base and base[-1] in TRAILING_NOISE:
            base = base[:-1]
            base_end -= 1
        if len(base) < 1 or len(base) > 4:
            continue
        if base in CN_STOPWORDS:
            continue
        if not _left_ok(line, base_start):
            continue
        if not _right_ok(line, base_end):
            continue
        hit = NameHit(
            base=base,
            suffix=suffix,
            base_start=base_start,
            base_end=base_end,
            token_start=m.start(),
            token_end=m.end(),
        )
        hits.append(hit)
    return hits


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(
                prev[j] + 1,      # delete
                curr[j - 1] + 1,  # insert
                prev[j - 1] + cost,  # replace
            ))
        prev = curr
    return prev[-1]


def align_hits(
    jp_occurrences: List[Tuple[int, str]],
    cn_hits: List[NameHit],
    original_line: str,
    translated_line: str,
    canonical_map: Dict[str, str],
    max_distance: int,
) -> List[Tuple[str, NameHit]]:
    if not jp_occurrences or not cn_hits:
        return []

    aligned: List[Tuple[str, NameHit]] = []
    # 情况1：数量相同，按顺序对齐，最稳定
    if len(jp_occurrences) == len(cn_hits):
        for (_, jp_name), hit in zip(jp_occurrences, cn_hits):
            aligned.append((jp_name, hit))
        return aligned

    # 情况2：数量不同，用相对位置（ratio）找最近候选
    used: set[int] = set()
    olen = max(1, len(original_line) - 1)
    tlen = max(1, len(translated_line) - 1)
    for o_start, jp_name in jp_occurrences:
        target = (o_start / olen) * tlen
        canonical = canonical_map.get(jp_name)
        best_idx = None
        best_score = float("inf")
        for idx, hit in enumerate(cn_hits):
            if idx in used:
                continue
            pos_score = abs(hit.center - target)
            if canonical:
                dist = edit_distance(hit.base, canonical)
                if dist > max_distance:
                    continue
                score = pos_score + (dist * 100.0)
            else:
                score = pos_score
            if score < best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None:
            used.add(best_idx)
            aligned.append((jp_name, cn_hits[best_idx]))
    return aligned


def resolve_output_path(input_path: Path, output_dir: Path | None, in_place: bool) -> Path:
    if in_place:
        return input_path
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / input_path.name
    out_dir = input_path.parent.with_name(f"{input_path.parent.name}_namefix")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / input_path.name


def parse_name_rule(raw: str) -> Tuple[str, str]:
    if "=" not in raw:
        raise ValueError(f"人名映射格式错误（缺少=）：{raw}")
    jp, cn = raw.split("=", 1)
    jp = jp.strip()
    cn = cn.strip()
    if not jp or not cn:
        raise ValueError(f"人名映射格式错误（左右不能为空）：{raw}")
    return normalize_jp_name(jp), cn


def load_name_map(name_map_args: Sequence[str], name_map_file: Path | None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in name_map_args:
        jp, cn = parse_name_rule(raw)
        out[jp] = cn
    if name_map_file:
        for raw in name_map_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            jp, cn = parse_name_rule(line)
            out[jp] = cn
    return out


def parse_alias_rule(raw: str) -> Tuple[str, List[str]]:
    if ":" not in raw:
        raise ValueError(f"别名映射格式错误（缺少:）：{raw}")
    jp, aliases_raw = raw.split(":", 1)
    jp = normalize_jp_name(jp.strip())
    aliases = [x.strip() for x in aliases_raw.split(",") if x.strip()]
    if not jp or not aliases:
        raise ValueError(f"别名映射格式错误（左右不能为空）：{raw}")
    return jp, aliases


def parse_compact_rule(raw: str) -> Tuple[str, str, List[str]]:
    # 支持：日文=标准名|别名1,别名2
    # 以及：日文=标准名
    if "=" not in raw:
        raise ValueError(f"规则格式错误（缺少=）：{raw}")
    jp, rhs = raw.split("=", 1)
    jp = normalize_jp_name(jp.strip())
    rhs = rhs.strip()
    if not jp or not rhs:
        raise ValueError(f"规则格式错误（左右不能为空）：{raw}")

    if "|" in rhs:
        cn, aliases_raw = rhs.split("|", 1)
        aliases = [x.strip() for x in aliases_raw.split(",") if x.strip()]
    else:
        cn = rhs
        aliases = []
    cn = cn.strip()
    if not cn:
        raise ValueError(f"规则格式错误（标准名不能为空）：{raw}")
    return jp, cn, aliases


def load_alias_map(alias_args: Sequence[str], alias_file: Path | None) -> Dict[str, set[str]]:
    out: Dict[str, set[str]] = defaultdict(set)
    for raw in alias_args:
        jp, aliases = parse_alias_rule(raw)
        out[jp].update(aliases)
    if alias_file:
        for raw in alias_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            jp, aliases = parse_alias_rule(line)
            out[jp].update(aliases)
    return out


def _clean_rule_line(raw: str) -> str:
    line = raw.strip()
    if not line or line.startswith("#") or line == "---":
        return ""
    # 允许行尾注释：<rule>  # comment
    line = line.split(" #", 1)[0].strip()
    return line


def load_rules_file(rules_file: Path | None) -> Tuple[Dict[str, str], Dict[str, set[str]]]:
    name_map: Dict[str, str] = {}
    alias_map: Dict[str, set[str]] = defaultdict(set)
    if not rules_file:
        return name_map, alias_map

    for lineno, raw in enumerate(rules_file.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        line = _clean_rule_line(raw)
        if not line:
            continue
        if "=" in line:
            jp, cn, aliases = parse_compact_rule(line)
            name_map[jp] = cn
            if aliases:
                alias_map[jp].update(aliases)
            continue
        raise ValueError(
            "规则格式错误（仅支持 '日文=标准名|别名1,别名2' 或 '日文=标准名'）: "
            f"{rules_file}:{lineno}: {raw}"
        )

    return name_map, alias_map


def auto_collect_jp_names(lines: List[str], min_occurrence: int = 2) -> List[str]:
    names: Counter[str] = Counter()
    for line in lines:
        for m in JP_NAME_RE.finditer(line):
            n = normalize_jp_name(m.group(0))
            if len(n) < 2 or n in JP_BLOCKLIST:
                continue
            names[n] += 1
    return [n for n, c in names.most_common() if c >= max(1, min_occurrence)]


def infer_canonical(
    counters: Dict[str, Counter[str]],
    first_seen: Dict[str, str],
    strategy: str,
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for jp, cnt in counters.items():
        if not cnt:
            continue
        if strategy == "most":
            out[jp] = cnt.most_common(1)[0][0]
        else:
            # first
            if jp in first_seen:
                out[jp] = first_seen[jp]
            else:
                out[jp] = cnt.most_common(1)[0][0]
    return out


def is_safe_auto_alias(token: str, canonical: str) -> bool:
    """Return whether an inferred alias is safe enough for automatic replacement."""
    if not token or token == canonical:
        return False
    # Avoid deleting grammar by treating "高尾却" or "夏奈带" as aliases for "高尾"/"夏奈".
    if canonical and canonical in token:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="按日文名映射统一双语文件中的中文人名")
    parser.add_argument("inputs", nargs="+", help="输入文件/目录/通配符")
    parser.add_argument("--name-map", action="append", default=[], help="人名映射：日文=中文，可重复")
    parser.add_argument("--name-map-file", type=Path, default=None, help="人名映射文件（每行 日文=中文）")
    parser.add_argument("--alias", action="append", default=[], help="显式别名：日文:别名1,别名2")
    parser.add_argument("--alias-file", type=Path, default=None, help="显式别名文件（每行 日文:别名1,别名2）")
    parser.add_argument(
        "--rules-file",
        type=Path,
        default=None,
        help="合并规则文件（同一文件内支持：日文=中文 和 日文:别名1,别名2）",
    )
    parser.add_argument(
        "--auto-canonical",
        choices=["off", "first", "most"],
        default="off",
        help="映射缺失时自动推断标准名：first=首次命中，most=最高频，off=不自动推断",
    )
    parser.add_argument("--min-support", type=int, default=1, help="候选别名最小命中次数（默认1）")
    parser.add_argument("--max-distance", type=int, default=1, help="候选名与标准名的最大编辑距离（默认1）")
    parser.add_argument("--no-auto-alias", action="store_true", help="禁用自动别名推断，仅使用 --alias/--alias-file")
    parser.add_argument("--output-dir", type=Path, default=None, help="输出目录（默认 <原目录>_namefix）")
    parser.add_argument("--in-place", action="store_true", help="原地改写")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖输出文件")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写文件")
    parser.add_argument("--global-alias", action="store_true", help="忽略原文行是否出现日文名，直接全局替换别名")
    parser.add_argument("--report-file", type=Path, default=None, help="输出 JSON 报告（可选）")
    args = parser.parse_args()

    if args.in_place and args.output_dir:
        raise SystemExit("--in-place 与 --output-dir 不能同时使用")

    files = collect_files(args.inputs)
    if not files:
        raise SystemExit("未找到任何 .txt 文件")

    configured_map = load_name_map(args.name_map, args.name_map_file)
    explicit_alias_map = load_alias_map(args.alias, args.alias_file)
    rule_names, rule_aliases = load_rules_file(args.rules_file)
    configured_map.update(rule_names)
    for jp, aliases in rule_aliases.items():
        explicit_alias_map[jp].update(aliases)
    global_report: Dict[str, object] = {
        "files": [],
        "total_files": len(files),
        "files_changed": 0,
        "total_replacements": 0,
    }

    for i, path in enumerate(files, 1):
        out_path = resolve_output_path(path, args.output_dir, args.in_place)
        if out_path.exists() and not args.overwrite and out_path != path and not args.dry_run:
            print(f"[{i}/{len(files)}] SKIP exists: {out_path}")
            continue

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        _, body_lines = split_front_matter(lines)
        # 如果无 front matter，直接全量作为正文处理
        process_lines = body_lines if body_lines else lines

        jp_name_pool = auto_collect_jp_names(process_lines)
        # 仅保留在池子里的映射，避免误触
        name_map = {k: v for k, v in configured_map.items() if k in jp_name_pool}
        target_names = sorted(set(jp_name_pool) | set(name_map.keys()))

        pair_indices: List[Tuple[int, int]] = []
        idx = 0
        while idx < len(process_lines):
            if not process_lines[idx].strip():
                idx += 1
                continue
            if idx + 1 < len(process_lines):
                pair_indices.append((idx, idx + 1))
                idx += 2
            else:
                idx += 1

        counters: Dict[str, Counter[str]] = defaultdict(Counter)
        first_seen: Dict[str, str] = {}
        line_alignments: Dict[int, List[Tuple[str, NameHit]]] = {}

        # Pass 1: 统计候选
        for orig_i, trans_i in pair_indices:
            original = process_lines[orig_i]
            translated = process_lines[trans_i]
            jp_occ = extract_jp_occurrences(original, target_names)
            if not jp_occ:
                continue
            cn_hits = extract_cn_hits(translated)
            aligned = align_hits(jp_occ, cn_hits, original, translated, name_map, args.max_distance)
            if not aligned:
                continue
            line_alignments[trans_i] = aligned
            for jp_name, hit in aligned:
                counters[jp_name][hit.base] += 1
                if jp_name not in first_seen:
                    first_seen[jp_name] = hit.base

        if args.auto_canonical != "off":
            inferred = infer_canonical(counters, first_seen, args.auto_canonical)
            for jp_name, cn_name in inferred.items():
                name_map.setdefault(jp_name, cn_name)

        aliases: Dict[str, set[str]] = {}
        for jp_name, cnt in counters.items():
            canonical = name_map.get(jp_name)
            if not canonical:
                continue
            bucket: set[str] = set()
            if not args.no_auto_alias:
                bucket = {
                    token
                    for token, c in cnt.items()
                    if is_safe_auto_alias(token, canonical)
                    and c >= max(1, args.min_support)
                    and edit_distance(token, canonical) <= max(0, args.max_distance)
                }
            bucket.update(explicit_alias_map.get(jp_name, set()))
            bucket.discard(canonical)
            aliases[jp_name] = bucket

        # Pass 2: 应用替换
        # 策略：当原文行包含某个日文名时，在对应译文行中对该名别名做全量替换。
        # 这样比“单点对齐替换”更适合批量清理同名多译。
        changed_lines = 0
        replacement_count = 0
        new_lines = process_lines[:]

        for orig_i, trans_i in pair_indices:
            original = process_lines[orig_i]
            line = new_lines[trans_i]
            if args.global_alias:
                jp_present = set(name_map.keys())
            else:
                jp_present = {name for _, name in extract_jp_occurrences(original, target_names)}
            line_repl = 0
            for jp_name in sorted(jp_present):
                canonical = name_map.get(jp_name)
                if not canonical:
                    continue
                alias_list = sorted(aliases.get(jp_name, set()), key=len, reverse=True)
                for alias in alias_list:
                    if not alias or alias == canonical:
                        continue
                    n = line.count(alias)
                    if n <= 0:
                        continue
                    line = line.replace(alias, canonical)
                    line_repl += n
            if line_repl > 0:
                changed_lines += 1
                replacement_count += line_repl
                new_lines[trans_i] = line

        file_changed = changed_lines > 0
        if file_changed:
            global_report["files_changed"] = int(global_report["files_changed"]) + 1
            global_report["total_replacements"] = int(global_report["total_replacements"]) + replacement_count

        file_report = {
            "file": str(path),
            "changed_lines": changed_lines,
            "replacements": replacement_count,
            "name_map": name_map,
            "aliases": {k: sorted(v) for k, v in aliases.items() if v},
            "candidate_counts": {k: dict(v) for k, v in counters.items() if v},
        }
        global_report["files"].append(file_report)

        print(
            f"[{i}/{len(files)}] {path.name}: changed_lines={changed_lines}, replacements={replacement_count}"
            + (" (dry-run)" if args.dry_run else "")
        )

        if args.dry_run:
            continue

        out_lines = new_lines if body_lines else new_lines
        if body_lines:
            # 原文件有 front matter，保留原样头部
            front, _ = split_front_matter(lines)
            out_lines = front + new_lines

        out_text = "\n".join(out_lines) + "\n"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_text, encoding="utf-8")

    print(
        f"完成：files_changed={global_report['files_changed']}/{global_report['total_files']}, "
        f"replacements={global_report['total_replacements']}"
    )

    if args.report_file:
        args.report_file.parent.mkdir(parents=True, exist_ok=True)
        args.report_file.write_text(
            json.dumps(global_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"报告已写入: {args.report_file}")


if __name__ == "__main__":
    main()
