#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
from pathlib import Path
from typing import Tuple


def basic_quality_check(original_text: str, translated_text: str, bilingual: bool = True) -> Tuple[bool, str]:
    """轻量基础检测：
    - 非空
    - 长度比例 >= 20%
    - 错误模式排查
    - 日文比例阈值（bilingual模式下放宽到50%）
    - 末尾句子完整性（弱约束）
    """
    if not translated_text or not translated_text.strip():
        return False, "翻译结果为空"

    original_len = len(original_text.strip())
    translated_len = len(translated_text.strip())
    if original_len > 0 and translated_len < original_len * 0.2:
        return False, f"翻译结果太短: {translated_len}/{original_len} ({translated_len/max(1,original_len):.1%})"

    error_patterns = [
        r'（以下省略）', r'\[TO BE CONTINUED\]', r'\[\.\.\.\]', r'（此处省略', r'（注：',
        r'完整版请参考', r'由于文本长度限制', r'内容性质原因', r'仅展示部分', r'省略大量重复', r'最终段落', r'（翻译结束）',
        r'<think>', r'</think>',
    ]
    for pattern in error_patterns:
        if re.search(pattern, translated_text, flags=re.IGNORECASE):
            return False, f"包含错误模式: {pattern}"

    japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', translated_text))
    total_chars = max(1, len(translated_text))
    max_ratio = 0.5 if bilingual else 0.3
    if japanese_chars > total_chars * max_ratio:
        return False, f"包含过多日语原文: {japanese_chars}/{total_chars} ({japanese_chars/total_chars:.1%})"

    return True, "基础检测：翻译质量良好"


def main():
    ap = argparse.ArgumentParser(description="清理重复与低质量的 bilingual 文件")
    ap.add_argument("root", type=str, help="根目录，例如 tasks/translation/data/pixiv/50235390")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"目录不存在: {root}")
        return

    deleted_count = 0
    checked_count = 0
    kept_count = 0

    for path in root.rglob("*.txt"):
        name = path.name

        # 1) 删除 *_bilingual_bilingual.txt
        if name.endswith("_bilingual_bilingual.txt"):
            try:
                path.unlink()
                deleted_count += 1
                print(f"DELETE duplicate: {path}")
            except Exception as e:
                print(f"WARN 删除失败: {path} -> {e}")
            continue

        # 2) 对 *_bilingual.txt 做质量检测，不合格则删除
        if name.endswith("_bilingual.txt"):
            # 找原文：去掉尾部 "_bilingual" 后缀
            original_path = path.with_name(path.stem.replace("_bilingual", "") + ".txt")
            if not original_path.exists():
                # 找不到原文，跳过质量判断
                kept_count += 1
                print(f"SKIP no-original: {path}")
                continue
            try:
                original_text = original_path.read_text(encoding="utf-8", errors="ignore")
                translated_text = path.read_text(encoding="utf-8", errors="ignore")
                is_good, reason = basic_quality_check(original_text, translated_text, bilingual=True)
                checked_count += 1
                if is_good:
                    print(f"KEEP {path} ({reason})")
                    kept_count += 1
                else:
                    print(f"DELETE low-quality: {path} ({reason})")
                    path.unlink()
                    deleted_count += 1
            except Exception as e:
                print(f"WARN 质量检测失败: {path} -> {e}")
            continue

        # 3) *_zh.* 一律忽略
        if "_zh" in name:
            continue

        # 4) 原文：无 *_bilingual / *_awq_bilingual 后缀
        # 检查是否已有对应 bilingual，若有则跳过（不翻译）
        if name.endswith(".txt"):
            stem = path.stem
            bilingual_exist = (
                path.with_name(stem + "_bilingual.txt").exists() or
                path.with_name(stem + "_awq_bilingual.txt").exists()
            )
            if bilingual_exist:
                print(f"SKIP original (bilingual exists): {path}")
            # 这里只报告，不进行翻译
            continue

    print(f"\nSummary: deleted={deleted_count}, checked={checked_count}, kept={kept_count}")


if __name__ == "__main__":
    main()



