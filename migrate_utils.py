#!/usr/bin/env python3
"""
Utils重构迁移脚本
用于更新现有代码中的导入语句
"""

import os
import re
from pathlib import Path


def update_imports_in_file(file_path: Path) -> bool:
    """
    更新文件中的导入语句
    
    Args:
        file_path: 文件路径
        
    Returns:
        是否有更新
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # 更新旧的utils导入
        old_imports = [
            r'from utils import',
            r'from \.\.utils import',
            r'from \.\.\.utils import',
        ]
        
        new_imports = [
            'from ..utils import',
            'from ..utils import', 
            'from ...utils import',
        ]
        
        for old_pattern, new_pattern in zip(old_imports, new_imports):
            content = re.sub(old_pattern, new_pattern, content)
        
        # 更新具体的函数导入
        function_mappings = {
            'parse_yaml_front_matter': 'from ..utils.file import parse_yaml_front_matter',
            'clean_filename': 'from ..utils.file import clean_filename',
            'split_text_into_chunks': 'from ..utils.text import split_text_into_chunks',
            'estimate_tokens': 'from ..utils.text import estimate_tokens',
            'create_bilingual_output': 'from ..utils.format import create_bilingual_output',
        }
        
        for func_name, new_import in function_mappings.items():
            # 查找使用该函数的地方
            if func_name in content and f'from ..utils import {func_name}' not in content:
                # 添加新的导入
                if new_import not in content:
                    # 在文件开头添加导入
                    lines = content.split('\n')
                    import_line = -1
                    for i, line in enumerate(lines):
                        if line.startswith('from ') or line.startswith('import '):
                            import_line = i
                    
                    if import_line >= 0:
                        lines.insert(import_line + 1, new_import)
                        content = '\n'.join(lines)
        
        # 如果有更新，写回文件
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
        
    except Exception as e:
        print(f"更新文件 {file_path} 时出错: {e}")
        return False


def migrate_core_files():
    """
    迁移核心文件
    """
    core_files = [
        'src/core/file_handler.py',
        'src/core/translator.py', 
        'src/core/pipeline.py',
        'src/core/quality_checker.py',
    ]
    
    updated_files = []
    
    for file_path in core_files:
        path = Path(file_path)
        if path.exists():
            if update_imports_in_file(path):
                updated_files.append(file_path)
                print(f"✅ 已更新: {file_path}")
            else:
                print(f"⏭️  无需更新: {file_path}")
        else:
            print(f"❌ 文件不存在: {file_path}")
    
    return updated_files


def main():
    """
    主函数
    """
    print("🚀 开始Utils重构迁移...")
    
    # 迁移核心文件
    updated_files = migrate_core_files()
    
    print(f"\n📊 迁移完成:")
    print(f"   - 更新文件数: {len(updated_files)}")
    
    if updated_files:
        print(f"\n📝 更新的文件:")
        for file_path in updated_files:
            print(f"   - {file_path}")
    
    print(f"\n✨ 迁移完成！")


if __name__ == "__main__":
    main()
