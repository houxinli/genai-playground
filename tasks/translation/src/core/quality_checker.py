#!/usr/bin/env python3
"""
翻译质量检测模块
"""

import re
import json
from pathlib import Path
from typing import Tuple, Optional
from openai import OpenAI
from openai import BadRequestError

from .config import TranslationConfig
from .streaming_handler import StreamingHandler
from .profile_manager import ProfileManager, GenerationParams
from .logger import UnifiedLogger


class QualityChecker:
    """翻译质量检测器"""
    
    def __init__(self, config: TranslationConfig, logger=None):
        """
        初始化质量检测器
        
        Args:
            config: 翻译配置
            logger: 日志器
        """
        self.config = config
        self.logger = logger
        self.client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")
        self.profile_manager = ProfileManager(config.profiles_file)
        self.streaming_handler = StreamingHandler(self.client, logger, config, self.profile_manager)
    
    def check_translation_quality_basic(self, original_text: str, translated_text: str, bilingual: bool = False) -> Tuple[bool, str]:
        """
        基础质量检测（规则-based）
        
        Args:
            original_text: 原文
            translated_text: 译文
            bilingual: 是否为双语模式
            
        Returns:
            (是否通过, 失败原因)
        """
        if not translated_text or not translated_text.strip():
            return False, "翻译结果为空"
        
        # 检查长度比例（utils优先）
        try:
            from ..utils.validation.length_check import validate_length_ratio
            ok_len, reason_len = validate_length_ratio(original_text, translated_text, 0.3, 3.0)
            if not ok_len:
                return False, reason_len
        except Exception:
            if len(translated_text) < len(original_text) * 0.3:
                return False, "翻译结果过短"
            if len(translated_text) > len(original_text) * 3:
                return False, "翻译结果过长"
        
        # 检查错误模式
        error_patterns = [
            "（以下省略）",
            "（省略）",
            "翻译失败",
            "无法翻译",
            "ERROR",
            "error"
        ]
        
        for pattern in error_patterns:
            if pattern in translated_text:
                return False, f"包含错误模式: {pattern}"
        
        # 检查日语字符比例（仅以假名判定，避免将中文汉字误判为日文汉字）
        # Hiragana: \u3040-\u309F, Katakana: \u30A0-\u30FF, 半角片假名: \uFF66-\uFF9D
        japanese_chars = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9D]', translated_text))
        total_chars = len(translated_text)
        
        if bilingual:
            # 双语模式：允许更多日语字符（可能是原文）
            if japanese_chars / total_chars > 0.8:
                return False, "日语字符过多（双语模式）"
        else:
            # 单语模式：日语字符应该很少
            if japanese_chars / total_chars > 0.3:
                return False, "日语字符过多（单语模式）"
        
        # 检查重复字符（utils优先）
        try:
            from ..utils.validation.repetition_check import has_excessive_repetition
            if has_excessive_repetition(translated_text):
                return False, "包含过多重复字符"
        except Exception:
            if self._has_excessive_repetition(translated_text):
                return False, "包含过多重复字符"

        # 检查中文复制日语片段（启发式规则迁移到 utils）
        try:
            from ..utils.validation.jp_copy_check import has_chinese_copying_japanese
            if has_chinese_copying_japanese(original_text, translated_text, bilingual):
                return False, "中文部分直接复制了日语片段"
        except Exception:
            # 回退到内部旧实现（保持兼容）
            if self._has_chinese_copying_japanese(original_text, translated_text, bilingual):
                return False, "中文部分直接复制了日语片段"

        # 检测中文长串无标点（utils优先）
        try:
            from ..utils.validation.cjk_punctuation_check import validate_cjk_separators
            ok_punc, reason_punc = validate_cjk_separators(translated_text)
            if not ok_punc:
                return False, reason_punc
        except Exception:
            pass
        
        return True, "基础检测通过"
    
    def check_translation_quality_with_llm(self, original_text: str, translated_text: str, bilingual: bool = False) -> Tuple[bool, str]:
        """
        使用大模型进行质量检测（逐行检查版）。
        """
        if self.config.no_llm_check:
            return True, "跳过LLM检测"
        
        try:
            # 逐行对齐检查
            orig_lines = [ln.strip() for ln in original_text.split('\n')]
            tran_lines = [ln.strip() for ln in translated_text.split('\n')]
            # 仅针对非空行进行一一对应检查
            packed = [(o, t) for o, t in zip(orig_lines, tran_lines) if o or t]

            for idx, (orig_line, tran_line) in enumerate(packed, 1):
                # 构造逐行消息
                messages = self._build_quality_messages(orig_line, tran_line, bilingual)
                # 可选记录
                try:
                    system_content = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
                    user_content = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
                except Exception:
                    system_content, user_content = "", ""
                if self.logger:
                    # 仅写文件，避免刷屏
                    self.logger.debug(f"QC System prompt (line {idx}):\n" + system_content, mode=UnifiedLogger.LogMode.FILE)
                    self.logger.debug(f"QC User prompt (line {idx}):\n" + user_content, mode=UnifiedLogger.LogMode.FILE)

                result = self._quality_check_with_stream(messages)
                cleaned = self._clean_quality_output(result)
                verdict = self._extract_verdict(cleaned)
                if verdict != "GOOD":
                    return False, f"LLM逐行质检失败：第{idx}行判定为{verdict or 'UNSURE'}"

            return True, "LLM逐行质检通过"
                
        except Exception as e:
            return False, f"LLM质量检测失败: {str(e)}"
    
    def _quality_check_with_stream(self, messages: list) -> str:
        """使用流式输出进行质量检测（system+user 消息结构）"""
        try:
            # 使用统一的流式输出处理器
            max_tokens = getattr(self.config, 'quality_max_tokens', 0)
            # 设定一个合理下限，避免QC在模型思考阶段被截断
            if max_tokens <= 0:
                max_tokens = 4096
            from .streaming_handler import StreamingHandler
            params = self.profile_manager.get_generation_params(
                "quality_check",
                max_tokens=max_tokens if max_tokens > 0 else 0,
                stop=[],
            )
            result, token_stats = self.streaming_handler.stream_with_params(
                model=self.config.model,
                messages=messages,
                params=params,
            )
            
            # 记录token使用情况
            self.logger.info(f"质量检测完成，Token使用情况: {token_stats}")
            
            return result.strip()
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"质量检测流式调用失败: {e}")
            raise

    def _build_quality_messages_block(self, original_lines: list[str], translated_lines: list[str], bilingual: bool) -> list:
        """整块QC：将一批原文/译文行打包到同一条user消息中，期望单词（GOOD/BAD）裁决。"""
        base = Path(__file__).parent.parent.parent / "data"
        preface_path = base / "preface_qc.txt"
        sample_path = base / "samples" / "sample_qc.txt"

        system_content = "你是翻译质检员。仅输出一个词（GOOD 或 BAD）。不要解释。"
        try:
            if preface_path.exists():
                system_content = preface_path.read_text(encoding='utf-8').strip()
        except Exception:
            pass

        messages = [{"role": "system", "content": system_content}]

        # 复用逐行few-shot
        try:
            if sample_path.exists():
                raw = sample_path.read_text(encoding='utf-8')
                lines = [ln.rstrip('\n') for ln in raw.splitlines()]
                current_role: str | None = None
                buffer: list[str] = []
                def flush():
                    nonlocal buffer, current_role
                    if current_role and buffer:
                        content = '\n'.join(buffer).strip()
                        if content:
                            messages.append({"role": current_role, "content": content})
                    buffer = []
                for ln in lines:
                    low = ln.strip().lower()
                    if low.startswith('user:'):
                        flush(); current_role = 'user'; rem = ln[5:].lstrip();
                        if rem: buffer.append(rem); continue
                    if low.startswith('assistant:'):
                        flush(); current_role = 'assistant'; rem = ln[10:].lstrip();
                        if rem: buffer.append(rem); continue
                    buffer.append(ln)
                flush()
        except Exception:
            pass

        # 当前整块内容：编号对齐
        def number_lines(ls: list[str]) -> str:
            buf = []
            for idx, t in enumerate(ls, 1):
                buf.append(f"{idx}. {t}")
            return '\n'.join(buf)

        user_content = f"原文：\n{number_lines(original_lines)}\n\n译文：\n{number_lines(translated_lines)}"
        messages.append({"role": "user", "content": user_content})
        return messages

    def check_translation_quality_block(self, original_text: str, translated_text: str, bilingual: bool = False) -> Tuple[bool, str]:
        """整块质检：一次性对当前批次所有行进行裁决，输出单词（GOOD/BAD）。"""
        if self.config.no_llm_check:
            return True, "跳过LLM检测"
        try:
            orig_lines = [ln.strip() for ln in original_text.split('\n') if ln.strip()]
            tran_lines = [ln.strip() for ln in translated_text.split('\n') if ln.strip()]
            # 对齐到最短长度，避免越界
            n = min(len(orig_lines), len(tran_lines))
            orig_lines = orig_lines[:n]
            tran_lines = tran_lines[:n]
            messages = self._build_quality_messages_block(orig_lines, tran_lines, bilingual)
            # 可选记录
            try:
                system_content = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
                user_content = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
            except Exception:
                system_content, user_content = "", ""
            if self.logger:
                self.logger.debug("QC System prompt (block):\n" + system_content, mode=UnifiedLogger.LogMode.FILE)
                self.logger.debug("QC User prompt (block):\n" + user_content, mode=UnifiedLogger.LogMode.FILE)
            result = self._quality_check_with_stream(messages)
            cleaned = self._clean_quality_output(result)
            verdict = self._extract_verdict(cleaned)
            return (verdict == "GOOD"), ("LLM整块质检: " + (verdict or 'UNSURE'))
        except Exception as e:
            return False, f"LLM质量检测失败: {str(e)}"

    def check_translation_quality_block_with_bisect(self, original_text: str, translated_text: str, bilingual: bool = False, min_block: int = 10) -> Tuple[bool, str]:
        """整块QC（二分降级）：
        - 先整块QC
        - 失败则二分（或多次二分）到阈值min_block，再逐行QC兜底
        """
        try:
            ok, reason = self.check_translation_quality_block(original_text, translated_text, bilingual)
            if ok:
                return ok, reason
            # 二分递归
            orig_lines = [ln.strip() for ln in original_text.split('\n') if ln.strip()]
            tran_lines = [ln.strip() for ln in translated_text.split('\n') if ln.strip()]
            n = min(len(orig_lines), len(tran_lines))
            if n <= min_block:
                return self.check_translation_quality(original_text, translated_text, bilingual)
            mid = n // 2
            left_ok, left_reason = self.check_translation_quality_block_with_bisect('\n'.join(orig_lines[:mid]), '\n'.join(tran_lines[:mid]), bilingual, min_block)
            right_ok, right_reason = self.check_translation_quality_block_with_bisect('\n'.join(orig_lines[mid:]), '\n'.join(tran_lines[mid:]), bilingual, min_block)
            return (left_ok and right_ok), f"bisect: left={left_reason}, right={right_reason}"
        except Exception as e:
            return False, f"LLM质量检测失败: {str(e)}"

    def _build_quality_messages(self, original_line: str, translated_line: str, bilingual: bool) -> list:
        """从外部preface_qc与few-shot文件构建QC消息；逐行输入。"""
        base = Path(__file__).parent.parent.parent / "data"
        preface_path = base / "preface_qc.txt"
        sample_path = base / "samples" / "sample_qc.txt"

        system_content = "你是翻译质检员。仅输出一个词（GOOD 或 BAD）。不要解释。"
        try:
            if preface_path.exists():
                system_content = preface_path.read_text(encoding='utf-8').strip()
        except Exception:
            pass

        messages = [{"role": "system", "content": system_content}]

        # 追加few-shot（多轮对话，保证格式与下方user一致）
        try:
            if sample_path.exists():
                raw = sample_path.read_text(encoding='utf-8')
                lines = [ln.rstrip('\n') for ln in raw.splitlines()]
                current_role: str | None = None
                buffer: list[str] = []
                parsed: list[dict] = []

                def flush() -> None:
                    nonlocal buffer, current_role
                    if current_role and buffer:
                        content = '\n'.join(buffer).strip()
                        if content:
                            parsed.append({"role": current_role, "content": content})
                    buffer = []

                for ln in lines:
                    low = ln.strip().lower()
                    if low.startswith('user:'):
                        flush()
                        current_role = 'user'
                        remainder = ln[5:].lstrip()
                        if remainder:
                            buffer.append(remainder)
                        continue
                    if low.startswith('assistant:'):
                        flush()
                        current_role = 'assistant'
                        remainder = ln[10:].lstrip()
                        if remainder:
                            buffer.append(remainder)
                        continue
                    buffer.append(ln)
                flush()

                # 规范化 few-shot：严格 user(含“原文/译文”) -> assistant(仅 GOOD/BAD)
                normalized: list[dict] = []
                i = 0
                while i < len(parsed):
                    blk = parsed[i]
                    if blk.get('role') == 'user' and ('原文' in blk.get('content','')) and ('译文' in blk.get('content','')):
                        user_blk = blk
                        # 寻找下一个 assistant GOOD/BAD
                        j = i + 1
                        verdict_blk = None
                        while j < len(parsed):
                            cand = parsed[j]
                            if cand.get('role') == 'assistant':
                                up = cand.get('content','').strip().upper()
                                if up in ('GOOD','BAD'):
                                    verdict_blk = {"role": "assistant", "content": up}
                                    break
                            j += 1
                        normalized.append({"role": 'user', "content": user_blk.get('content','')})
                        if verdict_blk is not None:
                            normalized.append(verdict_blk)
                            i = j + 1
                        else:
                            i += 1
                    else:
                        i += 1

                messages.extend(normalized)
        except Exception:
            pass

        # 当前逐行待检内容
        if bilingual:
            user_content = f"原文：\n{original_line}\n\n译文：\n{translated_line}"
        else:
            user_content = f"原文：\n{original_line}\n\n译文：\n{translated_line}"

        messages.append({"role": "user", "content": user_content})
        return messages

    def _clean_quality_output(self, text: str) -> str:
        """移除大模型的思维/标记等噪声，得到判定可读文本。"""
        import re
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        return cleaned.strip()

    def _extract_verdict(self, text: str) -> str:
        """从输出中提取最终结论（取最后一个 GOOD/BAD）。"""
        import re
        matches = re.findall(r"\b(GOOD|BAD)\b", text.upper())
        return matches[-1] if matches else ""
    
    def check_translation_quality(self, original_text: str, translated_text: str, bilingual: bool = False) -> Tuple[bool, str]:
        """
        综合质量检测
        
        Args:
            original_text: 原文
            translated_text: 译文
            bilingual: 是否为双语模式
            
        Returns:
            (是否通过, 失败原因)
        """
        # 先进行基础检测
        is_good, reason = self.check_translation_quality_basic(original_text, translated_text, bilingual)
        if not is_good:
            return False, reason
        
        # 如果基础检测通过，进行LLM检测
        return self.check_translation_quality_with_llm(original_text, translated_text, bilingual)

    def check_yaml_quality_rules(self, original_yaml_block: str, translated_yaml_block: str) -> Tuple[bool, str]:
        """YAML 规则检测：
        - 仅 title/caption/tags/series.title 的行出现“双行对照”（原文行后紧跟译文行）。
        - 其他 YAML 行保持单行原文；分隔线 '---' 保留。
        - tags 译文行：保留 [] 与逗号，元素使用“原词 / 中文”映射；顺序不变；R-18 等固定标记不翻。
        - key/冒号/空格、缩进与层级与原文一致；不新增/删改键。
        返回 (是否通过, 原因)。
        """
        try:
            if not translated_yaml_block or not translated_yaml_block.strip():
                return False, "译文为空"
            # 基本结构：以 '---' 开始
            if not translated_yaml_block.strip().startswith('---'):
                return False, "缺少起始分隔线---"
            # 简单逐行校验
            orig_lines = [ln.rstrip('\n') for ln in original_yaml_block.splitlines()]
            tran_lines = [ln.rstrip('\n') for ln in translated_yaml_block.splitlines()]
            # 允许双行对照导致行数不同，这里做模式规则校验
            allowed_keys = {"title", "caption", "tags", "series.title"}

            def is_key_line(line: str, key: str) -> bool:
                return line.lstrip().startswith(f"{key}:")

            # 遍历原 YAML，按键类型期望译文行数
            i = 0
            j = 0
            n = len(orig_lines)
            m = len(tran_lines)
            # 跳过第一行 '---'
            if i < n and orig_lines[i].strip() == '---':
                i += 1
            if j < m and tran_lines[j].strip() == '---':
                j += 1
            while i < n:
                orig = orig_lines[i]
                # series.title 需要上下文判断
                key_is_series_title = False
                stripped = orig.lstrip()
                if stripped.startswith('series:'):
                    # 进入 series 块，逐行复制到下一个非缩进行
                    i += 1
                    # 在译文中必须同样进入 series: 单行
                    if j >= m or tran_lines[j].lstrip() != 'series:':
                        return False, "series 块应保持单行键名一致"
                    j += 1
                    # 读取 series 子项
                    while i < n and (orig_lines[i].startswith('  ') or orig_lines[i].startswith('\t')):
                        sub = orig_lines[i]
                        if sub.lstrip().startswith('title:'):
                            # 检查series.title是否为空
                            title_value = sub.split(':', 1)[1].strip()
                            if not title_value:
                                # 空值：只期望单行原样保留
                                if j >= m or tran_lines[j].strip() != sub.strip():
                                    return False, "series.title 空值需原样保留"
                                j += 1
                            else:
                                # 非空值：期望两行（原+译）
                                if j + 1 >= m:
                                    return False, "series.title 缺少双行对照"
                                if tran_lines[j].strip() != sub.strip():
                                    return False, "series.title 首行需原样保留"
                                # 粗略检查译文行仍以 'title:' 开头
                                if not tran_lines[j+1].lstrip().startswith('title: '):
                                    return False, "series.title 译文行需保持 key 与冒号空格"
                                j += 2
                        else:
                            # 非 title: 子项必须单行原样
                            if j >= m or tran_lines[j].strip() != sub.strip():
                                return False, "series 其他子项必须原样单行"
                            j += 1
                        i += 1
                    continue

                # 非 series 块
                if stripped.startswith('title:') or stripped.startswith('caption:') or stripped.startswith('tags:'):
                    # 期望两行（原+译）
                    if j + 1 >= m:
                        return False, f"{stripped.split(':',1)[0]} 缺少双行对照"
                    if tran_lines[j].strip() != orig.strip():
                        return False, f"{stripped.split(':',1)[0]} 首行需原样保留"
                    # 译文 key 保持
                    key = stripped.split(':',1)[0]
                    if not tran_lines[j+1].lstrip().startswith(f"{key}: "):
                        return False, f"{key} 译文行需保持 key 与冒号空格"
                    # tags 特殊格式粗检
                    if key == 'tags':
                        if '[' not in tran_lines[j+1] or ']' not in tran_lines[j+1]:
                            return False, "tags 译文行需保留方括号结构"
                        if ',' not in tran_lines[j+1]:
                            return False, "tags 元素需用逗号分隔"
                    j += 2
                else:
                    # 其他 YAML 行必须单行原样
                    if j >= m or tran_lines[j].strip() != orig.strip():
                        return False, "非可译字段的 YAML 行必须原样单行"
                    j += 1
                i += 1
            return True, "YAML 规则检测通过"
        except Exception as e:
            return False, f"YAML 规则检测异常: {e}"
    
    # 旧的本地实现已迁移到 utils/validation 模块
