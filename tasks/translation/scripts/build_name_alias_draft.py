#!/usr/bin/env python3
"""
从 normalize_bilingual_names.py 的 JSON 报告中聚合候选，生成：
1) 已有人名映射的 alias 草案（可直接用于 --alias-file）
2) 新人名候选草案（待人工确认后加入 --name-map-file）
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


JP_NAME_RE = re.compile(r"^[\u30A1-\u30FFー]{2,8}$")
JP_HONORIFIC_RE = re.compile(
    r"([ぁ-んァ-ヶー]{2,8})(?:くん|君|ちゃん|チャン|さん|サン|様|先輩|センパイ)"
)

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
    "オタク",
    "ボク",
    "オニー",
    "スタッフ",
    "モデル",
    "ディルド",
    "ツンデレ",
    "グラビアアイドル",
    "ローション",
    "ワン",
    "シー",
    "エス",
    "リキャラメスガキ",
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

CN_BAD_CHARS = set("我你他她它们的了在把被让给和与就都又并才要会能可这那啊呀哦嘛吧呢")

SMALL_KANA = set("ァィゥェォャュョッヮー")


def parse_name_rule(raw: str) -> Tuple[str, str]:
    if "=" not in raw:
        raise ValueError(f"人名映射格式错误（缺少=）：{raw}")
    jp, cn = raw.split("=", 1)
    jp = jp.strip()
    cn = cn.strip()
    if not jp or not cn:
        raise ValueError(f"人名映射格式错误（左右不能为空）：{raw}")
    return jp, cn


def parse_alias_rule(raw: str) -> Tuple[str, List[str]]:
    if ":" not in raw:
        raise ValueError(f"别名映射格式错误（缺少:）：{raw}")
    jp, aliases_raw = raw.split(":", 1)
    jp = jp.strip()
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
    jp = jp.strip()
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


def load_name_map(path: Path | None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path or not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        jp, cn = parse_name_rule(line)
        out[jp] = cn
    return out


def load_alias_map(path: Path | None) -> Dict[str, set[str]]:
    out: Dict[str, set[str]] = defaultdict(set)
    if not path or not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
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
    line = line.split(" #", 1)[0].strip()
    return line


def load_rules_file(path: Path | None) -> Tuple[Dict[str, str], Dict[str, set[str]]]:
    name_map: Dict[str, str] = {}
    alias_map: Dict[str, set[str]] = defaultdict(set)
    if not path or not path.exists():
        return name_map, alias_map

    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
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
            f"{path}:{lineno}: {raw}"
        )

    return name_map, alias_map


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
            curr.append(
                min(
                    prev[j] + 1,
                    curr[j - 1] + 1,
                    prev[j - 1] + cost,
                )
            )
        prev = curr
    return prev[-1]


def is_jp_name_like(jp: str) -> bool:
    if not JP_NAME_RE.match(jp):
        return False
    if jp in JP_BLOCKLIST:
        return False
    if all(ch in SMALL_KANA for ch in jp):
        return False
    return True


def is_cn_candidate(cn: str) -> bool:
    if not cn:
        return False
    if len(cn) < 2:
        return False
    if len(cn) > 4:
        return False
    if cn in CN_STOPWORDS:
        return False
    if any(ch in CN_BAD_CHARS for ch in cn):
        return False
    return all("\u4e00" <= ch <= "\u9fff" for ch in cn)


def aggregate_counts(report_json: Path) -> Tuple[Dict[str, Counter[str]], Dict[str, set[str]]]:
    obj = json.loads(report_json.read_text(encoding="utf-8"))
    agg: Dict[str, Counter[str]] = defaultdict(Counter)
    files_hit: Dict[str, set[str]] = defaultdict(set)

    for file_item in obj.get("files", []):
        file_name = Path(file_item.get("file", "")).name
        for jp, cn_counts in file_item.get("candidate_counts", {}).items():
            if not isinstance(cn_counts, dict):
                continue
            for cn, c in cn_counts.items():
                if not isinstance(c, int):
                    continue
                agg[jp][cn] += c
                files_hit[jp].add(file_name)
    return agg, files_hit


def extract_likely_names_from_source(source_dir: Path) -> Counter[str]:
    out: Counter[str] = Counter()
    for path in sorted(source_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in JP_HONORIFIC_RE.finditer(text):
            base = m.group(1)
            if not JP_NAME_RE.match(base):
                continue
            if base in JP_BLOCKLIST:
                continue
            out[base] += 1
    return out


def build_alias_lines(
    name_map: Dict[str, str],
    existing_aliases: Dict[str, set[str]],
    agg: Dict[str, Counter[str]],
    min_alias_support: int,
    max_alias_distance: int,
) -> List[str]:
    lines: List[str] = []
    for jp in sorted(name_map):
        canonical = name_map[jp]
        discovered: set[str] = set()
        for cn, count in agg.get(jp, Counter()).most_common():
            if not is_cn_candidate(cn):
                continue
            if cn == canonical:
                continue
            if count < max(1, min_alias_support):
                continue
            if edit_distance(cn, canonical) > max(0, max_alias_distance):
                continue
            discovered.add(cn)

        merged = sorted(set(existing_aliases.get(jp, set())) | discovered)
        if not merged:
            continue
        lines.append(f"{jp}:{','.join(merged)}")
    return lines


def build_name_candidates(
    agg: Dict[str, Counter[str]],
    files_hit: Dict[str, set[str]],
    name_map: Dict[str, str],
    allowed_names: set[str] | None,
    candidate_min_total: int,
    candidate_min_top: int,
    candidate_min_files: int,
    candidate_min_ratio: float,
    candidate_alias_support: int,
    candidate_max_alias_distance: int,
) -> List[str]:
    rows: List[Tuple[int, str, str, int, int, float, List[str]]] = []
    for jp, raw_counter in agg.items():
        if jp in name_map:
            continue
        if allowed_names is not None and jp not in allowed_names:
            continue
        if not is_jp_name_like(jp):
            continue

        counter = Counter({cn: n for cn, n in raw_counter.items() if is_cn_candidate(cn)})
        if not counter:
            continue

        total = sum(counter.values())
        if total < candidate_min_total:
            continue

        file_count = len(files_hit.get(jp, set()))
        if file_count < candidate_min_files:
            continue

        ordered = counter.most_common()
        top_cn, top_count = ordered[0]
        second_count = ordered[1][1] if len(ordered) > 1 else 0
        ratio = math.inf if second_count == 0 else top_count / second_count
        if top_count < candidate_min_top or ratio < candidate_min_ratio:
            continue

        aliases: List[str] = []
        for cn, count in ordered[1:]:
            if count < candidate_alias_support:
                continue
            if edit_distance(cn, top_cn) > max(0, candidate_max_alias_distance):
                continue
            aliases.append(cn)

        rows.append((total, jp, top_cn, file_count, top_count, ratio, aliases))

    rows.sort(key=lambda x: (x[0], x[4]), reverse=True)

    out: List[str] = []
    for total, jp, top_cn, file_count, top_count, ratio, aliases in rows:
        suffix = f"# total={total} files={file_count} top={top_count} ratio={ratio:.2f}"
        if aliases:
            suffix += f" aliases={','.join(aliases)}"
        out.append(f"{jp}={top_cn}  {suffix}")
    return out


def write_lines(path: Path, header_lines: Sequence[str], body_lines: Iterable[str]) -> None:
    content_lines = list(header_lines) + list(body_lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(content_lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="从 name scan 报告聚合 alias 草案和新人名候选")
    parser.add_argument("report_json", type=Path, help="normalize_bilingual_names.py 生成的 JSON 报告")
    parser.add_argument("--rules-file", type=Path, default=None, help="合并规则文件（同一文件内支持 = 与 :）")
    parser.add_argument("--name-map-file", type=Path, default=None, help="已确认人名映射文件（日文=中文）")
    parser.add_argument("--alias-file", type=Path, default=None, help="现有别名文件（可选）")
    parser.add_argument("--output-alias-file", type=Path, required=True, help="输出 alias 草案文件")
    parser.add_argument("--output-candidate-file", type=Path, default=None, help="输出新人名候选草案（可选）")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="原文目录（可选）：用于用敬称模式过滤出更像人名的日文词",
    )
    parser.add_argument("--min-alias-support", type=int, default=1, help="已确认名字的 alias 最小命中次数")
    parser.add_argument("--max-alias-distance", type=int, default=1, help="已确认名字 alias 的最大编辑距离")
    parser.add_argument("--candidate-min-total", type=int, default=6, help="新人名候选总命中阈值")
    parser.add_argument("--candidate-min-top", type=int, default=3, help="新人名候选 top 命中阈值")
    parser.add_argument("--candidate-min-files", type=int, default=1, help="新人名候选最少出现文件数")
    parser.add_argument("--candidate-min-name-hits", type=int, default=2, help="敬称命中最小次数（需配合 --source-dir）")
    parser.add_argument("--candidate-min-ratio", type=float, default=2.0, help="新人名候选 top/second 比值阈值")
    parser.add_argument("--candidate-alias-support", type=int, default=2, help="新人名候选 alias 最小命中次数")
    parser.add_argument(
        "--candidate-max-alias-distance",
        type=int,
        default=1,
        help="新人名候选 alias 的最大编辑距离",
    )
    args = parser.parse_args()

    if not args.rules_file and not args.name_map_file:
        raise SystemExit("至少提供 --rules-file 或 --name-map-file")

    name_map = load_name_map(args.name_map_file)
    existing_aliases = load_alias_map(args.alias_file)
    rule_names, rule_aliases = load_rules_file(args.rules_file)
    name_map.update(rule_names)
    for jp, aliases in rule_aliases.items():
        existing_aliases[jp].update(aliases)
    agg, files_hit = aggregate_counts(args.report_json)
    likely_name_hits = extract_likely_names_from_source(args.source_dir) if args.source_dir else Counter()
    allowed_names = None
    if args.source_dir:
        allowed_names = {
            jp
            for jp, c in likely_name_hits.items()
            if c >= max(1, args.candidate_min_name_hits)
        }

    alias_lines = build_alias_lines(
        name_map=name_map,
        existing_aliases=existing_aliases,
        agg=agg,
        min_alias_support=args.min_alias_support,
        max_alias_distance=args.max_alias_distance,
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_lines(
        args.output_alias_file,
        header_lines=[
            "# 自动生成（可手工修改）",
            "# 格式: 日文名:别名1,别名2",
            f"# generated_at: {now}",
            f"# source_report: {args.report_json}",
        ],
        body_lines=alias_lines,
    )

    candidate_count = 0
    if args.output_candidate_file:
        candidate_lines = build_name_candidates(
            agg=agg,
            files_hit=files_hit,
            name_map=name_map,
            allowed_names=allowed_names,
            candidate_min_total=args.candidate_min_total,
            candidate_min_top=args.candidate_min_top,
            candidate_min_files=args.candidate_min_files,
            candidate_min_ratio=args.candidate_min_ratio,
            candidate_alias_support=args.candidate_alias_support,
            candidate_max_alias_distance=args.candidate_max_alias_distance,
        )

        if allowed_names is not None:
            covered = {line.split("=", 1)[0].strip() for line in candidate_lines if "=" in line}
            unresolved = sorted(
                jp
                for jp in allowed_names
                if jp not in name_map and jp not in covered
            )
            if unresolved:
                candidate_lines.append("# --- 以下是仅由原文敬称命中得到、尚未自动推断出中文标准名的候选 ---")
                for jp in unresolved:
                    candidate_lines.append(f"{jp}=<待确认>  # source_hits={likely_name_hits.get(jp, 0)}")

        candidate_count = len(candidate_lines)
        write_lines(
            args.output_candidate_file,
            header_lines=[
                "# 自动扫描候选（待人工确认）",
                "# 格式: 日文名=建议中文",
                f"# generated_at: {now}",
                f"# source_report: {args.report_json}",
                f"# source_dir: {args.source_dir}" if args.source_dir else "# source_dir: <none>",
            ],
            body_lines=candidate_lines,
        )

    print(f"alias_draft_written={args.output_alias_file} entries={len(alias_lines)}")
    if args.output_candidate_file:
        print(f"name_candidates_written={args.output_candidate_file} entries={candidate_count}")
    if args.source_dir:
        print(f"likely_name_pool_from_source={len(allowed_names or set())}")


if __name__ == "__main__":
    main()
