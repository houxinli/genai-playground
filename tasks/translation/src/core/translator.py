#!/usr/bin/env python3
"""
翻译核心模块
"""

import time
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from openai import OpenAI
from openai import BadRequestError

from .config import TranslationConfig
from .logger import UnifiedLogger
from .quality_checker import QualityChecker
from .prompt import PromptBuilder, create_config
from ..utils.text.cleaning import clean_output_text, detect_and_truncate_repetition
from ..utils.text.token_estimation import calculate_max_tokens_for_messages, log_model_call
from .streaming_handler import StreamingHandler
from .profile_manager import ProfileManager, GenerationParams


class Translator:
    """翻译核心类"""
    
    def __init__(self, config: TranslationConfig, logger: UnifiedLogger, quality_checker: QualityChecker):
        """
        初始化翻译器
        
        Args:
            config: 翻译配置
            logger: 日志器
            quality_checker: 质量检测器
        """
        self.config = config
        self.logger = logger
        self.quality_checker = quality_checker
        # 确保质量检测器也有logger
        if hasattr(self.quality_checker, 'logger'):
            self.quality_checker.logger = logger
        # 确保质量检测器的StreamingHandler也有logger
        if hasattr(self.quality_checker, 'streaming_handler'):
            self.quality_checker.streaming_handler.logger = logger
        # 初始化 OpenAI 兼容客户端（支持 vLLM/Ollama/OpenAI/OpenRouter）
        base_url = self.config.llm_base_url
        provider = (self.config.llm_provider or "vllm").lower()
        api_key = self.config.llm_api_key or "dummy"
        
        # 调试：记录 API key 状态（不打印完整 key）
        if provider == "openrouter" and api_key and api_key != "dummy":
            self.logger.debug(f"OpenRouter API key 已读取: {api_key[:20]}...")
            self.logger.info("OpenRouter: 将禁用流式并使用最小参数集调用")
        elif provider == "openrouter":
            self.logger.warning(f"⚠️ OpenRouter API key 未设置，provider={provider}, api_key={api_key}")
        
        if not base_url:
            if provider == "vllm":
                base_url = "http://localhost:8000/v1"
                if not self.config.llm_api_key:
                    api_key = "dummy"
            elif provider == "ollama":
                base_url = "http://localhost:11434/v1"
                if not self.config.llm_api_key:
                    api_key = "ollama"
            elif provider == "openrouter":
                base_url = "https://openrouter.ai/api/v1"
            elif provider == "openai":
                base_url = None  # 使用 SDK 默认 https://api.openai.com/v1
        
        # OpenRouter 需要额外的 headers（根据官方文档：https://openrouter.ai/docs/quickstart）
        client_timeout = getattr(self.config, "request_timeout_s", 60) or 60
        if provider == "openrouter":
            default_headers = {
                "HTTP-Referer": "https://github.com/houxinli/genai-playground",  # 用于排名展示
                "X-Title": "Translation Tool"  # 用于排名展示
            }
            self.client = OpenAI(
                base_url=base_url,
                api_key=api_key,
                default_headers=default_headers,
                timeout=client_timeout,
            )
        else:
            self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=client_timeout)
        self.profile_manager = ProfileManager(config.profiles_file)
        self.streaming_handler = StreamingHandler(self.client, logger, config, self.profile_manager)
        
        # 初始化PromptBuilder（支持 prompt style）
        prompt_styles_dir = Path(__file__).parent.parent.parent / "data" / "prompt_styles"
        style_name = getattr(self.config, "prompt_style", "default") or "default"
        style_dir = prompt_styles_dir / style_name
        if not style_dir.exists():
            style_dir = prompt_styles_dir / "default"
        prompt_config = create_config("translation", style_dir)
        prompt_config.preface_file = "preface.txt"
        prompt_config.sample_file = "sample.txt"
        if self.config.terminology_file:
            prompt_config.terminology_file = str(self.config.terminology_file)
        else:
            prompt_config.terminology_file = None
        prompt_config.max_context_lines = getattr(self.config, "context_lines", prompt_config.max_context_lines)
        self.prompt_builder = PromptBuilder(prompt_config)
        self.name_glossary_context = ""

    def clear_name_glossary(self) -> None:
        """清除当前文件的人名译名提示，避免跨文件串味。"""
        self.name_glossary_context = ""
        if hasattr(self.prompt_builder.config, "extra_system_context"):
            self.prompt_builder.config.extra_system_context = None

    def set_name_glossary(self, glossary_text: str) -> None:
        """设置当前文件的人名译名提示，供正文翻译 prompt 使用。"""
        block = self._format_name_glossary_block(glossary_text)
        self.name_glossary_context = block
        if hasattr(self.prompt_builder.config, "extra_system_context"):
            self.prompt_builder.config.extra_system_context = block

    def _format_name_glossary_block(self, glossary_text: str) -> str:
        glossary_text = (glossary_text or "").strip()
        if not glossary_text:
            return ""
        compact_lines = self._compact_name_glossary(glossary_text)
        return (
            "【人名译名硬约束】\n"
            "本节只用于保持人名、昵称、称谓一致，严禁输出本节任何内容。"
            "“=>”后的中文名是唯一标准译名；“禁止译为”后的名称不得使用。"
            "若人工/历史规则与自动候选冲突，必须使用人工/历史规则。\n"
            + "\n".join(compact_lines)
        )

    def _compact_name_glossary(self, glossary_text: str) -> List[str]:
        """把规则文件或 Markdown 表格压成模型更不容易复读的短约束行。"""
        compact: List[str] = []
        for raw in glossary_text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            if line.startswith("|"):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if len(cells) < 3:
                    continue
                if cells[0] in {"日文表記", "---"} or set(cells[0]) <= {"-"}:
                    continue
                jp = cells[0]
                kana = cells[1] if len(cells) > 1 else ""
                zh = cells[2] if len(cells) > 2 else ""
                aliases = cells[3] if len(cells) > 3 else ""
                note = cells[4] if len(cells) > 4 else ""
                if jp and zh:
                    detail = f"- {jp}"
                    if kana and kana != jp:
                        detail += f"（{kana}）"
                    detail += f" => {zh}"
                    if aliases:
                        detail += f"；别名/称谓: {aliases}"
                    if note:
                        detail += f"；备注: {note}"
                    compact.append(detail)
                continue
            if "=" in line:
                source, target = line.split("=", 1)
                source = source.strip()
                target = target.strip()
                preferred, forbidden = target, ""
                if "|" in target:
                    preferred, forbidden = [part.strip() for part in target.split("|", 1)]
                if source and preferred:
                    detail = f"- {source} => {preferred}"
                    if forbidden:
                        detail += f"；禁止译为: {forbidden}"
                    compact.append(detail)
            elif line.startswith("【") and line.endswith("】"):
                compact.append(line)
            elif len(line) <= 160:
                compact.append(f"- {line}")
        return compact[:120]

    def _append_runtime_name_glossary(self, parts: List[str]) -> None:
        if self.name_glossary_context:
            parts.append(self.name_glossary_context)

    def extract_name_glossary(self, source_text: str, metadata: Optional[Dict] = None) -> Tuple[str, Dict[str, int]]:
        """通读单篇原文，抽取人名/读音/昵称/中文译名建议。"""
        metadata = metadata or {}
        max_chars = max(1, getattr(self.config, "name_glossary_max_chars", 120000))
        source = source_text.strip()
        truncated = False
        if len(source) > max_chars:
            source = source[:max_chars]
            truncated = True

        title = metadata.get("title") or metadata.get("post_id") or metadata.get("novel_id") or ""
        system = (
            "你是日中小说翻译流水线的人名术语整理器。"
            "任务是从整篇日文原文中抽取角色名、姓氏、名字、假名/片假名写法、昵称、称谓、代称，"
            "并给出稳定的简体中文译名。只整理名称，不翻译剧情。"
            "必须特别注意：同一个假名可能对应不同汉字；同一角色可能有昵称或称谓；"
            "不要把不同角色合并。不要抽取普通群体名词、泛称、职业称呼、地点、物品或剧情概念；"
            "只有在它们是固定专有名词或具名角色称呼时才列入。"
        )
        user = (
            "请只输出 Markdown 表格，列为：日文表记 | 假名/片假名 | 中文标准译名 | 别名/昵称/称谓 | 备注。\n"
            "要求：\n"
            "1. 只列有助于后续翻译一致性的人名/角色称呼/组织称呼。\n"
            "2. 中文译名要自然；已有常见译名时优先常见译名。\n"
            "3. 不确定的译名可在备注写“待确认”，但仍给出一个稳定译法。\n"
            "4. 排除“同学”“老师”“男生们”“女生组”等普通称呼，除非原文把它当作专名。\n"
            "5. 不输出解释段落，不输出剧情摘要。\n\n"
            f"标题/ID: {title}\n"
            f"全文是否截断: {'是' if truncated else '否'}\n\n"
            "【原文】\n"
            f"{source}"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            allowed = self._calculate_max_tokens(messages, requested_max_tokens=1800, cap=1800)
            params = self.profile_manager.get_generation_params(
                "yaml",
                max_tokens=allowed,
                temperature=0.0,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                stop=None,
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            cleaned = clean_output_text(result or "").strip()
            return cleaned, token_stats
        except Exception as e:
            self.logger.warning(f"人名译名表抽取失败: {e}")
            return "", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    
    def translate_text(self, text: str, chunk_index: Optional[int] = None) -> Tuple[str, str, bool, Dict[str, int]]:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            chunk_index: 分块索引（用于日志）
            
        Returns:
            (翻译结果, 完整prompt, 是否成功, token统计)
        """
        chunk_info = f"块 {chunk_index}" if chunk_index is not None else "块"
        
        for attempt in range(1, self.config.retries + 1):
            try:
                self.logger.info(f"调用模型，prompt长度: {len(text)}")
                
                # 计算token统计 - 使用更保守的估算方法
                # 对于包含日语和中文的文本，token密度更高
                estimated_input_tokens = len(text) // 2  # 更保守的估算
                max_context_length = self.config.get_max_context_length()
                
                # 动态计算 max_tokens - 充分利用模型context window
                if self.config.max_tokens > 0:
                    max_tokens = self.config.max_tokens
                else:
                    # 大幅减少安全余量，充分利用context window
                    safety_margin = 1024
                    remain = max_context_length - estimated_input_tokens - safety_margin
                    if remain < 500:
                        remain = 500
                    # 设置合理的上限，避免超出context限制
                    max_tokens = min(remain, 25000)  # 设置25000的上限
                
                self.logger.info(f"动态计算 max_tokens: {max_tokens} (基于输入长度 {len(text)}, 估算输入tokens: {estimated_input_tokens}, 模型上下文长度: {max_context_length})")
                
                # 调用模型
                result, prompt, token_meta = self._translate_with_stream(text, max_tokens)
                
                if result and result.strip():
                    # 进行质量检测
                    self.logger.info(f"对{chunk_info}进行质量检测...")
                    is_good, reason = self.quality_checker.check_translation_quality(
                        text, result, self.config.bilingual
                    )
                    
                    if is_good:
                        self.logger.info(f"{chunk_info}质量检测通过: {reason}")
                        return result, prompt, True, token_meta
                    else:
                        self.logger.warning(f"{chunk_info}质量检测失败: {reason}")
                        if attempt < self.config.retries:
                            self.logger.warning(f"质量不佳，重试{chunk_info} (尝试 {attempt + 1}/{self.config.retries})")
                            time.sleep(self.config.retry_wait)
                            continue
                        else:
                            self.logger.warning(f"{chunk_info}质量不佳但已达到最大重试次数，返回结果")
                            # 在debug模式下，质量检测失败应该被视为失败
                            success = not self.config.debug
                            return result, prompt, success, token_meta
                else:
                    self.logger.warning(f"{chunk_info}翻译结果为空，重试 (尝试 {attempt + 1}/{self.config.retries})")
                    if attempt < self.config.retries:
                        time.sleep(self.config.retry_wait)
                        continue
                    else:
                        return "", "", False, {"input_tokens": estimated_input_tokens, "output_tokens": 0, "total_tokens": estimated_input_tokens}
                        
            except Exception as e:
                self.logger.error(f"{chunk_info}重试 {attempt}/{self.config.retries}: Exception: {e}")
                if attempt < self.config.retries:
                    time.sleep(self.config.retry_wait)
                    continue
                else:
                    self.logger.error(f"{chunk_info}所有重试都失败了，最后错误: {e}")
                    return "", "", False, {"input_tokens": estimated_input_tokens, "output_tokens": 0, "total_tokens": estimated_input_tokens}
        
        return "", "", False, {"input_tokens": estimated_input_tokens, "output_tokens": 0, "total_tokens": estimated_input_tokens}
    
    def _translate_with_stream(self, text: str, max_tokens: int) -> Tuple[str, str, Dict[str, int]]:
        """流式翻译"""
        messages = self._build_messages(text)
        try:
            allowed = self._calculate_max_tokens(messages, requested_max_tokens=max_tokens, cap=None)
            max_tokens = allowed
            freq_penalty = max(self.config.frequency_penalty, 0.5) if self.config.bilingual_simple else self.config.frequency_penalty
            params = self.profile_manager.get_generation_params(
                "body",
                max_tokens=max_tokens,
                frequency_penalty=freq_penalty
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
        except BadRequestError as e:
            msg = str(e)
            if "max_tokens" not in msg and "max_completion_tokens" not in msg:
                raise
            safe_allowed = self._calculate_max_tokens(messages, requested_max_tokens=max_tokens, cap=int(max_tokens * 0.6))
            max_tokens = safe_allowed
            self.logger.warning(f"max_tokens 调整为保守值: {max_tokens} 后重试流式调用")
            retry_params = self.profile_manager.get_generation_params(
                "body",
                max_tokens=max_tokens,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=retry_params,
            )
        return self._process_translation_result(result, str(messages), max_tokens)
    
    def _process_translation_result(self, result: str, prompt: str, max_tokens: int) -> Tuple[str, str, Dict[str, int]]:
        """处理翻译结果的通用逻辑"""
        # 清理输出
        cleaned_result = clean_output_text(result)
        
        # self.logger.info(f"翻译完成，结果长度: {len(result)}")
        # self.logger.info(f"清理后长度: {len(cleaned_result)}")
        
        # 估算token使用量（streaming_handler已记录详细统计）
        token_meta = {
            "input_tokens": len(prompt) // 4,
            "output_tokens": len(result) // 4,
            "total_tokens": (len(prompt) + len(result)) // 4,
            "max_tokens": max_tokens
        }
        
        return cleaned_result, prompt, token_meta
    
    

    def _build_messages(self, text: str) -> list:
        """构建通用正文消息（对话包装）。"""
        return self._build_messages_generic(
            text=text,
            preface_path=self.config.preface_file,
            sample_path=self.config.sample_file,
            add_samples=True,
            default_preface="请将以下日语文本翻译为中文，严格逐行对照，不新增或删除换行。",
            log_label="Prompt (single user)"
        )

    def _extract_yaml_block_only(self, text: str) -> str:
        """提取首个完整的 YAML block（含 --- 分隔），避免多余内容污染。"""
        try:
            if not text:
                return text
            start = text.find("---")
            if start < 0:
                return text.strip()
            end = text.find("---", start + 3)
            if end < 0:
                # 只有起始分隔线：取到文本末尾
                return text[start:].strip()
            return text[start:end+3].strip()
        except Exception:
            return text.strip()

    def _build_messages_yaml(self, text: str) -> list:
        """构建 YAML 消息（对话包装）。"""
        return self._build_messages_generic(
            text=text,
            preface_path=(self.config.preface_yaml_file or self.config.preface_file),
            sample_path=self.config.sample_yaml_file,
            add_samples=True,
            default_preface="YAML 特例：仅翻译 title、caption 或 excerpt、series.title（若存在）以及 tags 的内容，并按“两行制”输出：先原文行，紧接着中文行；其他键直接原样保留。无论 Pixiv 还是 Fanbox，若存在 caption 或 excerpt 其中之一就翻译相应字段。tags 译文行保留 [] 与逗号，元素需写成 原词 / 中文。必须完全保持缩进、层级以及 key: 后的空格。",
            log_label="YAML Prompt (single user)"
        )

    def _build_messages_body(self, text: str) -> list:
        """构建正文消息（对话包装）。"""
        return self._build_messages_generic(
            text=text,
            preface_path=(self.config.preface_body_file or self.config.preface_file),
            sample_path=None,
            add_samples=False,
            default_preface="请将以下日语文本翻译为中文，严格逐行对照（原文行后紧跟译文），禁止省略，沿用原文引号样式，中文需使用恰当标点，不合并/不拆分/不调序。",
            log_label="Body Prompt (single user)"
        )

    def _build_messages_generic(self, text: str, preface_path: Optional[Path], sample_path: Optional[Path], add_samples: bool, default_preface: str, log_label: str) -> list:
        parts: list[str] = []
        # preface
        if preface_path and Path(preface_path).exists():
            with open(preface_path, 'r', encoding='utf-8') as f:
                parts.append(f.read().strip())
        else:
            parts.append(default_preface)
        # terminology
        if self.config.terminology_file and self.config.terminology_file.exists():
            with open(self.config.terminology_file, 'r', encoding='utf-8') as f:
                parts.append("术语对照表：\n" + f.read().strip())
        self._append_runtime_name_glossary(parts)
        # samples (optional)
        if add_samples and sample_path and Path(sample_path).exists():
            with open(sample_path, 'r', encoding='utf-8') as f:
                parts.append("示例（Few-shot）：\n" + f.read().strip())
        # wrap input
        parts.append(text)
        content = "\n\n".join(parts)
        messages = [{"role": "user", "content": content}]
        self.logger.debug(f"{log_label}:\n" + content)
        return messages

    def translate_yaml_text(self, text: str) -> Tuple[str, str, bool, Dict[str, int]]:
        """针对 YAML 段的翻译（不分块）。"""
        messages = self._build_messages_yaml(text)
        try:
            yaml_prof = self.profile_manager.get_profile("yaml")
            # 固定参数：T=0.0, top_p=1.0, freq=0.0, presence=0.0, 无重复惩罚，max_tokens=800，stop=None
            allowed = self._calculate_max_tokens(messages, requested_max_tokens=800, cap=800)
            from .streaming_handler import StreamingHandler
            params = self.profile_manager.get_generation_params(
                "yaml",
                max_tokens=allowed,
                watchdog_timeout_s=int(yaml_prof.get("watchdog_timeout_s", 180))
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            # 先从原始结果中提取首个 YAML 块，避免清洗时误删
            yaml_block = self._extract_yaml_block_only(result or "")
            # 再对提取后的 YAML 块进行温和清洗（去掉 think/围栏等）
            yaml_block_cleaned = clean_output_text(yaml_block)
            prompt = str(messages)
            meta = {
                "input_tokens": len(prompt) // 4,
                "output_tokens": len(result or "") // 4,
                "total_tokens": (len(prompt) + len(result or "")) // 4,
                "max_tokens": allowed,
            }
            return yaml_block_cleaned, prompt, True, meta
        except Exception as e:
            self.logger.error(f"YAML 翻译失败: {e}")
            return "", "", False, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def translate_yaml_kv_batch(self, kv: Dict[str, object]) -> Tuple[Dict[str, object], str, bool, Dict[str, int]]:
        """批量翻译 YAML 目标字段：仅提供目标键原值，不给整段 YAML。
        输入 kv 可包含：'title', 'caption', 'excerpt', 'series.title', 'tags'
        返回同键的译值（tags 返回 List[str]）。
        """
        # 构建最小上下文
        yaml_prof = self.profile_manager.get_profile("yaml")
        parts: list[str] = []
        # 强制性指令：限制输出为 key: value 行，避免解释/Markdown
        parts.append(
            "仅输出以下五个键的译文行，严格保持 key 与冒号空格，禁止任何额外说明/Markdown/空行：\n"
            "1) title: 原文\n   title: 中文\n"
            "2) caption: 原文\n   caption: 中文（保留 HTML 标签/链接）\n"
            "3) excerpt: 原文\n   excerpt: 中文（保留 HTML 标签/链接）\n"
            "4) series.title: 原文（在缩进下）\n   series.title: 中文\n"
            "5) tags: [a, b]\n   tags: [a / a中文, b / b中文]"
        )
        # 前言
        preface_path = self.config.preface_yaml_file or self.config.preface_file
        if preface_path and Path(preface_path).exists():
            with open(preface_path, 'r', encoding='utf-8') as f:
                parts.append(f.read().strip())
        # 术语
        if self.config.terminology_file and self.config.terminology_file.exists():
            with open(self.config.terminology_file, 'r', encoding='utf-8') as f:
                parts.append("术语对照表：\n" + f.read().strip())
        self._append_runtime_name_glossary(parts)
        # 构造用户段
        def render_tags(items: list[str]) -> str:
            return "[" + ", ".join([x for x in items]) + "]"
        lines: list[str] = []
        if isinstance(kv.get('title'), str) and kv['title'].strip():
            lines.append(f"title: {kv['title']}")
        if isinstance(kv.get('caption'), str) and kv['caption'].strip():
            lines.append(f"caption: {kv['caption']}")
        if isinstance(kv.get('excerpt'), str) and kv['excerpt'].strip():
            lines.append(f"excerpt: {kv['excerpt']}")
        if isinstance(kv.get('series.title'), str) and kv['series.title'].strip():
            lines.append(f"series.title: {kv['series.title']}")
        if isinstance(kv.get('tags'), list):
            try:
                lines.append("tags: " + render_tags([str(x) for x in kv['tags']]))
            except Exception:
                pass
        parts.append("\n".join(lines))
        content = "\n\n".join(parts)
        messages = [{"role": "user", "content": content}]
        # 调用
        try:
            # 固定参数：T=0.0, top_p=1.0, freq=0.0, presence=0.0, 无重复惩罚，max_tokens=800，stop=None
            allowed = self._calculate_max_tokens(messages, requested_max_tokens=800, cap=800)
            from .streaming_handler import StreamingHandler
            params = self.profile_manager.get_generation_params(
                "yaml",
                max_tokens=allowed,
                watchdog_timeout_s=int(yaml_prof.get("watchdog_timeout_s", 180))
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            cleaned = clean_output_text(result or "")
            # 解析：按行找 key: value / tags: [..]
            out: Dict[str, object] = {}
            for raw in cleaned.splitlines():
                line = raw.strip()
                if not line or ':' not in line:
                    continue
                k, v = line.split(':', 1)
                k = k.strip()
                v = v.strip()
                if k == 'tags' and v.startswith('[') and v.endswith(']'):
                    items = [x.strip().strip('"').strip("'") for x in v[1:-1].split(',') if x.strip()]
                    out['tags'] = items
                elif k in ('title', 'caption', 'excerpt', 'series.title'):
                    out[k] = v.strip().strip('"').strip("'")
            prompt = str(messages)
            meta = {
                "input_tokens": len(prompt) // 4,
                "output_tokens": len(result or "") // 4,
                "total_tokens": (len(prompt) + len(result or "")) // 4,
                "max_tokens": allowed,
            }
            return out, prompt, True, meta
        except Exception as e:
            self.logger.error(f"YAML 批量翻译失败: {e}")
            return {}, "", False, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def translate_body_text(self, text: str, chunk_index: Optional[int] = None) -> Tuple[str, str, bool, Dict[str, int]]:
        """正文翻译（使用 Body 专用提示；流式）。"""
        messages = self._build_messages_body(text)
        try:
            body_prof = self.profile_manager.get_profile("body")
            # 生成上限
            cap_tokens = int(body_prof.get("cap_tokens", 2000))
            allowed = self._calculate_max_tokens(messages, requested_max_tokens=cap_tokens, cap=cap_tokens)
            # 采样参数（从 profile 应用）
            temperature = float(body_prof.get("temperature", self.config.temperature))
            top_p = float(body_prof.get("top_p", self.config.top_p))
            freq_penalty = float(body_prof.get("frequency_penalty_min", self.config.frequency_penalty))
            presence_penalty = float(body_prof.get("presence_penalty", self.config.presence_penalty))
            repetition_penalty = float(body_prof.get("repetition_penalty", self.config.repetition_penalty))
            no_repeat_ngram_size = int(body_prof.get("no_repeat_ngram_size", self.config.no_repeat_ngram_size))
            stop_list = body_prof.get("stop", None)
            stop_list = None if (stop_list is None or stop_list == "" or str(stop_list).lower() == "null") else stop_list
            from .streaming_handler import StreamingHandler
            params = self.profile_manager.get_generation_params(
                "body",
                max_tokens=allowed,
                temperature=temperature,
                top_p=top_p,
                stop=stop_list,
                frequency_penalty=freq_penalty,
                presence_penalty=presence_penalty,
                repetition_penalty=repetition_penalty,
                no_repeat_ngram_size=no_repeat_ngram_size
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            cleaned, prompt, meta = self._process_translation_result(result, str(messages), allowed)
            return cleaned, prompt, True, meta
        except Exception as e:
            self.logger.error(f"正文翻译失败: {e}")
            return "", "", False, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    
    # ===== 工具方法 =====
    def _calculate_max_tokens(self, messages: list, requested_max_tokens: int = 0, cap: Optional[int] = None) -> int:
        """计算安全的max_tokens值"""
        return calculate_max_tokens_for_messages(
            messages, 
            self.config.model,
            self.config.get_max_context_length(),
            requested_max_tokens,
            cap
        )

    def _trim_previous_io(
        self,
        previous_io: Optional[Tuple[List[str], List[str]]],
    ) -> Optional[Tuple[List[str], List[str]]]:
        """根据 context_lines 限制上一批原/译对的行数，避免把整批加入 prompt。"""
        if not previous_io:
            return None
        context_limit = max(0, getattr(self.config, "context_lines", 0))
        if context_limit <= 0:
            return None
        prev_inputs, prev_outputs = previous_io
        trimmed_inputs = prev_inputs[-context_limit:] if prev_inputs else []
        trimmed_outputs = prev_outputs[-context_limit:] if prev_outputs else []
        if not trimmed_inputs:
            return None
        return trimmed_inputs, trimmed_outputs
    
    def translate_lines_simple(
        self,
        target_lines: List[str],
        previous_io: Tuple[List[str], List[str]] = None,
        start_line_number: Optional[int] = None,
        context_lines: Optional[List[str]] = None,
    ) -> Tuple[List[str], str, bool, Dict[str, int], Tuple[List[str], List[str]]]:
        """
        简化的行级翻译方法
        输入：目标行列表 + 前一次的输入输出
        输出：中文行列表 + prompt + 成功标志 + token统计 + 本次的previous_io
        """
        try:
            # 预处理：记录空白行位置，移除空白行
            non_empty_lines = []
            empty_line_positions = []
            
            for i, line in enumerate(target_lines):
                if line.strip():  # 非空白行
                    # 保存原始行（包含缩进）和去除缩进的行
                    non_empty_lines.append((line, line.strip()))
                else:  # 空白行
                    empty_line_positions.append(i)
            
            if self.logger:
                self.logger.debug(f"预处理结果：总行数{len(target_lines)}，非空白行{len(non_empty_lines)}，空白行位置{empty_line_positions}")
            
            # 构建最小化的prompt（只使用非空白行，去除缩进）
            stripped_lines = [line_stripped for _, line_stripped in non_empty_lines]
            trimmed_previous_io = self._trim_previous_io(previous_io)
            messages = self.prompt_builder.build_messages(
                target_lines=stripped_lines,
                previous_io=trimmed_previous_io,
                context_lines=context_lines,
            )
            # 可选：记录批次起始行号，便于定位（不影响功能）
            if start_line_number is not None and self.logger:
                try:
                    self.logger.debug(f"简化翻译批次起始行号: {start_line_number}")
                except Exception:
                    pass
            
            # 使用ProfileManager获取bilingual_simple参数
            max_tokens = self._estimate_simple_max_tokens(stripped_lines)
            # 为小批/逐行提供生成下限，避免被思考阶段占满
            if max_tokens is None or max_tokens < 1024:
                max_tokens = 1024
            params = self.profile_manager.get_generation_params(
                "bilingual_simple",
                max_tokens=max_tokens
            )
            
            # 调用模型
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            
            # 记录完整的原始翻译结果（debug级别）
            # if self.logger:
            #     self.logger.debug(f"原始翻译结果（{len(result)}字符）:\n{result}")
            
            # 清理思考内容
            cleaned_result = clean_output_text(result)
            # 若末尾存在完成标记行，则移除
            cleaned_result = re.sub(r"(?:\n|\r|\r\n)*\[翻译完成\]\s*$", "", cleaned_result.strip())
            
            # 记录清理后的结果（debug级别）
            # if self.logger:
            #     self.logger.debug(f"清理后翻译结果（{len(cleaned_result)}字符）：\n{cleaned_result}")
            
            # 解析结果：按行分割，过滤空行，复制原文缩进
            chinese_lines = []
            for i, line in enumerate(cleaned_result.split('\n')):
                line = line.strip()
                if line:
                    # 复制对应原文的缩进
                    if i < len(non_empty_lines):
                        original_line, _ = non_empty_lines[i]
                        # 计算原文的行首缩进（包括全角空格等）
                        leading_indent = original_line[:len(original_line) - len(original_line.lstrip())]
                        # 为翻译结果添加相同的缩进
                        indented_line = leading_indent + line
                        chinese_lines.append(indented_line)
                    else:
                        chinese_lines.append(line)
            
            # 记录解析后的行数（debug级别）
            # if self.logger:
            #     self.logger.debug(f"解析后中文行数: {len(chinese_lines)}")
            #     for i, line in enumerate(chinese_lines, 1):
            #         self.logger.debug(f"  第{i}行: {line}")
            
            # 使用QC模块检查行数对齐
            # non_empty_lines是元组列表，需要提取strip后的行
            stripped_lines = [line_stripped for _, line_stripped in non_empty_lines]
            alignment_ok, alignment_reason = self.quality_checker.check_line_alignment(stripped_lines, chinese_lines)
            if not alignment_ok:
                self.logger.warning(f"行数对齐检查失败: {alignment_reason}")
                return [], str(messages), False, token_stats, None
            
            # 后处理：在正确位置插入空白行
            final_chinese_lines = []
            chinese_index = 0
            
            for i in range(len(target_lines)):
                if i in empty_line_positions:
                    # 插入空白行
                    final_chinese_lines.append("")
                else:
                    # 插入翻译行
                    if chinese_index < len(chinese_lines):
                        final_chinese_lines.append(chinese_lines[chinese_index])
                        chinese_index += 1
                    else:
                        self.logger.error(f"翻译行数不足：期望{len(non_empty_lines)}行，实际{len(chinese_lines)}行")
                        return [], str(messages), False, token_stats, None
            
            
            # 进行质量检测（规则 + LLM），支持逐行重试策略
            try:
                original_text_for_qc = "\n".join(stripped_lines)
                translated_text_for_qc = cleaned_result
                self.logger.info("对本批次进行QC LLM检测（整块+二分降级）…")
                
                # 使用改进的QC方法（整块QC + 规则QC组合）
                qc_result, qc_reason = self.quality_checker.check_translation_quality_with_llm(
                    original_text_for_qc,
                    translated_text_for_qc
                )
                
                if not qc_result:
                    self.logger.warning(f"QC失败：{qc_reason}，返回失败让上层降级处理")
                    return [], str(messages), False, token_stats, None
                else:
                    self.logger.info(f"QC通过：{qc_reason}")
                    
            except Exception as _e:
                self.logger.warning(f"QC 调用异常，视为失败：{_e}")
                return [], str(messages), False, token_stats, None

            # 记录对照版的target_lines+final_chinese_lines
            if self.logger:
                self.logger.debug(f"对照版翻译结果：")
                for i, (orig, trans) in enumerate(zip(target_lines, final_chinese_lines)):
                    if orig.strip():  # 只记录非空白行
                        self.logger.debug(f"  第{i+1}行: {orig} -> {trans}")
                    else:
                        self.logger.debug(f"  第{i+1}行: [空白行] -> {trans}")
            
            # 构建本次的 current_io（用于下一批次的上下文）
            # 注意：input 使用 stripped_lines（字符串），output 使用 cleaned_result
            current_io = (
                stripped_lines,  # 输入行（字符串列表）
                cleaned_result.split('\n')  # 输出行（清理后的结果按行分割）
            )
            
            return final_chinese_lines, str(messages), True, token_stats, current_io
        
        except Exception as e:
            self.logger.error(f"简化翻译失败: {e}")
            return [], "", False, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, None

    
    def _estimate_simple_max_tokens(self, target_lines: List[str]) -> int:
        """估算简化翻译的max_tokens；token_estimator=simple 时跳过 transformers 依赖。"""
        if getattr(self.config, "token_estimator", "auto") == "simple":
            estimated_output = len(target_lines) * 150
            return min(estimated_output + 1000, 6000)
        
        from ..utils.text.token_analyzer import get_token_analyzer
        
        try:
            analyzer = get_token_analyzer(self.config.model)
            estimation = analyzer.estimate_batch_tokens(target_lines)
            
            # 使用建议的max_tokens，但不超过6000
            suggested_max = estimation["suggested_max_tokens"]
            return min(suggested_max, 6000)
            
        except Exception as e:
            self.logger.warning(f"Token估算失败，使用回退方法: {e}")
            # 回退到简单估算
            estimated_output = len(target_lines) * 150
            return min(estimated_output + 1000, 6000)
