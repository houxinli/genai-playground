"""
统一的Prompt构建器
基于bilingual-simple的最佳实践，提供统一的prompt构建接口
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from .config import PromptConfig, create_config


class PromptBuilder:
    """统一的Prompt构建器"""
    
    def __init__(self, config: PromptConfig):
        """
        初始化Prompt构建器
        
        Args:
            config: 配置对象，包含所有必要的配置信息
        """
        self.config = config
    
    def build_messages(
        self,
        target_lines: List[str],
        translated_lines: Optional[List[str]] = None,
        previous_io: Optional[Tuple[List[str], List[str]]] = None,
        context_lines: Optional[List[str]] = None,
        **kwargs
    ) -> List[Dict[str, str]]:
        """
        构建多轮对话消息
        
        Args:
            target_lines: 目标行列表（原文）
            translated_lines: 译文行列表（QC和增强模式需要）
            previous_io: 前一次的输入输出 (input_lines, output_lines)
            context_lines: 上下文行列表
            **kwargs: 其他参数
            
        Returns:
            消息列表
        """
        config = self.config
        messages = []
        
        # 1. 构建系统消息
        system_content = self._build_system_content(config)
        messages.append({"role": "system", "content": system_content})
        
        # 2. 添加few-shot示例
        few_shot_messages = self._build_few_shot_messages(config)
        messages.extend(few_shot_messages)
        
        # 3. 添加上下文（如果支持）
        if config.support_context and context_lines:
            context_messages = self._build_context_messages(context_lines, config)
            messages.extend(context_messages)
        
        # 4. 添加前一次的输入输出（如果支持）
        if config.support_previous_io and previous_io:
            prev_messages = self._build_previous_io_messages(previous_io, config)
            messages.extend(prev_messages)
        
        # 5. 添加当前目标行
        current_messages = self._build_current_messages(target_lines, translated_lines, config, **kwargs)
        messages.extend(current_messages)
        
        return messages
    
    def _build_system_content(self, config: PromptConfig) -> str:
        """构建系统消息内容"""
        # 读取preface文件
        preface_path = config.data_dir / config.preface_file
        if preface_path.exists():
            with open(preface_path, 'r', encoding='utf-8') as f:
                system_content = f.read().strip()
        else:
            # 默认内容
            system_content = self._get_default_system_content(config.mode)
        
        # 添加术语表（如果有）
        if config.terminology_file:
            terminology_path = config.data_dir / config.terminology_file
            if terminology_path.exists():
                with open(terminology_path, 'r', encoding='utf-8') as f:
                    terminology = f.read().strip()
                    system_content += f"\n\n术语对照表：\n{terminology}"
        
        return system_content
    
    def _build_few_shot_messages(self, config: PromptConfig) -> List[Dict[str, str]]:
        """构建few-shot示例消息"""
        messages = []
        
        # 读取sample文件
        sample_path = config.data_dir / config.sample_file
        if not sample_path.exists():
            return messages
        
        with open(sample_path, 'r', encoding='utf-8') as f:
            sample_content = f.read().strip()
        
        # 解析多轮对话格式
        messages = self._parse_sample_content(sample_content, config)
        
        return messages
    
    def _parse_sample_content(self, content: str, config: PromptConfig) -> List[Dict[str, str]]:
        """解析sample文件内容"""
        messages = []
        lines = content.split('\n')
        
        current_role = None
        current_content: List[str] = []
        user_no = 1
        assistant_no = 1
        last_user_block_start = 1
        
        def flush_current():
            nonlocal user_no, assistant_no, last_user_block_start, current_role, current_content
            if current_role and current_content:
                # 检查内容是否已经有行号
                has_line_numbers = any(line.strip() and re.match(r'^\d+\.\s+', line.strip()) for line in current_content)
                
                if has_line_numbers:
                    # 如果已经有行号，直接使用
                    content_block = '\n'.join(current_content).strip()
                else:
                    # 如果没有行号，添加行号
                    numbered = self._add_line_numbers(current_content, current_role, user_no, assistant_no, last_user_block_start)
                    content_block = '\n'.join(numbered).strip()
                
                # 添加结束标记（如果配置要求）
                if config.use_end_marker and current_role.lower() == 'assistant':
                    content_block += f"\n{config.end_marker}"
                
                messages.append({"role": current_role.lower(), "content": content_block})
                
                # 更新计数器
                if current_role.lower() == 'user':
                    user_no += len(current_content)
                    last_user_block_start = user_no - len(current_content)
                else:
                    assistant_no += len(current_content)
                
                current_content = []
        
        # 解析内容
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检查角色标记
            if line.startswith('User:'):
                flush_current()
                current_role = "user"
                continue
            elif line.startswith('Assistant:'):
                flush_current()
                current_role = "assistant"
                continue
            
            # 普通内容行
            if current_role is None:
                current_role = "user"
            current_content.append(line)
        
        flush_current()
        
        return messages
    
    def _add_line_numbers(
        self, 
        content: List[str], 
        role: str, 
        user_no: int, 
        assistant_no: int, 
        last_user_block_start: int
    ) -> List[str]:
        """为内容添加行号"""
        if role.lower() == 'user':
            return [f"{user_no + i}. {line}" for i, line in enumerate(content)]
        else:
            # assistant与上一用户块对齐编号
            return [f"{last_user_block_start + i}. {line}" for i, line in enumerate(content)]
    
    def _build_context_messages(self, context_lines: List[str], config: PromptConfig) -> List[Dict[str, str]]:
        """构建上下文消息"""
        if not context_lines:
            return []
        
        # 限制上下文行数
        limited_context = context_lines[-config.max_context_lines:] if config.max_context_lines > 0 else context_lines
        
        # 为上下文添加行号
        numbered_context = [f"{i+1}. {line}" for i, line in enumerate(limited_context)]
        
        return [{"role": "user", "content": "\n".join(numbered_context)}]
    
    def _build_previous_io_messages(self, previous_io: Tuple[List[str], List[str]], config: PromptConfig) -> List[Dict[str, str]]:
        """构建前一次输入输出的消息"""
        input_lines, output_lines = previous_io
        if not input_lines or not output_lines:
            return []
        
        messages = []
        
        # 根据模式构建不同的输入格式
        if config.mode == "enhancement":
            # 增强模式：使用"原文 + 现译"格式
            if config.use_line_numbers:
                numbered_input = []
                for i, (original, translated) in enumerate(zip(input_lines, output_lines)):
                    numbered_input.append(f"{i+1}. 原文: {original}")
                    numbered_input.append(f"{i+1}. 现译: {translated}")
            else:
                numbered_input = []
                for original, translated in zip(input_lines, output_lines):
                    numbered_input.append(f"原文: {original}")
                    numbered_input.append(f"现译: {translated}")
        else:
            # 其他模式：使用原始格式
            if config.use_line_numbers:
                numbered_input = [f"{i+1}. {line}" for i, line in enumerate(input_lines)]
            else:
                numbered_input = input_lines
        
        messages.append({"role": "user", "content": "\n".join(numbered_input)})
        
        # 输出消息
        if config.use_line_numbers:
            numbered_output = [f"{i+1}. {line}" for i, line in enumerate(output_lines)]
        else:
            numbered_output = output_lines
        
        content = "\n".join(numbered_output)
        if config.use_end_marker:
            content += f"\n{config.end_marker}"
        
        messages.append({"role": "assistant", "content": content})
        
        return messages
    
    def _build_current_messages(self, target_lines: List[str], translated_lines: Optional[List[str]], config: PromptConfig, **kwargs) -> List[Dict[str, str]]:
        """构建当前目标行的消息"""
        if not target_lines:
            return []
        
        # 根据模式构建不同的消息格式
        if config.mode in ["qc"]:
            return self._build_qc_messages(target_lines, translated_lines, config, **kwargs)
        elif config.mode in ["enhancement", "enhanced"]:
            return self._build_enhancement_messages(target_lines, translated_lines, config, **kwargs)
        else:
            return self._build_translation_messages(target_lines, config, **kwargs)
    
    def _build_translation_messages(self, target_lines: List[str], config: PromptConfig, **kwargs) -> List[Dict[str, str]]:
        """构建翻译模式的消息"""
        if config.use_line_numbers:
            numbered_lines = [f"{i+1}. {line}" for i, line in enumerate(target_lines)]
        else:
            numbered_lines = target_lines
        
        return [{"role": "user", "content": "\n".join(numbered_lines)}]
    
    def _build_qc_messages(self, target_lines: List[str], translated_lines: Optional[List[str]], config: PromptConfig, **kwargs) -> List[Dict[str, str]]:
        """构建QC模式的消息"""
        # QC模式需要原文和译文对
        if translated_lines and len(translated_lines) == len(target_lines):
            content_lines = []
            for i, (orig, trans) in enumerate(zip(target_lines, translated_lines)):
                if config.use_line_numbers:
                    content_lines.append(f"{i+1}. 原文: {orig}")
                    content_lines.append(f"{i+1}. 译文: {trans}")
                else:
                    content_lines.append(f"原文: {orig}")
                    content_lines.append(f"译文: {trans}")
                if i < len(target_lines) - 1:
                    content_lines.append("")  # 空行分隔
            
            return [{"role": "user", "content": "\n".join(content_lines)}]
        else:
            # 回退到普通格式
            return self._build_translation_messages(target_lines, config, **kwargs)
    
    def _build_enhancement_messages(self, target_lines: List[str], translated_lines: Optional[List[str]], config: PromptConfig, **kwargs) -> List[Dict[str, str]]:
        """构建增强模式的消息"""
        # 增强模式需要原文和现译
        if translated_lines and len(translated_lines) == len(target_lines):
            content_lines = []
            
            # 获取规则检测结果（如果提供）
            rule_issues = kwargs.get('rule_issues', [])
            
            for i, (orig, curr) in enumerate(zip(target_lines, translated_lines)):
                if config.use_line_numbers:
                    content_lines.append(f"{i+1}. 原文: {orig}")
                    content_lines.append(f"{i+1}. 现译: {curr}")
                else:
                    content_lines.append(f"原文: {orig}")
                    content_lines.append(f"现译: {curr}")
                
                # 添加规则检测标记（如果有问题）
                if i < len(rule_issues) and rule_issues[i]:
                    content_lines.append(f"   规则检测: {rule_issues[i]}")
                
                content_lines.append("")  # 空行分隔
            
            return [{"role": "user", "content": "\n".join(content_lines)}]
        else:
            # 回退到普通格式
            return self._build_translation_messages(target_lines, config, **kwargs)
    
    def _get_default_system_content(self, mode: str) -> str:
        """获取默认的系统消息内容"""
        defaults = {
            "translation": "将下列日语逐行翻译为中文，仅输出对应中文行；不要解释、不要添加标点以外的额外内容。严格按照行数输出，每行一个翻译结果。",
            "qc": "你是专业的翻译质量评估专家。请对给定的日语原文和中文译文进行质量评估，为每一行给出0-1之间的分数（1为完美翻译）。",
            "enhancement": "你是专业的中日互译编辑。给定若干原文与当前译文，请逐行改进质量，仅输出改进后的中文译文，不要任何解释。"
        }
        return defaults.get(mode, "请处理以下内容。")
