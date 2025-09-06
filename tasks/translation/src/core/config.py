#!/usr/bin/env python3
"""
翻译配置管理模块
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
import argparse


@dataclass
class TranslationConfig:
    """翻译配置类，集中管理核心配置参数"""
    
    # 模型配置
    model: str = "Qwen/Qwen3-32B"
    max_context_length: Optional[int] = None
    
    # 翻译模式配置
    mode: str = "full"  # "full" 或 "chunked"
    bilingual: bool = False
    bilingual_simple: bool = False  # 新的简化bilingual模式
    stream: bool = False
    
    # 分块配置
    chunk_size_chars: int = 20000
    overlap_chars: int = 1000
    # 行级分块配置（>0 时优先生效）
    line_chunk_size_lines: int = 0
    line_overlap_lines: int = 0
    
    # bilingual-simple模式配置
    line_batch_size_lines: int = 20  # 每批翻译的行数
    context_lines: int = 3  # 上下文行数（前后各3行）
    
    # 重试配置
    retries: int = 3
    retry_wait: float = 2.0
    fallback_on_context: bool = True
    
    # 质量检测配置
    no_llm_check: bool = False
    strict_repetition_check: bool = False
    # 质量检测最大生成；<=0 表示不限制（交由模型/服务端按上下文决定）
    quality_max_tokens: int = 0
    
    # 文件配置
    overwrite: bool = False
    log_dir: Path = Path("logs")
    profiles_file: Optional[Path] = None
    terminology_file: Optional[Path] = None
    sample_file: Optional[Path] = None
    preface_file: Optional[Path] = None
    # 独立提示资产（可选）：YAML 与 正文
    preface_yaml_file: Optional[Path] = None
    sample_yaml_file: Optional[Path] = None
    preface_body_file: Optional[Path] = None
    sample_body_file: Optional[Path] = None
    
    # 默认生成参数（用于向后兼容，建议使用ProfileManager）
    # 注意：这些参数主要用于CLI参数解析和向后兼容
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 0
    frequency_penalty: float = 0.3
    presence_penalty: float = 0.2
    repetition_penalty: float = 1.1
    no_repeat_ngram_size: int = 8
    stop: List[str] = field(default_factory=lambda: [
        "（未完待续）", "[END]", "<|im_end|>", "</s>"
    ])
    
    # 日志配置
    realtime_log: bool = False
    debug: bool = False
    
    # 处理限制
    limit: int = 0
    # 流式行级 flush 阈值（字符数），防止短文本漏记
    stream_line_flush_chars: int = 60
    
    # 分节专用参数改为 profiles 文件覆盖与函数内默认，不再在 config 中分散定义
    # 仅翻译 YAML front matter
    metadata_only: bool = False
    
    @classmethod
    def from_args(cls, args: argparse.Namespace) -> 'TranslationConfig':
        """从命令行参数创建配置对象"""
        return cls(
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            max_context_length=args.max_context_length,
            mode=args.mode,
            bilingual=args.bilingual,
            bilingual_simple=getattr(args, 'bilingual_simple', False),
            stream=args.stream,
            chunk_size_chars=args.chunk_size_chars,
            overlap_chars=args.overlap_chars,
            line_chunk_size_lines=getattr(args, 'line_chunk_size_lines', 0),
            line_overlap_lines=getattr(args, 'line_overlap_lines', 0),
            line_batch_size_lines=getattr(args, 'line_batch_size_lines', 20),
            context_lines=getattr(args, 'context_lines', 3),
            retries=args.retries,
            retry_wait=args.retry_wait,
            fallback_on_context=args.fallback_on_context,
            no_llm_check=args.no_llm_check,
            strict_repetition_check=args.strict_repetition_check,
            overwrite=args.overwrite,
            log_dir=Path(args.log_dir),
            profiles_file=getattr(args, 'profiles_file', None),
            terminology_file=args.terminology_file if hasattr(args, 'terminology_file') else None,
            sample_file=args.sample_file if hasattr(args, 'sample_file') else None,
            preface_file=args.preface_file if hasattr(args, 'preface_file') else None,
            preface_yaml_file=getattr(args, 'preface_yaml_file', None),
            sample_yaml_file=getattr(args, 'sample_yaml_file', None),
            preface_body_file=getattr(args, 'preface_body_file', None),
            sample_body_file=getattr(args, 'sample_body_file', None),
            stop=args.stop,
            frequency_penalty=args.frequency_penalty,
            presence_penalty=args.presence_penalty,
            realtime_log=args.realtime_log,
            debug=getattr(args, 'debug', False),
            limit=args.limit,
            metadata_only=getattr(args, 'metadata_only', False),
        )
    
    def get_max_context_length(self) -> int:
        """获取模型的最大上下文长度"""
        if self.max_context_length:
            return self.max_context_length
        
        # 根据模型名称自动推断
        if "32B" in self.model and "AWQ" not in self.model:
            return 32768
        else:
            return 40960
    
    def get_output_suffix(self) -> str:
        """获取输出文件后缀"""
        is_awq = "AWQ" in self.model
        if self.bilingual or self.bilingual_simple:
            return "_awq_bilingual" if is_awq else "_bilingual"
        else:
            return "_awq_zh" if is_awq else "_zh"
    
    def validate(self) -> List[str]:
        """验证配置参数，返回错误列表"""
        errors = []
        
        if self.temperature < 0 or self.temperature > 2:
            errors.append("temperature 必须在 0-2 之间")
        
        if self.chunk_size_chars <= 0:
            errors.append("chunk_size_chars 必须大于 0")
        
        if self.overlap_chars < 0:
            errors.append("overlap_chars 不能为负数")
        
        if self.retries < 0:
            errors.append("retries 不能为负数")
        
        if self.retry_wait < 0:
            errors.append("retry_wait 不能为负数")
        
        return errors
