#!/usr/bin/env python3
"""
Token计数工具
支持通过命令行参数指定文件或目录
"""

import os
import sys
import argparse
from transformers import AutoTokenizer

def count_tokens_in_file(file_path, tokenizer):
    """计算单个文件的token数量"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        tokens = tokenizer.encode(text)
        return len(tokens)
    except Exception as e:
        print(f"❌ 读取文件失败 {file_path}: {e}")
        return 0

def count_tokens_in_directory(dir_path, tokenizer):
    """计算目录中所有txt文件的token数量"""
    total_tokens = 0
    file_count = 0
    
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith('.txt'):
                file_path = os.path.join(root, file)
                tokens = count_tokens_in_file(file_path, tokenizer)
                if tokens > 0:
                    print(f"📄 {file_path}: {tokens:,} tokens")
                    total_tokens += tokens
                    file_count += 1
    
    return total_tokens, file_count

def main():
    parser = argparse.ArgumentParser(description="Token计数工具")
    parser.add_argument("path", help="文件或目录路径")
    parser.add_argument("--model", "-m", default="Qwen/Qwen3-32B", help="使用的tokenizer模型")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.path):
        print(f"❌ 路径不存在: {args.path}")
        sys.exit(1)
    
    print(f"🔧 加载tokenizer: {args.model}")
    try:
        tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    except Exception as e:
        print(f"❌ 加载tokenizer失败: {e}")
        sys.exit(1)
    
    if os.path.isfile(args.path):
        # 单个文件
        tokens = count_tokens_in_file(args.path, tokenizer)
        print(f"📊 文件: {args.path}")
        print(f"📊 Token数量: {tokens:,}")
    else:
        # 目录
        print(f"📁 扫描目录: {args.path}")
        total_tokens, file_count = count_tokens_in_directory(args.path, tokenizer)
        print(f"📊 总文件数: {file_count}")
        print(f"📊 总Token数: {total_tokens:,}")

if __name__ == "__main__":
    main()
