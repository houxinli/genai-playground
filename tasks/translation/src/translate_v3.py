#!/usr/bin/env python3
"""
Pixiv小说翻译器 - 重构版本

基于面向对象设计的模块化翻译系统
"""

import sys
from pathlib import Path

# 添加当前目录到Python路径
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from src.core.config import TranslationConfig
from src.core.pipeline import TranslationPipeline
from src.cli import create_argument_parser, validate_args, setup_default_paths


def main() -> None:
    """主函数"""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # 设置默认路径
    setup_default_paths(args)
    
    # 验证参数
    errors = validate_args(args)
    if errors:
        for error in errors:
            print(f"错误: {error}")
        sys.exit(1)
    
    # 创建配置对象
    config = TranslationConfig.from_args(args)
    
    # 创建翻译流程
    pipeline = TranslationPipeline(config)
    
    # 运行翻译
    success_count = pipeline.run(args.inputs)
    
    if success_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
