#!/usr/bin/env python3
"""
审计双语文件中“已配置日文名”的残留中文变体，输出可人工确认的补充 alias 候选。

输入：
- bilingual_dir: 双语目录（原文/译文交替行）
- rules_file: 单文件规则（JP=CN 或 JP=CN|alias1,alias2）

输出：
- JSON 明细
- 文本草案（可复制到 rules 文件）
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


# 优先抓带称呼的人名（精度高）
CN_WITH_HONORIFIC_RE = re.compile(r"([\u4E00-\u9FFF]{2,5})(?:君|酱|醬|小姐|同学|老師|老师|先生)")
# 兜底：被标点/空白包围的短中文 token（精度中）
CN_BOUNDED_RE = re.compile(r"(?<![\u4E00-\u9FFF])([\u4E00-\u9FFF]{2,4})(?![\u4E00-\u9FFF])")

CN_NOISE = {
    "我们",
    "你们",
    "她们",
    "他们",
    "这个",
    "那个",
    "现在",
    "然后",
    "因为",
    "所以",
    "少女",
    "学校",
    "老师",
    "同学",
    "快感",
    "高潮",
    "精液",
    "乳房",
    "阴茎",
    "因为",
    "如果",
    "然后",
    "于是",
    "不过",
    "但是",
    "这个",
    "那个",
    "这里",
    "那里",
    "一边",
    "瞬间",
}

LEADING_NOISE = set("这那此因所与及并而但又把被在于从向对跟给让令使就都也还")
TRAILING_NOISE = set("的了着过吧呀啊呢嘛哇哦喔吗和与并且而且等们们儿")


def parse_rules_file(path: Path) -> Tuple[Dict[str, str], Dict[str, set[str]]]:
    canonical: Dict[str, str] = {}
    aliases: Dict[str, set[str]] = defaultdict(set)
    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(" #", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(f"规则格式错误（仅支持 JP=CN 或 JP=CN|a,b）: {path}:{lineno}: {raw}")
        jp, rhs = line.split("=", 1)
        jp = jp.strip()
        rhs = rhs.strip()
        if not jp or not rhs:
            raise ValueError(f"规则格式错误（左右不能为空）: {path}:{lineno}: {raw}")
        if "|" in rhs:
            cn, alias_raw = rhs.split("|", 1)
            canonical[jp] = cn.strip()
            for a in alias_raw.split(","):
                a = a.strip()
                if a:
                    aliases[jp].add(a)
        else:
            canonical[jp] = rhs
    return canonical, aliases


def iter_pairs(lines: List[str]) -> Iterable[Tuple[str, str]]:
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        if i + 1 >= len(lines):
            break
        yield lines[i], lines[i + 1]
        i += 2


def normalize_cn_token(token: str) -> str:
    token = token.strip()
    while token and token[0] in LEADING_NOISE:
        token = token[1:]
    while token and token[-1] in TRAILING_NOISE:
        token = token[:-1]
    return token


def looks_like_name(token: str) -> bool:
    if len(token) < 2 or len(token) > 4:
        return False
    if token in CN_NOISE:
        return False
    # 避免全是功能字
    bad_chars = set("我的你他她它在了就和与给把被让啊呀哦嘛吧呢")
    if any(ch in bad_chars for ch in token):
        return False
    return True


def collect_file_candidates(
    path: Path,
    jp_names: List[str],
    canonical: Dict[str, str],
    aliases: Dict[str, set[str]],
) -> Dict[str, Counter[str]]:
    out: Dict[str, Counter[str]] = defaultdict(Counter)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for orig, trans in iter_pairs(lines):
        present = [jp for jp in jp_names if jp in orig]
        if not present:
            continue
        # 同行出现多个日文名时，中文侧很容易交叉污染，审计阶段直接跳过以提高精度
        if len(present) != 1:
            continue
        tokens = [normalize_cn_token(m.group(1)) for m in CN_WITH_HONORIFIC_RE.finditer(trans)]
        if not tokens:
            tokens = [normalize_cn_token(m.group(1)) for m in CN_BOUNDED_RE.finditer(trans)]
        tokens = [t for t in tokens if looks_like_name(t)]
        if not tokens:
            continue
        for jp in present:
            can = canonical[jp]
            known = aliases.get(jp, set())
            for token in tokens:
                if token == can or token in known:
                    continue
                out[jp][token] += 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="审计双语文件中的残留人名变体")
    parser.add_argument("bilingual_dir", type=Path, help="双语目录")
    parser.add_argument("--rules-file", type=Path, required=True, help="规则文件（JP=CN 或 JP=CN|alias）")
    parser.add_argument("--min-count", type=int, default=2, help="候选最小命中次数")
    parser.add_argument("--report-json", type=Path, required=True, help="输出 JSON 报告")
    parser.add_argument("--draft-file", type=Path, required=True, help="输出规则补充草案（文本）")
    args = parser.parse_args()

    canonical, aliases = parse_rules_file(args.rules_file)
    jp_names = sorted(canonical)
    files = sorted(args.bilingual_dir.glob("*.txt"))

    agg: Dict[str, Counter[str]] = defaultdict(Counter)
    per_file: Dict[str, Dict[str, Dict[str, int]]] = {}

    for p in files:
        cands = collect_file_candidates(p, jp_names, canonical, aliases)
        if cands:
            per_file[p.name] = {jp: dict(cnt) for jp, cnt in cands.items() if cnt}
        for jp, cnt in cands.items():
            agg[jp].update(cnt)

    suggestions: List[Tuple[str, str, int]] = []
    for jp in sorted(agg):
        for token, n in agg[jp].most_common():
            if n >= max(1, args.min_count):
                suggestions.append((jp, token, n))

    report = {
        "bilingual_dir": str(args.bilingual_dir),
        "rules_file": str(args.rules_file),
        "min_count": args.min_count,
        "total_files": len(files),
        "files_with_candidates": len(per_file),
        "suggestions": [
            {"jp": jp, "token": token, "count": n}
            for jp, token, n in suggestions
        ],
        "per_file": per_file,
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    draft_lines = [
        "# 规则补充候选（人工确认后再写入 rules）",
        "# 格式建议：JP=标准名|... ,<新增别名>",
    ]
    grouped: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    for jp, token, n in suggestions:
        grouped[jp].append((token, n))
    for jp in sorted(grouped):
        can = canonical.get(jp, "")
        tokens = ",".join(f"{t}({n})" for t, n in grouped[jp])
        draft_lines.append(f"{jp}={can}  # candidates: {tokens}")

    args.draft_file.parent.mkdir(parents=True, exist_ok=True)
    args.draft_file.write_text("\n".join(draft_lines) + "\n", encoding="utf-8")

    print(f"files_with_candidates={len(per_file)}/{len(files)}")
    print(f"suggestions={len(suggestions)}")
    print(f"report={args.report_json}")
    print(f"draft={args.draft_file}")


if __name__ == "__main__":
    main()
