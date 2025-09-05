#!/usr/bin/env python3
"""
命令行接口模块
"""

import argparse
from pathlib import Path
from typing import List

from ..core.config import TranslationConfig


def create_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(description="批量翻译 Pixiv 小说到 _zh.txt")
    
    # 模型配置
    parser.add_argument("--model", default="Qwen/Qwen3-32B", help="使用的模型名称")
    parser.add_argument("--temperature", type=float, default=0.1, help="生成温度")
    parser.add_argument("--max-tokens", type=int, default=0, help="最大生成token数，<=0 表示不限制")
    parser.add_argument("--max-context-length", type=int, default=None, help="模型的最大上下文长度")
    
    # 翻译模式配置
    parser.add_argument("--mode", choices=["full", "chunked"], default="full", help="翻译模式")
    parser.add_argument("--bilingual", action="store_true", help="启用双语对照模式")
    parser.add_argument("--stream", action="store_true", help="启用流式输出")
    
    # 分块配置
    parser.add_argument("--chunk-size-chars", type=int, default=20000, help="分块大小（字符）")
    parser.add_argument("--overlap-chars", type=int, default=1000, help="分块重叠大小（字符）")
    
    # 重试配置
    parser.add_argument("--retries", type=int, default=3, help="重试次数")
    parser.add_argument("--retry-wait", type=float, default=2.0, help="重试等待时间（秒）")
    parser.add_argument("--fallback-on-context", action="store_true", help="上下文溢出时自动降级为分块")
    
    # 质量检测配置
    parser.add_argument("--no-llm-check", action="store_true", help="禁用LLM质量检测")
    parser.add_argument("--strict-repetition-check", action="store_true", help="启用严格重复检测")
    
    # 文件配置
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的输出文件")
    parser.add_argument("--log-dir", default="logs", help="日志目录")
    parser.add_argument("--terminology-file", type=Path, help="术语文件路径")
    parser.add_argument("--sample-file", type=Path, help="示例文件路径")
    parser.add_argument("--preface-file", type=Path, help="前言文件路径")
    
    # 生成参数
    parser.add_argument("--stop", nargs="*", default=["（未完待续）", "[END]"], help="停止词")
    parser.add_argument("--frequency-penalty", type=float, default=0.3, help="频率惩罚")
    parser.add_argument("--presence-penalty", type=float, default=0.2, help="存在惩罚")
    
    # 日志配置
    parser.add_argument("--realtime-log", action="store_true", help="启用实时日志")
    parser.add_argument("--debug", action="store_true", help="调试模式：降低重试、增强日志")
    
    # 处理限制
    parser.add_argument("--limit", type=int, default=0, help="限制处理的文件数量")
    
    # 输入文件
    parser.add_argument("inputs", nargs="+", help="输入文件/目录/通配符")
    
    return parser


def validate_args(args: argparse.Namespace) -> List[str]:
    """验证命令行参数"""
    errors = []
    
    # 检查模型名称
    if not args.model:
        errors.append("模型名称不能为空")
    
    # 检查温度值
    if args.temperature < 0 or args.temperature > 2:
        errors.append("temperature 必须在 0-2 之间")
    
    # 检查分块大小
    if args.chunk_size_chars <= 0:
        errors.append("chunk_size_chars 必须大于 0")
    
    if args.overlap_chars < 0:
        errors.append("overlap_chars 不能为负数")
    
    # 检查重试参数
    if args.retries < 0:
        errors.append("retries 不能为负数")
    
    if args.retry_wait < 0:
        errors.append("retry_wait 不能为负数")
    
    # 检查文件路径
    if args.terminology_file and not args.terminology_file.exists():
        errors.append(f"术语文件不存在: {args.terminology_file}")
    
    if args.sample_file and not args.sample_file.exists():
        errors.append(f"示例文件不存在: {args.sample_file}")
    
    if args.preface_file and not args.preface_file.exists():
        errors.append(f"前言文件不存在: {args.preface_file}")
    
    return errors


def setup_default_paths(args: argparse.Namespace) -> None:
    """设置默认文件路径"""
    base_dir = Path(__file__).parent.parent.parent  # 从 src/cli/ 回到 translation/
    
    if not args.terminology_file:
        args.terminology_file = base_dir / "data" / "terminology.txt"
    
    if not args.sample_file:
        # 根据模式选择示例文件
        if args.bilingual:
            args.sample_file = base_dir / "data" / "samples" / "sample_bilingual.txt"
        else:
            args.sample_file = base_dir / "data" / "samples" / "sample.txt"
    
    if not args.preface_file:
        # 根据模式选择preface文件
        if args.bilingual:
            args.preface_file = base_dir / "data" / "preface_bilingual.txt"
        else:
            args.preface_file = base_dir / "data" / "preface.txt"
