#!/usr/bin/env python3
"""
翻译质量检测模块
"""

import re
import json
from typing import Tuple, Optional
from openai import OpenAI
from openai import BadRequestError

from .config import TranslationConfig
from .streaming_handler import StreamingHandler
from .profile_manager import ProfileManager, GenerationParams


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
        
        # 检查长度比例
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
        
        # 检查日语字符比例（双语模式更宽松）
        japanese_chars = len(re.findall(r'[ひらがなカタカナ一-龯]', translated_text))
        total_chars = len(translated_text)
        
        if bilingual:
            # 双语模式：允许更多日语字符（可能是原文）
            if japanese_chars / total_chars > 0.8:
                return False, "日语字符过多（双语模式）"
        else:
            # 单语模式：日语字符应该很少
            if japanese_chars / total_chars > 0.3:
                return False, "日语字符过多（单语模式）"
        
        # 检查重复字符
        if self._has_excessive_repetition(translated_text):
            return False, "包含过多重复字符"

        # 检测中文长串无标点（句中标点缺失风险，仅作告警判定）
        try:
            import re as _re
            # 抽样检查最近 1200 字符
            tail = translated_text[-1200:] if len(translated_text) > 1200 else translated_text
            # 匹配长串中文（含字母数字）但缺少常见分隔标点
            runs = _re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{80,}", tail)
            if runs:
                # 如果这些长串内不包含任何分隔标点，则视为不佳
                if not _re.search(r"[，、；。！？……]", ''.join(runs)):
                    return False, "中文句中疑似缺少分隔标点"
        except Exception:
            pass
        
        return True, "基础检测通过"
    
    def check_translation_quality_with_llm(self, original_text: str, translated_text: str, bilingual: bool = False) -> Tuple[bool, str]:
        """
        使用大模型进行质量检测
        
        Args:
            original_text: 原文
            translated_text: 译文
            bilingual: 是否为双语模式
            
        Returns:
            (是否通过, 失败原因)
        """
        if self.config.no_llm_check:
            return True, "跳过LLM检测"
        
        try:
            # 提取尾部片段（bilingual 模式下译文段取更长片段；强调关注中后段到结尾）
            if bilingual:
                orig_tail_len = 400
                tran_tail_len = 800
            else:
                orig_tail_len = 500
                tran_tail_len = 500

            original_tail = original_text[-orig_tail_len:] if len(original_text) > orig_tail_len else original_text
            translated_tail = translated_text[-tran_tail_len:] if len(translated_text) > tran_tail_len else translated_text

            messages = self._build_quality_messages(original_tail, translated_tail, bilingual)
            # 分开记录 system 与 user，避免单行过长
            try:
                system_content = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
                user_content = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
            except Exception:
                system_content, user_content = "", ""
            if self.logger:
                self.logger.debug("QC System prompt:\n" + system_content)
                self.logger.debug("QC User prompt:\n" + user_content)

            # 使用流式输出进行质量检测（system+user）
            result = self._quality_check_with_stream(messages)

            cleaned = self._clean_quality_output(result)
            verdict = self._extract_verdict(cleaned)

            mode_text = "bilingual对照模式" if bilingual else "单语模式"
            if verdict == "GOOD":
                return True, f"大模型评估：{mode_text}最后部分翻译质量良好"
            elif verdict == "BAD":
                return False, f"大模型评估：{mode_text}最后部分翻译质量不佳"
            else:
                # 回退：无法解析明确结论时，保守为不佳并附上简短截断说明
                short = (cleaned[:120] + '...') if len(cleaned) > 120 else cleaned
                return False, f"大模型评估：{mode_text}结论不明（{short}）"
                
        except Exception as e:
            return False, f"LLM质量检测失败: {str(e)}"
    
    def _quality_check_with_stream(self, messages: list) -> str:
        """使用流式输出进行质量检测（system+user 消息结构）"""
        try:
            # 使用统一的流式输出处理器
            max_tokens = getattr(self.config, 'quality_max_tokens', 0)
            from .streaming_handler import StreamingHandler
            params = self.profile_manager.get_generation_params(
                "quality_check",
                max_tokens=max_tokens if max_tokens > 0 else 0
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

    def _build_quality_messages(self, original_tail: str, translated_tail: str, bilingual: bool) -> list:
        """构建质量检测消息：system=规范+few-shot；user=待评片段。"""
        mode_text = "bilingual对照模式（原文-译文交替）" if bilingual else "单语模式"

        system_parts = []
        system_parts.append(
            (
                f"你是严格的翻译质检员。输入是{mode_text}的尾段片段。\n"
                "- 片段开头可能是机械截断，判断重点放在片段的中后段直到结尾。\n"
                "- 仅在最后一行输出结论：GOOD 或 BAD（大写）。不要附加任何解释。\n"
                "- 检查：行对齐/错配、含义对应/明显误译、结尾是否完整无截断。\n"
            )
        )
        # few-shot（用User/Assistant标注）
        system_parts.append(
            (
                "示例 A\n"
                "User:\n<原文尾段>...\n<译文尾段>...\n"
                "Assistant:\nGOOD\n\n"
                "示例 B\n"
                "User:\n<原文尾段>...\n<译文尾段（结尾截断/错配）>...\n"
                "Assistant:\nBAD\n"
            )
        )
        system_content = "\n\n".join(system_parts)

        if bilingual:
            user_content = (
                f"原文尾段（可能截断开头）：\n{original_tail}\n\n"
                f"对照译文尾段（可能截断开头）：\n{translated_tail}"
            )
        else:
            user_content = (
                f"原文尾段（可能截断开头）：\n{original_tail}\n\n"
                f"译文尾段（可能截断开头）：\n{translated_tail}"
            )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

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
    
    def _has_excessive_repetition(self, text: str) -> bool:
        """检查是否有过多重复字符（更宽松的检测）"""
        if len(text) < 10:
            return False
        
        # 检查单字符重复（更宽松：连续12个相同字符）
        for char in set(text):
            if char * 12 in text:  # 从8个提高到12个
                return True
        
        # 检查短片段重复（更宽松：同一片段出现超过5次）
        for i in range(len(text) - 30):
            segment = text[i:i+15]  # 从10个字符提高到15个字符
            if text.count(segment) > 5:  # 从3次提高到5次
                return True
        
        return False
