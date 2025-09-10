#!/usr/bin/env python3
"""
列出待翻译文件并按长度排序
"""

import sys
from pathlib import Path
import argparse

def get_file_length(file_path: Path) -> int:
    """获取文件长度（字符数）"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return len(content)
    except Exception as e:
        print(f"读取文件失败 {file_path}: {e}")
        return 0

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

def analyze_directory(directory_path: str):
    """分析目录中的文件"""
    dir_path = Path(directory_path)
    
    if not dir_path.exists():
        print(f"❌ 目录不存在: {directory_path}")
        return
    
    print(f"📁 分析目录: {directory_path}")
    print("=" * 60)
    
    # 查找所有txt文件
    txt_files = sorted(dir_path.glob("*.txt"), key=lambda x: x.name)
    
    files_to_translate = []
    
    for file_path in txt_files:
        # 检查是否已有高质量双语文件
        bilingual_path_same_dir = file_path.parent / f"{file_path.stem}_bilingual.txt"
        bilingual_path_bilingual_dir = file_path.parent.parent / f"{file_path.parent.name}_bilingual" / f"{file_path.stem}.txt"
        
        has_high_quality = False
        
        # 检查同目录下的bilingual文件
        if bilingual_path_same_dir.exists():
            if check_bilingual_simple_quality(bilingual_path_same_dir):
                has_high_quality = True
        
        # 检查_bilingual目录下的文件
        if bilingual_path_bilingual_dir.exists():
            if check_bilingual_simple_quality(bilingual_path_bilingual_dir):
                has_high_quality = True
        
        if not has_high_quality:
            # 获取文件长度
            length = get_file_length(file_path)
            files_to_translate.append((file_path.name, length))
    
    # 按长度排序（从长到短）
    files_to_translate.sort(key=lambda x: x[1], reverse=True)
    
    print(f"📊 需要翻译的文件（按长度排序，从长到短）:")
    print(f"   总文件数: {len(files_to_translate)}")
    print("=" * 60)
    
    for i, (filename, length) in enumerate(files_to_translate, 1):
        print(f"{i:2d}. {filename:<40} ({length:,} 字符)")
    
    print("=" * 60)
    
    # 计算总字符数
    total_chars = sum(length for _, length in files_to_translate)
    print(f"📈 总字符数: {total_chars:,}")
    print(f"📈 平均长度: {total_chars // len(files_to_translate) if files_to_translate else 0:,} 字符")

def main():
    parser = argparse.ArgumentParser(description="列出待翻译文件并按长度排序")
    parser.add_argument("directory", help="要分析的目录路径")
    
    args = parser.parse_args()
    analyze_directory(args.directory)

if __name__ == "__main__":
    main()

