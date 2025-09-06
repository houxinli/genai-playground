#!/usr/bin/env python3
"""
统一工具模块接口
"""

# 文本处理工具
from .text import (
    split_text_into_chunks,
    clean_output_text,
    detect_and_truncate_repetition,
    estimate_tokens,
    estimate_prompt_tokens
)

# 文件处理工具
from .file import (
    parse_yaml_front_matter,
    clean_filename,
    generate_output_filename
)

# 格式化工具
from .format import (
    create_bilingual_output,
    format_quality_output
)

# 验证工具
from .validation import (
    validate_translation_quality,
    validate_content_format
)

__all__ = [
    # 文本处理
    'split_text_into_chunks',
    'clean_output_text',
    'detect_and_truncate_repetition',
    'estimate_tokens',
    'estimate_prompt_tokens',
    
    # 文件处理
    'parse_yaml_front_matter',
    'clean_filename',
    'generate_output_filename',
    
    # 格式化
    'create_bilingual_output',
    'format_quality_output',
    
    # 验证
    'validate_translation_quality',
    'validate_content_format'
]