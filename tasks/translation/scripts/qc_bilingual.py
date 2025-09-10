#!/usr/bin/env python3
"""
单独处理bilingual文件的QC脚本
"""

import sys
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.quality_checker import QualityChecker
from src.core.config import TranslationConfig
from src.core.logger import UnifiedLogger

def parse_bilingual_file(file_path: str):
    """
    解析bilingual文件，提取原文和译文
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    original_lines = []
    translated_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 检查下一行是否是译文
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            
            # 判断是否为对照行
            is_pair = False
            
            # YAML字段对照
            if (line.startswith('title:') and next_line.startswith('title:') and line != next_line) or \
               (line.startswith('caption:') and next_line.startswith('caption:') and line != next_line) or \
               (line.startswith('tags:') and next_line.startswith('tags:') and line != next_line):
                is_pair = True
            
            # 对话对照
            elif (line.startswith('「') and next_line.startswith('「') and line != next_line):
                is_pair = True
            
            # 正文对照
            elif (line.startswith('　') and next_line.startswith('　') and line != next_line):
                is_pair = True
            
            if is_pair:
                original_lines.append(line)
                translated_lines.append(next_line)
                i += 2
            else:
                original_lines.append(line)
                translated_lines.append('')
                i += 1
        else:
            original_lines.append(line)
            translated_lines.append('')
            i += 1
    
    return original_lines, translated_lines

def main():
    if len(sys.argv) != 2:
        print("用法: python qc_bilingual.py <bilingual_file>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if not Path(file_path).exists():
        print(f"文件不存在: {file_path}")
        sys.exit(1)
    
    print(f"=== 处理bilingual文件: {file_path} ===")
    
    # 解析文件
    original_lines, translated_lines = parse_bilingual_file(file_path)
    
    print(f"解析结果:")
    print(f"  原文行数: {len(original_lines)}")
    print(f"  译文行数: {len(translated_lines)}")
    
    # 初始化QC
    config = TranslationConfig()
    config.bilingual_simple = True
    config.debug = True
    
    qc = QualityChecker(config, logger=None)
    
    # 测试行数对齐
    alignment_ok, alignment_reason = qc.check_line_alignment(original_lines, translated_lines)
    print(f"\n行数对齐检查:")
    print(f"  结果: {alignment_ok}")
    print(f"  原因: {alignment_reason}")
    
    # 测试基础QC
    original_text = '\n'.join(original_lines)
    translated_text = '\n'.join(translated_lines)
    basic_ok, basic_reason = qc.check_translation_quality_basic(original_text, translated_text)
    print(f"\n基础QC检查:")
    print(f"  结果: {basic_ok}")
    print(f"  原因: {basic_reason}")
    
    # 测试逐行规则QC
    verdicts, summary, conclusion = qc.check_translation_quality_rules_lines(original_text, translated_text, bilingual=True)
    print(f"\n逐行规则QC:")
    print(f"  判定数量: {len(verdicts)}")
    print(f"  GOOD行数: {verdicts.count('GOOD')}")
    print(f"  BAD行数: {verdicts.count('BAD')}")
    print(f"  摘要: {summary}")
    print(f"  结论: {conclusion}")
    
    # 显示BAD行
    if verdicts.count('BAD') > 0:
        print(f"\nBAD行详情:")
        for i, (orig, trans, verdict) in enumerate(zip(original_lines, translated_lines, verdicts)):
            if verdict == 'BAD':
                print(f"  第{i+1}行: {orig[:50]}... -> {trans[:50]}...")
    
    print(f"\n日志文件: 无（简化模式）")

if __name__ == "__main__":
    main()
