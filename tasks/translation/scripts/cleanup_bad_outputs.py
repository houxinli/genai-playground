#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
清理问题译文文件：
1) few-shot 泄漏样例内容
2) 译文大段直接复制原文（日文片段）

用法：
  python scripts/cleanup_bad_outputs.py --bilingual-dir tasks/translation/data/pixiv/50235390_bilingual --original-dir tasks/translation/data/pixiv/50235390
"""

import argparse
from pathlib import Path
import re


FEW_SHOT_LEAK_MARKERS = [
    "狭山，我喜欢你",
    "体育館裏",
    "体育馆后面",
    "余下的留到下次再说",
    "放課後、体育館裏",
]

KANA_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9D]')


def is_leak(text: str) -> bool:
    t = text
    for m in FEW_SHOT_LEAK_MARKERS:
        if m in t:
            return True
    return False


def count_copied_kana_lines(original_text: str, translated_text: str) -> int:
    """统计译文中和原文完全相同且包含假名的行数。"""
    if not original_text:
        return 0
    orig_set = set(ln.strip() for ln in original_text.splitlines() if ln.strip())
    cnt = 0
    for ln in translated_text.splitlines():
        s = ln.strip()
        if s and s in orig_set and KANA_RE.search(s):
            cnt += 1
    return cnt


def main() -> None:
    ap = argparse.ArgumentParser(description="删除few-shot泄漏或复制原文的bilingual输出文件")
    ap.add_argument("--bilingual-dir", required=True, help="双语输出目录，如 tasks/translation/data/pixiv/50235390_bilingual")
    ap.add_argument("--original-dir", required=True, help="原文目录，如 tasks/translation/data/pixiv/50235390")
    ap.add_argument("--copy-threshold", type=int, default=10, help="判定复制原文的行数阈值（含假名且完全相同）")
    args = ap.parse_args()

    bi_root = Path(args.bilingual_dir)
    orig_root = Path(args.original_dir)
    if not bi_root.exists():
        print(f"bilingual 目录不存在: {bi_root}")
        return
    if not orig_root.exists():
        print(f"original 目录不存在: {orig_root}")
        return

    checked = 0
    deleted = 0

    for p in bi_root.rglob("*.txt"):
        try:
            checked += 1
            bi_text = p.read_text(encoding="utf-8", errors="ignore")
            # few-shot 泄漏检测
            leak = is_leak(bi_text)

            # 映射原文路径（去掉 _bilingual 后缀）
            stem = p.stem
            if stem.endswith("_bilingual"):
                orig_name = stem[:-10] + ".txt"
            else:
                orig_name = stem + ".txt"
            orig_path = orig_root / orig_name
            orig_text = ""
            if orig_path.exists():
                orig_text = orig_path.read_text(encoding="utf-8", errors="ignore")

            # 复制原文（日文）检测
            copy_cnt = count_copied_kana_lines(orig_text, bi_text) if orig_text else 0

            if leak or copy_cnt >= args.copy_threshold:
                try:
                    p.unlink()
                    deleted += 1
                    print(f"DELETE {p} (leak={leak}, copy_cnt={copy_cnt})")
                except Exception as e:
                    print(f"WARN 删除失败 {p}: {e}")
        except Exception as e:
            print(f"WARN 处理失败 {p}: {e}")

    print(f"Summary: checked={checked}, deleted={deleted}")


if __name__ == "__main__":
    main()


