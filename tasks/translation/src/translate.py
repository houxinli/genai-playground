#!/usr/bin/env python3
"""翻译入口脚本（支持 Pixiv/Fanbox 文本与双语修复流程）。"""

import argparse
import sys
from pathlib import Path

# 添加当前目录到Python路径
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from src.core.config import TranslationConfig
from src.core.pipeline import TranslationPipeline
from src.cli import create_argument_parser, validate_args, setup_default_paths
from src.utils.presets import prepare_preset_defaults


def main() -> None:
    """主函数"""
    raw_argv = sys.argv[1:]

    preset_parser = argparse.ArgumentParser(add_help=False)
    preset_parser.add_argument("--preset")
    preset_parser.add_argument("--presets-file")
    preset_args, _ = preset_parser.parse_known_args(raw_argv)

    parser = create_argument_parser()
    presets_file = Path(preset_args.presets_file).expanduser() if preset_args.presets_file else None
    prepare_preset_defaults(parser, preset_args.preset, presets_file)
    args = parser.parse_args(raw_argv)
    if args.llm_provider is None:
        args.llm_provider = "openrouter"
    
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
