#!/usr/bin/env python3
"""
命令行接口模块
"""

import argparse
from pathlib import Path
from typing import List

try:
    from ..core.config import TranslationConfig
except ImportError as exc:  # unittest discover may import this package as top-level "cli".
    if "attempted relative import" not in str(exc):
        raise
    from core.config import TranslationConfig


def create_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(description="批量翻译文本到双语/中文输出")
    
    # 模型配置
    parser.add_argument("--model", default="Qwen/Qwen3-32B", help="使用的模型名称")
    parser.add_argument("--temperature", type=float, default=0.7, help="生成温度")
    parser.add_argument("--top-p", dest="top_p", type=float, default=0.9, help="nucleus sampling top_p")
    parser.add_argument("--max-tokens", type=int, default=0, help="最大生成token数，<=0 表示不限制")
    parser.add_argument("--max-context-length", type=int, default=None, help="模型的最大上下文长度")

    # 提供商与连接配置
    parser.add_argument("--llm-provider", dest="llm_provider", choices=["vllm", "ollama", "openai", "openrouter"], default=None, help="LLM 提供商类型；可用 env LLM_PROVIDER 覆盖")
    parser.add_argument("--llm-base-url", dest="llm_base_url", default=None, help="OpenAI 兼容 Base URL；可用 env LLM_BASE_URL 覆盖")
    parser.add_argument("--llm-api-key", dest="llm_api_key", default=None, help="API Key；可用 env OPENROUTER_API_KEY / OPENAI_API_KEY / LLM_API_KEY 覆盖")
    parser.add_argument("--preset", help="使用 config/presets.json 中的预设（命令行参数可继续覆盖）")
    parser.add_argument("--presets-file", type=Path, default=None, help="自定义预设文件路径（默认指向 config/presets.json）")
    
    # 翻译模式配置
    parser.add_argument("--bilingual-simple", dest="bilingual_simple", action="store_true", help="启用简化双语模式（小批量翻译+代码拼接）")

    # bilingual-simple模式配置
    parser.add_argument("--line-batch-size-lines", dest="line_batch_size_lines", type=int, default=50, help="简化双语模式每批翻译的行数（基于token分析优化）")
    parser.add_argument("--context-lines", dest="context_lines", type=int, default=3, help="简化双语模式上下文行数（前后各N行）")
    parser.add_argument("--bilingual-simple-temperature", dest="bilingual_simple_temperature", type=float, default=0.0, help="简化双语模式温度（建议0.0）")
    parser.add_argument("--bilingual-simple-top-p", dest="bilingual_simple_top_p", type=float, default=1.0, help="简化双语模式top_p（建议1.0）")

    # 重试配置
    parser.add_argument("--retries", type=int, default=3, help="重试次数")
    parser.add_argument("--retry-wait", type=float, default=2.0, help="重试等待时间（秒）")
    parser.add_argument("--fallback-on-context", action="store_true", help="上下文溢出时自动降级为分块")
    
    # 质量检测配置
    parser.add_argument("--no-llm-check", action="store_true", help="禁用LLM质量检测（旧标志）")
    parser.add_argument("--disable-llm-qc", action="store_true", help="等同于 --no-llm-check，用于显式关闭 LLM 质检")
    parser.add_argument("--strict-repetition-check", action="store_true", help="启用严格重复检测")
    parser.add_argument("--qa-report", action="store_true", help="翻译/修复完成后生成硬规则 QA 报告")
    parser.add_argument("--qa-report-dir", type=Path, default=None, help="QA 报告输出目录，默认写到 log_dir/qa_reports")
    parser.add_argument("--qa-fail-on-error", action="store_true", help="QA 报告存在 error 时让该文件处理失败")
    parser.add_argument("--qa-only", action="store_true", help="仅对已有输出文件生成 QA 报告，不执行翻译")
    
    # 文件配置
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的输出文件")
    parser.add_argument("--log-dir", default="tasks/translation/logs", help="日志目录")
    parser.add_argument("--profiles-file", type=Path, default=None, help="可选：分节超参配置 JSON 文件路径")
    parser.add_argument("--enable-terminology", action="store_true", help="启用术语表提示")
    parser.add_argument("--terminology-file", type=Path, help="术语文件路径（需配合 --enable-terminology）")
    parser.add_argument("--sample-file", type=Path, help="示例文件路径")
    parser.add_argument("--preface-file", type=Path, help="前言文件路径")
    parser.add_argument("--prompt-style", choices=["default", "fanfic"], default="default", help="Prompt 模板样式（位于 prompt_styles/ 下）")
    # 独立 YAML/正文提示资产（可选）
    parser.add_argument("--preface-yaml-file", type=Path, default=None, help="YAML 专用前言提示文件路径")
    parser.add_argument("--sample-yaml-file", type=Path, default=None, help="YAML 专用示例文件路径")
    parser.add_argument("--preface-body-file", type=Path, default=None, help="正文专用前言提示文件路径")
    parser.add_argument("--sample-body-file", type=Path, default=None, help="正文专用示例文件路径")
    parser.add_argument(
        "--enable-name-glossary",
        action="store_true",
        help="翻译正文前先通读单篇全文抽取人名/昵称译名表，并注入正文 prompt",
    )
    parser.add_argument(
        "--name-glossary-file",
        type=Path,
        default=None,
        help="手动提供人名译名表；设置后会直接注入正文 prompt",
    )
    parser.add_argument(
        "--name-glossary-output-dir",
        type=Path,
        default=None,
        help="自动抽取人名译名表的保存目录，默认写到 log_dir/name_glossaries",
    )
    parser.add_argument(
        "--name-glossary-max-chars",
        type=int,
        default=120000,
        help="自动抽取时送入模型的正文最大字符数，默认120000",
    )
    parser.add_argument(
        "--name-glossary-model",
        default=None,
        help="人名预读使用的模型；默认复用 --model",
    )
    parser.add_argument(
        "--name-glossary-llm-provider",
        choices=["vllm", "ollama", "openai", "openrouter"],
        default=None,
        help="人名预读使用的 LLM provider；默认复用 --llm-provider",
    )
    parser.add_argument(
        "--name-glossary-llm-base-url",
        default=None,
        help="人名预读使用的 OpenAI 兼容 Base URL；默认复用 --llm-base-url",
    )
    parser.add_argument(
        "--name-glossary-llm-api-key",
        default=None,
        help="人名预读使用的 API Key；默认复用主翻译 key 或 provider 默认值",
    )
    
    # 生成参数
    parser.add_argument("--stop", nargs="*", default=["（未完待续）", "[END]", "<|im_end|>", "</s>"], help="停止词")
    parser.add_argument("--frequency-penalty", type=float, default=0.3, help="频率惩罚")
    parser.add_argument("--presence-penalty", type=float, default=0.2, help="存在惩罚")
    parser.add_argument(
        "--token-estimator",
        choices=["auto", "simple"],
        default="auto",
        help="Token 估算模式：auto=尽量使用模型tokenizer，simple=全部采用简易估算并跳过远端加载",
    )
    
    # 日志配置
    parser.add_argument("--realtime-log", action="store_true", default=True, help="启用实时日志")
    parser.add_argument("--stream", action="store_true", help="兼容参数：当前默认流式处理，传入后忽略")
    parser.add_argument("--debug", action="store_true", help="调试模式：降低重试、增强日志（已弃用，请使用--debug-files和--log-level）")
    parser.add_argument("--debug-files", action="store_true", help="调试文件模式：创建debug文件而不是正式输出文件")
    parser.add_argument("--repair-existing", action="store_true", help="对已有双语文件执行局部修复，仅翻译缺失或不合格的行")
    parser.add_argument("--repair-from-qa-report-dir", type=Path, default=None, help="repair 时读取该目录中的 QA 报告，优先修复 QA 标记的问题行")
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
    if args.name_glossary_file and not args.name_glossary_file.exists():
        errors.append(f"人名译名表不存在: {args.name_glossary_file}")
    
    return errors


