#!/usr/bin/env python3
"""
Utils重构测试脚本
"""

import sys
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_text_utils():
    """测试文本工具"""
    print("🧪 测试文本工具...")
    
    try:
        from utils.text import split_text_into_chunks, clean_output_text, estimate_tokens
        
        # 测试文本分块
        text = "这是一个测试文本。" * 100
        chunks = split_text_into_chunks(text, 50)
        print(f"   ✅ 文本分块: {len(chunks)} 块")
        
        # 测试文本清理
        dirty_text = "<think>思考内容</think>这是正常文本。"
        clean_text = clean_output_text(dirty_text)
        print(f"   ✅ 文本清理: '{clean_text}'")
        
        # 测试token估算
        tokens = estimate_tokens("这是一个测试")
        print(f"   ✅ Token估算: {tokens}")
        
        return True
    except Exception as e:
        print(f"   ❌ 文本工具测试失败: {e}")
        return False


def test_file_utils():
    """测试文件工具"""
    print("🧪 测试文件工具...")
    
    try:
        from utils.file import parse_yaml_front_matter, clean_filename, generate_output_filename
        from pathlib import Path
        
        # 测试YAML解析
        yaml_content = """---
title: 测试标题
author: 测试作者
---
这是正文内容。"""
        metadata, content = parse_yaml_front_matter(yaml_content)
        print(f"   ✅ YAML解析: {metadata.get('title', 'N/A')}")
        
        # 测试文件名清理
        dirty_name = "test<>file.txt"
        clean_name = clean_filename(dirty_name)
        print(f"   ✅ 文件名清理: '{clean_name}'")
        
        # 测试输出文件名生成
        input_path = Path("test.txt")
        output_name = generate_output_filename(input_path, "_bilingual", debug_mode=True)
        print(f"   ✅ 输出文件名: '{output_name}'")
        
        return True
    except Exception as e:
        print(f"   ❌ 文件工具测试失败: {e}")
        return False


def test_format_utils():
    """测试格式化工具"""
    print("🧪 测试格式化工具...")
    
    try:
        from utils.format import create_bilingual_output, format_quality_output
        
        # 测试双语输出
        original_lines = ["原文1", "原文2"]
        translated_lines = ["译文1", "译文2"]
        bilingual = create_bilingual_output(original_lines, translated_lines)
        print(f"   ✅ 双语输出: {len(bilingual.split())} 行")
        
        # 测试质量输出格式化
        quality_result = "经过思考，我认为这个翻译质量很好。GOOD"
        formatted = format_quality_output(quality_result)
        print(f"   ✅ 质量输出格式化: '{formatted}'")
        
        return True
    except Exception as e:
        print(f"   ❌ 格式化工具测试失败: {e}")
        return False


def test_validation_utils():
    """测试验证工具"""
    print("🧪 测试验证工具...")
    
    try:
        from utils.validation import validate_translation_quality, validate_content_format
        
        # 测试翻译质量验证
        original = "这是原文。"
        translated = "This is the translation."
        is_valid, error = validate_translation_quality(original, translated)
        print(f"   ✅ 翻译质量验证: {is_valid}")
        
        # 测试内容格式验证
        content = "正常内容"
        is_valid, error = validate_content_format(content)
        print(f"   ✅ 内容格式验证: {is_valid}")
        
        return True
    except Exception as e:
        print(f"   ❌ 验证工具测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🚀 开始Utils重构测试...\n")
    
    tests = [
        test_text_utils,
        test_file_utils,
        test_format_utils,
        test_validation_utils,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！Utils重构成功！")
        return True
    else:
        print("❌ 部分测试失败，需要修复")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
