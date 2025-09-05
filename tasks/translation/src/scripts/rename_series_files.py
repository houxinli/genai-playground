#!/usr/bin/env python3
"""
重命名系列文件脚本
按照 {series_id}_{novel_id} 的命名规则重命名属于系列的文件
"""

import json
from pathlib import Path

def rename_series_files():
    """重命名系列文件"""
    base_dir = Path("tasks/translation/data/pixiv/50235390")
    index_file = base_dir / "index.json"
    
    # 读取index.json
    with open(index_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 获取系列信息
    by_series = data.get("_summary", {}).get("by_series", {})
    
    print("开始重命名系列文件...")
    
    for series_id, novel_ids in by_series.items():
        print(f"\n处理系列 {series_id}，包含 {len(novel_ids)} 篇文章:")
        
        for novel_id in novel_ids:
            # 查找所有相关文件
            old_files = list(base_dir.glob(f"{novel_id}.*"))
            
            for old_file in old_files:
                # 构建新文件名
                if old_file.suffix == ".txt":
                    new_name = f"{series_id}_{novel_id}.txt"
                elif old_file.suffix == "_zh.txt":
                    new_name = f"{series_id}_{novel_id}_zh.txt"
                else:
                    # 其他文件保持原样
                    continue
                
                new_file = base_dir / new_name
                
                if old_file.exists():
                    if new_file.exists():
                        print(f"  警告: {new_file.name} 已存在，跳过重命名 {old_file.name}")
                    else:
                        try:
                            old_file.rename(new_file)
                            print(f"  ✓ {old_file.name} -> {new_name}")
                        except Exception as e:
                            print(f"  ✗ 重命名失败 {old_file.name}: {e}")
                else:
                    print(f"  - 文件不存在: {old_file.name}")
    
    print("\n重命名完成!")

if __name__ == "__main__":
    rename_series_files()