def setup_default_paths(args: argparse.Namespace) -> None:
    """设置默认文件路径"""
    base_dir = Path(__file__).parent.parent.parent  # 从 src/cli/ 回到 translation/
    prompt_styles_dir = base_dir / "data" / "prompt_styles"
    style_name = getattr(args, "prompt_style", None) or "default"
    style_dir = prompt_styles_dir / style_name
    if not style_dir.exists():
        style_dir = prompt_styles_dir / "default"
        style_name = "default"
    args.prompt_style = style_name

    def pick_path(attr: str, paths: List[Path]) -> None:
        if getattr(args, attr, None):
            return
        for path in paths:
            if path and path.exists():
                setattr(args, attr, path)
                return

    data_dir = base_dir / "data"
    samples_dir = data_dir / "samples"

    if style_name == "default":
        if args.enable_terminology:
            pick_path("terminology_file", [data_dir / "terminology.txt"])
        pick_path("sample_file", [samples_dir / "sample.txt"])
        pick_path("preface_file", [data_dir / "preface.txt"])
        pick_path("preface_yaml_file", [data_dir / "preface_yaml.txt"])
        pick_path("preface_body_file", [data_dir / "preface_body.txt"])
        pick_path("sample_yaml_file", [samples_dir / "sample_yaml.txt"])
    else:
        if args.enable_terminology:
            pick_path("terminology_file", [
                style_dir / "terminology.txt",
                data_dir / "terminology.txt",
            ])
        pick_path("sample_file", [
            style_dir / "sample.txt",
            samples_dir / "sample.txt",
        ])
        pick_path("preface_file", [
            style_dir / "preface.txt",
            data_dir / "preface.txt",
        ])
        pick_path("preface_yaml_file", [
            style_dir / "preface_yaml.txt",
            data_dir / "preface_yaml.txt",
        ])
        pick_path("preface_body_file", [
            style_dir / "preface_body.txt",
            data_dir / "preface_body.txt",
        ])
        pick_path("sample_yaml_file", [
            style_dir / "sample_yaml.txt",
            samples_dir / "sample_yaml.txt",
        ])
    if not getattr(args, "presets_file", None):
        presets_path = base_dir / "config" / "presets.json"
        if presets_path.exists():
            args.presets_file = presets_path
    if not args.enable_terminology:
        args.terminology_file = None
    # 示例可选：不强制存在
