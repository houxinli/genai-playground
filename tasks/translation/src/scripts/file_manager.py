#!/usr/bin/env python3
"""
文件管理脚本
整合了下载、重命名、清理等功能
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

def rename_series_files(base_dir: Path, dry_run: bool = False) -> bool:
    """
    重命名系列文件
    按照 {series_id}_{novel_id} 的命名规则重命名属于系列的文件
    """
    index_file = base_dir / "index.json"
    
    if not index_file.exists():
        print(f"错误: 找不到 index.json 文件: {index_file}")
        return False
    
    try:
        # 读取index.json
        with open(index_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"错误: 读取 index.json 失败: {e}")
        return False
    
    # 获取系列信息
    by_series = data.get("_summary", {}).get("by_series", {})
    
    if not by_series:
        print("警告: 没有找到系列信息")
        return True
    
    print("开始重命名系列文件...")
    if dry_run:
        print("(试运行模式，不会实际重命名文件)")
    
    success_count = 0
    total_count = 0
    
    for series_id, novel_ids in by_series.items():
        print(f"\n处理系列 {series_id}，包含 {len(novel_ids)} 篇文章:")
        
        for novel_id in novel_ids:
            # 查找所有相关文件
            old_files = list(base_dir.glob(f"{novel_id}.*"))
            
            for old_file in old_files:
                total_count += 1
                
                # 构建新文件名
                if old_file.suffix == ".txt":
                    new_name = f"{series_id}_{novel_id}.txt"
                elif old_file.suffix == "_zh.txt":
                    new_name = f"{series_id}_{novel_id}_zh.txt"
                elif old_file.suffix == "_bilingual.txt":
                    new_name = f"{series_id}_{novel_id}_bilingual.txt"
                else:
                    # 其他文件保持原样
                    continue
                
                new_file = base_dir / new_name
                
                if old_file.exists():
                    if new_file.exists():
                        print(f"  警告: {new_file.name} 已存在，跳过重命名 {old_file.name}")
                    else:
                        if dry_run:
                            print(f"  [试运行] {old_file.name} -> {new_name}")
                        else:
                            try:
                                old_file.rename(new_file)
                                print(f"  ✓ {old_file.name} -> {new_name}")
                                success_count += 1
                            except Exception as e:
                                print(f"  ✗ 重命名失败 {old_file.name}: {e}")
                else:
                    print(f"  - 文件不存在: {old_file.name}")
    
    print(f"\n重命名完成! 成功: {success_count}/{total_count}")
    return True


def list_files_by_length(base_dir: Path, pattern: str = "*.txt", reverse: bool = True) -> List[tuple]:
    """
    列出文件并按长度排序
    """
    files = list(base_dir.rglob(pattern))
    file_lengths = []
    
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            length = len(content)
            file_lengths.append((file_path, length))
        except Exception as e:
            print(f"读取文件失败 {file_path}: {e}")
            file_lengths.append((file_path, 0))
    
    # 按长度排序
    file_lengths.sort(key=lambda x: x[1], reverse=reverse)
    return file_lengths


def check_bilingual_quality(file_path: Path) -> bool:
    """
    检查双语文件质量（专门针对bilingual_simple模式优化）
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
        def has_japanese_text(text):
            for char in text:
                # 平假名
                if 0x3040 <= ord(char) <= 0x309F:
                    return True
                # 片假名
                if 0x30A0 <= ord(char) <= 0x30FF:
                    return True
                # 汉字（日文常用汉字范围）
                if 0x4E00 <= ord(char) <= 0x9FAF:
                    return True
            return False
        
        def has_chinese_text(text):
            for char in text:
                # 中文字符
                if 0x4E00 <= ord(char) <= 0x9FAF:
                    return True
            return False
        
        # 检查是否同时包含日文和中文
        has_jp = has_japanese_text(content)
        has_cn = has_chinese_text(content)
        
        if not (has_jp and has_cn):
            return False
        
        # 5. 检查双语对的数量
        bilingual_pairs = 0
        for i in range(len(lines) - 1):
            if lines[i].strip() and lines[i + 1].strip():
                # 简单检查：如果连续两行都有内容，可能是双语对
                bilingual_pairs += 1
        
        # 至少应该有10对双语内容
        if bilingual_pairs < 10:
            return False
        
        return True
        
    except Exception as e:
        print(f"检查文件质量失败 {file_path}: {e}")
        return False


def cleanup_low_quality_files(base_dir: Path, dry_run: bool = False) -> bool:
    """
    清理低质量的双语文件
    """
    print("开始清理低质量文件...")
    if dry_run:
        print("(试运行模式，不会实际删除文件)")
    
    bilingual_files = list(base_dir.rglob("*_bilingual.txt"))
    low_quality_files = []
    
    for file_path in bilingual_files:
        if not check_bilingual_quality(file_path):
            low_quality_files.append(file_path)
            print(f"低质量文件: {file_path}")
    
    if not low_quality_files:
        print("没有发现低质量文件")
        return True
    
    print(f"\n发现 {len(low_quality_files)} 个低质量文件")
    
    if not dry_run:
        confirm = input("确认删除这些文件吗? (y/N): ")
        if confirm.lower() == 'y':
            for file_path in low_quality_files:
                try:
                    file_path.unlink()
                    print(f"已删除: {file_path}")
                except Exception as e:
                    print(f"删除失败 {file_path}: {e}")
        else:
            print("取消删除操作")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="文件管理工具")
    parser.add_argument("command", choices=["rename", "list", "cleanup"], 
                       help="命令: rename=重命名系列文件, list=列出文件, cleanup=清理低质量文件")
    parser.add_argument("--dir", type=str, default="tasks/translation/data/pixiv/50235390",
                       help="目标目录路径")
    parser.add_argument("--pattern", type=str, default="*.txt",
                       help="文件匹配模式 (仅用于list命令)")
    parser.add_argument("--reverse", action="store_true", default=True,
                       help="按长度降序排列 (仅用于list命令)")
    parser.add_argument("--dry-run", action="store_true",
                       help="试运行模式，不实际执行操作")
    parser.add_argument("--limit", type=int, default=0,
                       help="限制显示/处理文件数量 (0=无限制)")
    
    args = parser.parse_args()
    
    base_dir = Path(args.dir)
    if not base_dir.exists():
        print(f"错误: 目录不存在: {base_dir}")
        sys.exit(1)
    
    if args.command == "rename":
        success = rename_series_files(base_dir, args.dry_run)
        sys.exit(0 if success else 1)
    
    elif args.command == "list":
        files = list_files_by_length(base_dir, args.pattern, args.reverse)
        
        if args.limit > 0:
            files = files[:args.limit]
        
        print(f"\n文件列表 (按长度{'降序' if args.reverse else '升序'}排列):")
        print("-" * 80)
        for file_path, length in files:
            print(f"{length:8d} 字符  {file_path}")
        
        print(f"\n总计: {len(files)} 个文件")
    
    elif args.command == "cleanup":
        success = cleanup_low_quality_files(base_dir, args.dry_run)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
