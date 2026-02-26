#!/usr/bin/env python3
"""
发现 rules 文件中尚未覆盖的角色名候选（基于原文敬称 + 双语对齐）。

输出：
- 文本草案（可人工补到 rules）
- JSON 详情（含文件命中和中文候选分布）
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


# 原文中常见“名字 + 敬称”
# 仅允许单一脚本 token，避免把“そう言って如月”这种混合短语吞进去
JP_HONORIFIC_RE = re.compile(
    r"(?<![ぁ-んァ-ヶ一-龥々ー])([ァ-ヶー]{2,8}|[一-龥々]{2,4}|[ぁ-んー]{2,5})(?:くん|君|ちゃん|さん|様|先輩|先生|殿)"
)
HIRAGANA_ONLY_RE = re.compile(r"^[ぁ-んー]{2,5}$")
KATAKANA_ONLY_RE = re.compile(r"^[ァ-ヶー]{2,8}$")
KANJI_ONLY_RE = re.compile(r"^[一-龥々]{2,4}$")

# 译文侧优先抓带中文称呼的人名
CN_HONORIFIC_RE = re.compile(r"([\u4E00-\u9FFF]{2,6})(?:君|酱|醬|小姐|同学|老师|老師|先生)")
# 兜底：被边界包围的短中文 token（较噪）
CN_BOUNDED_RE = re.compile(r"(?<![\u4E00-\u9FFF])([\u4E00-\u9FFF]{2,4})(?![\u4E00-\u9FFF])")

JP_STOPWORDS = {
    "お姉",
    "姉",
    "お兄",
    "兄",
    "弟",
    "お母",
    "母",
    "お父",
    "父",
    "彼",
    "彼女",
    "旦那",
    "先生",
    "大家",
    "皆",
    "貴方",
    "ご主人",
    "オタク",
    "ボク",
    "たく",
    "そんな",
    "その",
    "ほら",
    "お疲れ",
    "無",
    "異",
    "おにー",
    "乳魔",
    "童貞",
    "教頭",
    "催眠",
    "淫魔",
    "女優",
    "スタッフ",
    "妊婦",
    "義兄",
    "旦那",
}

CN_STOPWORDS = {
    "我们",
    "你们",
    "她们",
    "他们",
    "现在",
    "然后",
    "因为",
    "所以",
    "这个",
    "那个",
    "这里",
    "那里",
    "乳房",
    "阴茎",
    "精液",
    "高潮",
    "快感",
    "同学",
    "老师",
}

CN_BAD_CHARS = set("我的你他她它在了就和与给把被让啊呀哦嘛吧呢这那")

CN_PREFIX_NOISE = [
    "如果",
    "向",
    "从",
    "对",
    "比",
    "但",
    "但是",
    "而",
    "并",
    "在",
    "让",
    "叫",
    "给",
    "把",
    "被",
    "和",
    "与",
]
CN_SUFFIX_NOISE = [
    "一边",
    "同",
    "先",
]


def parse_rules_known_names(rules_file: Path) -> set[str]:
    known: set[str] = set()
    for lineno, raw in enumerate(rules_file.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(" #", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(f"规则格式错误（仅支持 JP=CN 或 JP=CN|a,b）: {rules_file}:{lineno}: {raw}")
        jp, _ = line.split("=", 1)
        jp = jp.strip()
        if jp:
            known.add(jp)
    return known


def is_valid_jp_candidate(token: str) -> bool:
    if not token:
        return False
    if not (HIRAGANA_ONLY_RE.match(token) or KATAKANA_ONLY_RE.match(token) or KANJI_ONLY_RE.match(token)):
        return False
    if token in JP_STOPWORDS:
        return False
    if len(token) < 2:
        return False
    if token.endswith(("の", "に", "で", "て", "が", "を", "は", "も", "と", "か", "や")):
        return False
    # 全平假名时更严格一点，降低把普通词当名字的概率
    if HIRAGANA_ONLY_RE.match(token) and len(token) < 3:
        return False
    return True


def iter_bilingual_pairs(lines: List[str]) -> Iterable[Tuple[str, str]]:
    idx = 0
    while idx < len(lines):
        if not lines[idx].strip():
            idx += 1
            continue
        if idx + 1 >= len(lines):
            break
        yield lines[idx], lines[idx + 1]
        idx += 2


def normalize_cn(token: str) -> str:
    token = token.strip()
    changed = True
    while changed and len(token) >= 2:
        changed = False
        for p in CN_PREFIX_NOISE:
            if token.startswith(p) and len(token) - len(p) >= 2:
                token = token[len(p):]
                changed = True
                break
        if changed:
            continue
        for s in CN_SUFFIX_NOISE:
            if token.endswith(s) and len(token) - len(s) >= 2:
                token = token[:-len(s)]
                changed = True
                break
    return token


def is_valid_cn_candidate(token: str) -> bool:
    if not token:
        return False
    if len(token) < 2 or len(token) > 5:
        return False
    if token in CN_STOPWORDS:
        return False
    if any(ch in CN_BAD_CHARS for ch in token):
        return False
    return all("\u4e00" <= ch <= "\u9fff" for ch in token)


def collect_unknown_jp_candidates(
    original_dir: Path,
    known_names: set[str],
    min_mentions: int,
    min_mentions_hiragana: int,
) -> Tuple[Counter[str], Dict[str, set[str]]]:
    mentions: Counter[str] = Counter()
    files_hit: Dict[str, set[str]] = defaultdict(set)

    for path in sorted(original_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in JP_HONORIFIC_RE.finditer(text):
            jp = m.group(1)
            if jp in known_names:
                continue
            if not is_valid_jp_candidate(jp):
                continue
            mentions[jp] += 1
            files_hit[jp].add(path.name)

    # 先做 mentions 过滤，后续只处理更可信的候选
    filtered: Dict[str, int] = {}
    for jp, c in mentions.items():
        if HIRAGANA_ONLY_RE.match(jp):
            if c < max(1, min_mentions_hiragana):
                continue
        elif c < max(1, min_mentions):
            continue
        filtered[jp] = c
    mentions = Counter(filtered)
    files_hit = {jp: files for jp, files in files_hit.items() if jp in mentions}
    return mentions, files_hit


def collect_cn_suggestions(
    bilingual_dir: Path,
    jp_candidates: set[str],
) -> Dict[str, Counter[str]]:
    out: Dict[str, Counter[str]] = defaultdict(Counter)
    if not jp_candidates:
        return out

    for path in sorted(bilingual_dir.glob("*.txt")):
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for original, translated in iter_bilingual_pairs(lines):
            # 同行只出现一个候选名时再统计，避免交叉污染
            present = [jp for jp in jp_candidates if jp in original]
            if len(present) != 1:
                continue
            jp = present[0]

            cn_tokens = [normalize_cn(m.group(1)) for m in CN_HONORIFIC_RE.finditer(translated)]
            if not cn_tokens:
                cn_tokens = [normalize_cn(m.group(1)) for m in CN_BOUNDED_RE.finditer(translated)]
            for token in cn_tokens:
                if is_valid_cn_candidate(token):
                    out[jp][token] += 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="发现未纳入 rules 的角色名候选")
    parser.add_argument("original_dir", type=Path, help="原文目录（如 fanbox/momizi813）")
    parser.add_argument("bilingual_dir", type=Path, help="双语目录（如 fanbox/momizi813_bilingual_v2）")
    parser.add_argument("--rules-file", type=Path, required=True, help="现有 rules 文件（JP=CN 或 JP=CN|a,b）")
    parser.add_argument("--min-mentions", type=int, default=2, help="最小原文命中次数")
    parser.add_argument("--min-mentions-hiragana", type=int, default=5, help="平假名候选最小命中次数")
    parser.add_argument("--report-json", type=Path, required=True, help="输出 JSON 报告")
    parser.add_argument("--draft-file", type=Path, required=True, help="输出文本草案")
    args = parser.parse_args()

    known = parse_rules_known_names(args.rules_file)
    mentions, files_hit = collect_unknown_jp_candidates(
        args.original_dir,
        known,
        args.min_mentions,
        args.min_mentions_hiragana,
    )
    cn_suggestions = collect_cn_suggestions(args.bilingual_dir, set(mentions))

    rows = []
    for jp, c in mentions.most_common():
        cn_top = cn_suggestions.get(jp, Counter()).most_common(8)
        rows.append(
            {
                "jp": jp,
                "mentions": c,
                "files": len(files_hit.get(jp, set())),
                "cn_candidates": [{"token": t, "count": n} for t, n in cn_top],
                "files_hit": sorted(files_hit.get(jp, set())),
            }
        )

    report = {
        "original_dir": str(args.original_dir),
        "bilingual_dir": str(args.bilingual_dir),
        "rules_file": str(args.rules_file),
        "known_name_count": len(known),
        "unknown_name_count": len(rows),
        "rows": rows,
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    draft_lines = [
        "# 未纳入 rules 的角色候选（人工确认后追加）",
        "# 目标格式: JP=标准中文|别名1,别名2",
    ]
    for row in rows:
        jp = row["jp"]
        mentions = row["mentions"]
        files = row["files"]
        cn_part = ""
        if row["cn_candidates"]:
            cn_part = ", ".join(f"{x['token']}({x['count']})" for x in row["cn_candidates"])
        draft_lines.append(f"{jp}=<待定>  # mentions={mentions} files={files} cn={cn_part}")

    args.draft_file.parent.mkdir(parents=True, exist_ok=True)
    args.draft_file.write_text("\n".join(draft_lines) + "\n", encoding="utf-8")

    print(f"unknown_name_count={len(rows)}")
    print(f"report={args.report_json}")
    print(f"draft={args.draft_file}")


if __name__ == "__main__":
    main()
