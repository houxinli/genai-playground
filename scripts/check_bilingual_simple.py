#!/usr/bin/env python3
"""
bilingual_simple 模式的文件跳过检查脚本
专门针对 bilingual_simple 模式优化跳过逻辑
"""

import sys
from pathlib import Path
import json

def check_bilingual_simple_quality(file_path: Path) -> bool:
    """
    检查 bilingual_simple 模式生成的双语文件质量
    更严格的检查标准，适合 bilingual_simple 模式
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 1. 基本长度检查
        if len(content) < 200:  # bilingual_simple 模式应该有更长的内容
            return False
        
        # 2. 检查 bilingual_simple 特有的错误模式
        error_patterns = [
            "（以下省略）", "（省略）", "翻译失败", "无法翻译",
            "User:", "Assistant:",  # 不应该包含这些标记
            "思考中", "正在翻译", "请稍候",  # 不应该包含这些状态信息
            "ERROR", "FAILED", "EXCEPTION"  # 不应该包含错误信息
        ]
        
        for pattern in error_patterns:
            if pattern in content:
                return False
        
        # 3. 检查双语格式是否正确
        lines = content.split('\n')
        if len(lines) < 10:  # bilingual_simple 应该有足够的行数
            return False
        
        # 4. 检查是否包含日文和中文（双语特征）
        # 更宽泛的日文检测（包括平假名、片假名、汉字）
        def has_japanese_text(text):
            for char in text:
                # 平假名
                if 0x3040 <= ord(char) <= 0x309F:
                    return True
                # 片假名
                if 0x30A0 <= ord(char) <= 0x30FF:
                    return True
                # 日文汉字（部分重叠中文汉字）
                if 0x4E00 <= ord(char) <= 0x9FAF:
                    return True
            return False
        
        def has_chinese_text(text):
            for char in text:
                # 中文字符
                if 0x4E00 <= ord(char) <= 0x9FAF:
                    return True
            return False
        
        has_japanese = any(has_japanese_text(line) for line in lines)
        has_chinese = any(has_chinese_text(line) for line in lines)
        
        if not (has_japanese and has_chinese):
            return False
        
        # 5. 检查双语格式特征（日文行后跟中文行）
        bilingual_pairs = 0
        for i in range(len(lines) - 1):
            current_line = lines[i].strip()
            next_line = lines[i + 1].strip()
            
            # 如果当前行有日文，下一行有中文，且长度相近，认为是双语对
            if (has_japanese_text(current_line) and has_chinese_text(next_line) and 
                len(current_line) > 10 and len(next_line) > 10):
                bilingual_pairs += 1
        
        # 应该有足够的双语对
        if bilingual_pairs < 5:
            return False
        
        return True
        
    except Exception as e:
        print(f"检查文件质量时出错: {e}")
        return False

def natural_sort_key(filename):
    """自然排序键函数，正确处理数字"""
    import re
    # 将文件名分割为数字和非数字部分
    parts = re.split(r'(\d+)', filename)
    # 将数字部分转换为整数，非数字部分保持字符串
    return [int(part) if part.isdigit() else part for part in parts]

def analyze_directory(directory_path: str):
    """分析目录中的文件翻译状态"""
    dir_path = Path(directory_path)
    if not dir_path.exists():
        print(f"❌ 目录不存在: {directory_path}")
        return
    
    print(f"📁 分析目录: {directory_path}")
    print("=" * 60)
    
    # 统计信息
    total_files = 0
    skip_files = 0
    process_files = []
    
    # 查找所有 .txt 文件并按自然顺序排序
    txt_files = sorted(dir_path.glob("*.txt"), key=lambda x: natural_sort_key(x.name))
    
    for file_path in txt_files:
        name = file_path.name
        stem = file_path.stem
        
        # 跳过已处理的文件
        if name.endswith("_zh.txt"):
            print(f"⏭️  跳过已翻译文件: {name}")
            skip_files += 1
            continue
        
        if name.endswith("_bilingual.txt"):
            print(f"⏭️  跳过双语文件: {name}")
            skip_files += 1
            continue
        
        # 检查是否有对应的双语文件
        # 首先检查同目录下的双语文件
        bilingual_path = file_path.parent / f"{stem}_bilingual.txt"
        
        # 如果同目录没有，检查双语目录
        if not bilingual_path.exists():
            bilingual_dir = file_path.parent.parent / f"{file_path.parent.name}_bilingual"
            if bilingual_dir.exists():
                bilingual_path = bilingual_dir / f"{stem}.txt"
        
        if bilingual_path.exists():
            if check_bilingual_simple_quality(bilingual_path):
                print(f"✅ 跳过（高质量双语文件）: {name}")
                skip_files += 1
            else:
                print(f"🔄 重新翻译（低质量双语文件）: {name}")
                process_files.append(file_path)
                total_files += 1
        else:
            print(f"🆕 需要翻译: {name}")
            process_files.append(file_path)
            total_files += 1
    
    print("=" * 60)
    print(f"📊 统计结果:")
    print(f"   总文件数: {len(txt_files)}")
    print(f"   跳过文件数: {skip_files}")
    print(f"   需要翻译: {total_files}")
    print(f"   翻译进度: {skip_files}/{len(txt_files)} ({skip_files/len(txt_files)*100:.1f}%)")
    
    if process_files:
        print(f"\n📝 需要翻译的文件列表:")
        for i, file_path in enumerate(process_files, 1):
            print(f"   {i:2d}. {file_path.name}")

def main():
    if len(sys.argv) != 2:
        print("用法: python check_bilingual_simple.py <目录路径>")
        print("示例: python check_bilingual_simple.py tasks/translation/data/pixiv/50235390")
        sys.exit(1)
    
    directory_path = sys.argv[1]
    analyze_directory(directory_path)

if __name__ == "__main__":
    main()
