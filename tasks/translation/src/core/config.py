#!/usr/bin/env python3
"""
翻译配置管理模块
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
import argparse
import os
import json
from urllib.parse import urlparse


@dataclass
class TranslationConfig:
    """翻译配置类，集中管理核心配置参数"""
    
    # 模型配置
    model: str = "Qwen/Qwen3-32B"
    max_context_length: Optional[int] = None
    
    # 翻译模式配置
    bilingual_simple: bool = False  # 简化bilingual模式
    enhanced_mode: bool = False  # 增强模式：QC检测 + 重新翻译
    enhanced_output: str = "copy"  # copy | inplace
    
    # bilingual-simple模式配置
    line_batch_size_lines: int = 50  # 每批翻译的行数（基于token分析优化）
    context_lines: int = 3  # 上下文行数（前后各3行）
    
    # 增强模式配置
    enhanced_qc_threshold: float = 0.7  # QC质量阈值，低于此值重新翻译
    enhanced_retry_limit: int = 2  # 增强模式最大重试次数
    enhanced_context_lines: int = 5  # 增强模式上下文行数
    enhanced_batch_size: int = 10  # 增强模式批大小（逐行对照重译）
    
    # 重试配置
    retries: int = 3
    retry_wait: float = 2.0
    fallback_on_context: bool = True
    repair_existing: bool = False
    
    # 质量检测配置
    no_llm_check: bool = False
    strict_repetition_check: bool = False
    # 质量检测最大生成；<=0 表示不限制（交由模型/服务端按上下文决定）
    quality_max_tokens: int = 0
    
    # 文件配置
    overwrite: bool = False
    log_dir: Path = Path("tasks/translation/logs")
    profiles_file: Optional[Path] = None
    terminology_file: Optional[Path] = None
    sample_file: Optional[Path] = None
    preface_file: Optional[Path] = None
    # 独立提示资产（可选）：YAML 与 正文
    preface_yaml_file: Optional[Path] = None
    sample_yaml_file: Optional[Path] = None
    preface_body_file: Optional[Path] = None
    sample_body_file: Optional[Path] = None
    prompt_style: str = "default"
    
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
    token_estimator: str = "auto"
    
    # 日志配置
    realtime_log: bool = True
    debug: bool = False  # 已弃用，保持向后兼容
    debug_files: bool = False  # 调试文件模式：是否创建debug文件
    log_level: str = "INFO"  # 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
    
    # 超时和重试配置
    article_timeout_s: int = 3600  # 单篇文章超时（秒）
    request_timeout_s: int = 300   # 单次请求超时（秒）
    max_retries: int = 3           # 最大重试次数
    retry_delay_s: float = 2.0     # 重试延迟（秒）
    
    # 处理限制
    limit: int = 0
    offset: int = 0
    sort_by_length: bool = False
    # 流式行级 flush 阈值（字符数），防止短文本漏记
    stream_line_flush_chars: int = 60
    
    # 分节专用参数改为 profiles 文件覆盖与函数内默认，不再在 config 中分散定义
    # 仅翻译 YAML front matter
    metadata_only: bool = False

    # 人名一致性预读：翻译正文前先从全文抽取名称/昵称/译名表，再注入正文 prompt
    enable_name_glossary: bool = False
    name_glossary_file: Optional[Path] = None
    name_glossary_output_dir: Optional[Path] = None
    name_glossary_max_chars: int = 120000
    name_glossary_model: Optional[str] = None
    name_glossary_llm_provider: Optional[str] = None
    name_glossary_llm_base_url: Optional[str] = None
    name_glossary_llm_api_key: Optional[str] = None

    # 提供商与连接（可通过环境变量覆盖）
    # 支持 provider: vllm | ollama | openai | openrouter
    llm_provider: str = "openrouter"
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    
    @classmethod
    def _read_api_key_from_config(cls, config_path: Optional[Path] = None, provider: str = "openrouter") -> Optional[str]:
        """从 config.json 读取 API key（优先级：translator.openrouter.api-key > translator.openai.api-key）"""
        if config_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent  # translation/
            config_path = base_dir / "data" / "config.json"
        try:
            if not config_path.exists():
                return None
            data = json.loads(config_path.read_text(encoding="utf-8"))
            translator = data.get("translator", {})
            provider = (provider or "openrouter").lower()
            if provider == "openrouter":
                api_key = (
                    translator.get("openrouter", {}).get("api-key")
                    or translator.get("llm", {}).get("api-key")
                )
            elif provider == "openai":
                api_key = (
                    translator.get("openai", {}).get("api-key")
                    or translator.get("llm", {}).get("api-key")
                )
            else:
                api_key = translator.get("llm", {}).get("api-key")
            if api_key:
                return str(api_key).strip()
        except Exception:
            pass
        return None
    
    @classmethod
    def from_args(cls, args: argparse.Namespace) -> 'TranslationConfig':
        """从命令行参数创建配置对象"""
        # 优先级：CLI > ENV > config.json > 默认
        env_provider = os.environ.get("LLM_PROVIDER", None)
        env_base_url = os.environ.get("LLM_BASE_URL", None)

        def pick_api_key(provider_name: str) -> Optional[str]:
            provider_name = (provider_name or "").lower()
            if provider_name == "openrouter":
                return os.environ.get("OPENROUTER_API_KEY")
            if provider_name == "openai":
                return os.environ.get("OPENAI_API_KEY")
            # 其它 provider（vllm/ollama）不需要 API key
            return None

        provider_via_cli = getattr(args, 'llm_provider', None) or env_provider or 'openrouter'
        explicit_base_url = getattr(args, 'llm_base_url', None)
        # 避免 LLM_BASE_URL 污染显式/默认 provider。例如 openrouter 不应误连 localhost:11434。
        base_url = explicit_base_url
        if not base_url and env_base_url and env_provider and env_provider.lower() == str(provider_via_cli).lower():
            base_url = env_base_url
        env_api_key = pick_api_key(provider_via_cli)
        config_api_key = None
        if not env_api_key:
            config_api_key = cls._read_api_key_from_config(provider=provider_via_cli)

        return cls(
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            max_context_length=args.max_context_length,
            bilingual_simple=getattr(args, 'bilingual_simple', False),
            enhanced_mode=getattr(args, 'enhanced_mode', False),
            enhanced_output=getattr(args, 'enhanced_output', 'copy'),
            line_batch_size_lines=getattr(args, 'line_batch_size_lines', 20),
            context_lines=getattr(args, 'context_lines', 3),
            enhanced_qc_threshold=getattr(args, 'enhanced_qc_threshold', 0.7),
            enhanced_retry_limit=getattr(args, 'enhanced_retry_limit', 2),
            enhanced_context_lines=getattr(args, 'enhanced_context_lines', 5),
            enhanced_batch_size=getattr(args, 'enhanced_batch_size', 10),
            retries=args.retries,
            retry_wait=args.retry_wait,
            fallback_on_context=args.fallback_on_context,
            repair_existing=getattr(args, "repair_existing", False),
            no_llm_check=args.no_llm_check or getattr(args, "disable_llm_qc", False),
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
            prompt_style=getattr(args, 'prompt_style', 'default'),
            stop=args.stop,
            frequency_penalty=args.frequency_penalty,
            presence_penalty=args.presence_penalty,
            token_estimator=getattr(args, "token_estimator", "auto"),
            realtime_log=args.realtime_log,
            debug=getattr(args, 'debug', False),
            debug_files=getattr(args, 'debug_files', False) or getattr(args, 'debug', False),  # 新标志或旧标志
            log_level=getattr(args, 'log_level', 'DEBUG' if getattr(args, 'debug', False) else 'INFO'),  # 如果使用旧debug标志则设为DEBUG，否则使用新参数
            limit=args.limit,
            offset=args.offset,
            sort_by_length=getattr(args, 'sort_by_length', False),
            article_timeout_s=getattr(args, 'article_timeout_s', 3600),
            request_timeout_s=getattr(args, 'request_timeout_s', 300),
            max_retries=getattr(args, 'max_retries', 3),
            retry_delay_s=getattr(args, 'retry_delay_s', 2.0),
            metadata_only=getattr(args, 'metadata_only', False),
            enable_name_glossary=getattr(args, 'enable_name_glossary', False),
            name_glossary_file=getattr(args, 'name_glossary_file', None),
            name_glossary_output_dir=getattr(args, 'name_glossary_output_dir', None),
            name_glossary_max_chars=getattr(args, 'name_glossary_max_chars', 120000),
            name_glossary_model=getattr(args, 'name_glossary_model', None),
            name_glossary_llm_provider=getattr(args, 'name_glossary_llm_provider', None),
            name_glossary_llm_base_url=getattr(args, 'name_glossary_llm_base_url', None),
            name_glossary_llm_api_key=getattr(args, 'name_glossary_llm_api_key', None),
            llm_provider=provider_via_cli or 'openrouter',
            llm_base_url=base_url,
            llm_api_key=getattr(args, 'llm_api_key', None) or env_api_key or config_api_key,
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
        if self.bilingual_simple:
            return "_awq_bilingual" if is_awq else "_bilingual"
        else:
            return "_awq_zh" if is_awq else "_zh"
    
    def validate(self) -> List[str]:
        """验证配置参数，返回错误列表"""
        errors = []
        
        if self.temperature < 0 or self.temperature > 2:
            errors.append("temperature 必须在 0-2 之间")
        
        if self.retries < 0:
            errors.append("retries 不能为负数")
        
        if self.retry_wait < 0:
            errors.append("retry_wait 不能为负数")

        def validate_provider_url(provider_value: Optional[str], base_url_value: Optional[str], label: str) -> None:
            provider = (provider_value or "").lower()
            base_url = (base_url_value or "").strip()
            if not base_url:
                return
            parsed = urlparse(base_url)
            host = (parsed.hostname or "").lower()
            if provider == "openrouter" and host and "openrouter.ai" not in host:
                errors.append(
                    f"{label}=openrouter 时 base_url 必须指向 openrouter.ai；"
                    "如果要连本地服务，请改用 --llm-provider ollama 或 vllm"
                )
            if provider in {"ollama", "vllm"} and "openrouter.ai" in host:
                errors.append(
                    f"{label}={provider} 不能使用 OpenRouter base URL；"
                    "请改用 --llm-provider openrouter"
                )

        validate_provider_url(self.llm_provider, self.llm_base_url, "llm_provider")
        validate_provider_url(
            self.name_glossary_llm_provider or self.llm_provider,
            self.name_glossary_llm_base_url,
            "name_glossary_llm_provider",
        )

        if self.name_glossary_max_chars <= 0:
            errors.append("name_glossary_max_chars 必须为正数")
        
        return errors
