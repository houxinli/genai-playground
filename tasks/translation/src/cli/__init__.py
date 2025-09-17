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
    parser.add_argument("--temperature", type=float, default=0.7, help="生成温度")
    parser.add_argument("--top-p", dest="top_p", type=float, default=0.9, help="nucleus sampling top_p")
    parser.add_argument("--max-tokens", type=int, default=0, help="最大生成token数，<=0 表示不限制")
    parser.add_argument("--max-context-length", type=int, default=None, help="模型的最大上下文长度")
    
    # 翻译模式配置
    parser.add_argument("--bilingual-simple", dest="bilingual_simple", action="store_true", help="启用简化双语模式（小批量翻译+代码拼接）")
    parser.add_argument("--enhanced-mode", dest="enhanced_mode", action="store_true", help="启用增强模式（QC检测+重新翻译）")
    parser.add_argument("--enhanced-output", dest="enhanced_output", choices=["copy", "inplace"], default="copy", help="增强模式输出策略：copy=生成新文件（默认），inplace=原地改写")
    parser.add_argument("--stream", action="store_true", help="启用流式输出")
    
    # bilingual-simple模式配置
    parser.add_argument("--line-batch-size-lines", dest="line_batch_size_lines", type=int, default=50, help="简化双语模式每批翻译的行数（基于token分析优化）")
    parser.add_argument("--context-lines", dest="context_lines", type=int, default=3, help="简化双语模式上下文行数（前后各N行）")
    parser.add_argument("--bilingual-simple-temperature", dest="bilingual_simple_temperature", type=float, default=0.0, help="简化双语模式温度（建议0.0）")
    parser.add_argument("--bilingual-simple-top-p", dest="bilingual_simple_top_p", type=float, default=1.0, help="简化双语模式top_p（建议1.0）")
    
    # 增强模式配置
    parser.add_argument("--enhanced-qc-threshold", dest="enhanced_qc_threshold", type=float, default=0.7, help="增强模式QC质量阈值（0-1）")
    parser.add_argument("--enhanced-retry-limit", dest="enhanced_retry_limit", type=int, default=2, help="增强模式最大重试次数")
    parser.add_argument("--enhanced-context-lines", dest="enhanced_context_lines", type=int, default=5, help="增强模式上下文行数")
    parser.add_argument("--enhanced-batch-size", dest="enhanced_batch_size", type=int, default=10, help="增强模式批大小（一次送入的原/译对数量）")
    
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
    parser.add_argument("--profiles-file", type=Path, default=None, help="可选：分节超参配置 JSON 文件路径")
    parser.add_argument("--terminology-file", type=Path, help="术语文件路径")
    parser.add_argument("--sample-file", type=Path, help="示例文件路径")
    parser.add_argument("--preface-file", type=Path, help="前言文件路径")
    # 独立 YAML/正文提示资产（可选）
    parser.add_argument("--preface-yaml-file", type=Path, default=None, help="YAML 专用前言提示文件路径")
    parser.add_argument("--sample-yaml-file", type=Path, default=None, help="YAML 专用示例文件路径")
    parser.add_argument("--preface-body-file", type=Path, default=None, help="正文专用前言提示文件路径")
    parser.add_argument("--sample-body-file", type=Path, default=None, help="正文专用示例文件路径")
    
    # 生成参数
    parser.add_argument("--stop", nargs="*", default=["（未完待续）", "[END]", "<|im_end|>", "</s>"], help="停止词")
    parser.add_argument("--frequency-penalty", type=float, default=0.3, help="频率惩罚")
    parser.add_argument("--presence-penalty", type=float, default=0.2, help="存在惩罚")
    
    # 日志配置
    parser.add_argument("--realtime-log", action="store_true", help="启用实时日志")
    parser.add_argument("--debug", action="store_true", help="调试模式：降低重试、增强日志（已弃用，请使用--debug-files和--log-level）")
    parser.add_argument("--debug-files", action="store_true", help="调试文件模式：创建debug文件而不是正式输出文件")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="日志级别：DEBUG=详细日志，INFO=普通日志，WARNING=警告及以上，ERROR=错误及以上，CRITICAL=严重错误")
    
    # 处理限制
    parser.add_argument("--limit", type=int, default=0, help="限制处理的文件数量")
    parser.add_argument("--offset", type=int, default=0, help="跳过前n个文件")
    parser.add_argument("--sort-by-length", action="store_true", help="按文件长度排序（从长到短）")
    
    # 超时和重试配置
    parser.add_argument("--article-timeout", type=int, default=3600, help="单篇文章超时（秒），默认3600")
    parser.add_argument("--request-timeout", type=int, default=300, help="单次请求超时（秒），默认300")
    parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数，默认3")
    parser.add_argument("--retry-delay", type=float, default=2.0, help="重试延迟（秒），默认2.0")

    # 仅处理元数据（YAML front matter）
    parser.add_argument("--metadata-only", action="store_true", help="仅翻译 YAML front matter，跳过正文")
    
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
    if args.profiles_file and not args.profiles_file.exists():
        errors.append(f"profiles 文件不存在: {args.profiles_file}")
    
    return errors


def setup_default_paths(args: argparse.Namespace) -> None:
    """设置默认文件路径"""
    base_dir = Path(__file__).parent.parent.parent  # 从 src/cli/ 回到 translation/
    
    if not args.terminology_file:
        args.terminology_file = base_dir / "data" / "terminology.txt"
    
    if not args.sample_file:
        args.sample_file = base_dir / "data" / "samples" / "sample.txt"
    
    if not args.preface_file:
        args.preface_file = base_dir / "data" / "preface.txt"

    # 设置 YAML/正文专用前言与示例（可选默认）
    if not getattr(args, 'preface_yaml_file', None):
        args.preface_yaml_file = base_dir / "data" / "preface_yaml.txt"
    if not getattr(args, 'preface_body_file', None):
        args.preface_body_file = base_dir / "data" / "preface_body.txt"
    if not getattr(args, 'sample_yaml_file', None):
        args.sample_yaml_file = base_dir / "data" / "samples" / "sample_yaml.txt"
    # 示例可选：不强制存在
