"""
翻译输出解析器

负责解析模型输出的翻译结果，支持多种格式：
1. 带行号的格式：6. 翻译内容
2. 顺序映射格式：纯翻译内容按顺序排列
3. 混合格式：部分带行号，部分不带
"""

import re
from typing import List, Dict, Tuple, Optional
import logging


class TranslationOutputParser:
    """翻译输出解析器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def parse_translation_output(
        self, 
        output_lines: List[str], 
        expected_count: int, 
        start_line_number: int = 1
    ) -> Dict[int, str]:
        """
        解析翻译输出
        
        Args:
            output_lines: 模型输出的行列表
            expected_count: 期望的翻译行数
            start_line_number: 当前批次在当前多轮对话中的起始行号
            
        Returns:
            Dict[int, str]: 行号到翻译内容的映射（键为多轮对话中的行号）
        """
        self.logger.debug(f"开始解析翻译输出: {len(output_lines)}行，期望{expected_count}行，起始行号{start_line_number}")
        
        line_number_to_translation = {}
        
        # 策略1: 尝试解析带行号的格式（模型输出多轮对话中的行号）
        numbered_result = self._parse_numbered_format(output_lines)
        
        if numbered_result:
            # 优先使用行号解析策略
            line_number_to_translation = {}
            expected_range = range(start_line_number, start_line_number + expected_count)
            
            for model_line_num, translation in numbered_result.items():
                if model_line_num in expected_range:
                    line_number_to_translation[model_line_num] = translation
                    self.logger.debug(f"行号解析: 多轮对话行号{model_line_num} -> {translation}")
                else:
                    self.logger.warning(f"行号{model_line_num}超出期望范围[{start_line_number}-{start_line_number + expected_count - 1}]")
        else:
            # 没有行号时，使用顺序映射策略
            self.logger.debug("没有检测到行号，使用顺序映射策略")
            line_number_to_translation = self._parse_sequential_mapping(
                output_lines, start_line_number, expected_count
            )
        
        self.logger.debug(f"解析结果: {len(line_number_to_translation)}个有效翻译")
        return line_number_to_translation
    
    def _parse_sequential_mapping(
        self, 
        output_lines: List[str], 
        start_line_number: int,
        expected_count: int = None
    ) -> Dict[int, str]:
        """顺序映射策略：按顺序将输出行映射到行号"""
        line_number_to_translation = {}
        
        # 过滤空行和无效行，并去掉行号前缀
        valid_lines = []
        for line in output_lines:
            line = line.strip()
            if line and not line.startswith('[翻译完成]'):
                # 去掉行号前缀（如 "4. "）
                if line and line[0].isdigit():
                    parts = line.split('.', 1)
                    if len(parts) >= 2:
                        line = parts[1].strip()
                valid_lines.append(line)
        
        # 如果指定了期望行数，只映射期望的行数
        if expected_count is not None:
            valid_lines = valid_lines[:expected_count]
        
        self.logger.debug(f"顺序映射: 有效行数={len(valid_lines)}, 起始行号={start_line_number}")
        
        for idx, line in enumerate(valid_lines):
            relative_line_number = start_line_number + idx
            line_number_to_translation[relative_line_number] = line
            self.logger.debug(f"顺序映射: 行号{relative_line_number} -> {line}")
        
        return line_number_to_translation
    
    def _parse_numbered_format(self, output_lines: List[str]) -> Dict[int, str]:
        """行号格式解析策略：解析 '6. 翻译内容' 格式"""
        line_number_to_translation = {}
        
        for line in output_lines:
            line = line.strip()
            if not line:
                continue
                
            # 解析行号，格式如 "6. 翻译内容" 或 "6.「翻译内容」"
            if line and line[0].isdigit():
                parts = line.split('.', 1)
                if len(parts) >= 2:
                    try:
                        line_num = int(parts[0])
                        translation = parts[1].strip()
                        line_number_to_translation[line_num] = translation
                        self.logger.debug(f"解析成功: 行号{line_num} -> {translation}")
                    except ValueError:
                        self.logger.warning(f"无法解析行号: {line}")
                else:
                    self.logger.debug(f"行号格式不正确: {line}")
            else:
                self.logger.debug(f"跳过非数字开头行: {line}")
        
        return line_number_to_translation
    
    def map_to_batch_indices(
        self,
        line_number_to_translation: Dict[int, str],
        batch_lines: List[Tuple[str, str]],
        start_line_number: int
    ) -> List[str]:
        """
        将解析结果映射到批次索引
        
        Args:
            line_number_to_translation: 行号到翻译的映射（键为多轮对话中的行号）
            batch_lines: 批次行数据 (原文, 现译)
            start_line_number: 当前批次在当前多轮对话中的起始行号
            
        Returns:
            List[str]: 按批次顺序排列的翻译结果
        """
        enhanced_translations = []
        
        for idx, (original, translated) in enumerate(batch_lines):
            # 计算当前行在多轮对话中的行号
            conversation_line_number = start_line_number + idx
            if conversation_line_number in line_number_to_translation:
                enhanced_translations.append(line_number_to_translation[conversation_line_number])
            else:
                warning_msg = f"未找到多轮对话行号 {conversation_line_number} 的翻译，保持原译文"
                self.logger.warning(warning_msg)
                enhanced_translations.append(translated)
        
        return enhanced_translations
    
    def extract_clean_translation(self, result: str, preserve_line_numbers: bool = False) -> str:
        """
        从模型输出中提取纯净的翻译结果
        
        Args:
            result: 模型原始输出
            
        Returns:
            str: 纯净的翻译结果
        """
        # 去除首尾空白
        result = result.strip()
        
        # 如果结果为空，返回原结果
        if not result:
            return result
        
        # 去除<think>标签及其内容（处理没有闭合标签的情况）
        result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
        result = re.sub(r'<think>.*', '', result, flags=re.DOTALL)
        
        # 去除其他常见的思考标记
        result = re.sub(r'<thinking>.*?</thinking>', '', result, flags=re.DOTALL)
        result = re.sub(r'<reasoning>.*?</reasoning>', '', result, flags=re.DOTALL)
        
        # 去除首尾空白
        result = result.strip()
        
        # 如果清理后结果为空，返回空字符串
        if not result:
            return ""
        
        # 按行分割，处理带编号的多行输出
        lines = result.split('\n')
        clean_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 移除行号（如 "1. 译文内容" -> "译文内容"）
            if not preserve_line_numbers and re.match(r'^\d+\.\s*', line):
                line = re.sub(r'^\d+\.\s*', '', line)
            
            # 处理增强模式的箭头格式（如 "→ 译文内容" -> "译文内容"）
            if line.startswith('→'):
                line = line[1:].strip()
            
            # 跳过[翻译完成]标记
            if line == "[翻译完成]":
                continue
            
            # 跳过其他标记
            if line in ["[END]", "（未完待续）"]:
                continue
            
            # 跳过明显的思考内容（但保留翻译内容）
            # 更宽松的过滤条件：只跳过明显的思考开头，但保留翻译内容
            if (line.startswith('好的，我现在需要处理') or
                line.startswith('用户特别强调') or
                line.startswith('让我') or
                line.startswith('首先看') or
                line.startswith('需要') or
                line.startswith('确认') or
                line.startswith('接下来检查') or
                line.startswith('然后') or
                line.startswith('另外') or
                line.startswith('最后，确保') or
                line.startswith('检查所有规则') or
                line.startswith('确保没有添加') or
                line.startswith('可能') or
                line.startswith('应该') or
                line.startswith('不过现译已经') or
                line.startswith('但是') or
                line.startswith('因为') or
                line.startswith('如果') or
                line.startswith('虽然') or
                line.startswith('根据') or
                line.startswith('考虑') or
                line.startswith('注意') or
                line.startswith('所有改进点都已处理')):
                continue
            
            # 如果这行看起来像翻译结果，添加到结果中
            if len(line) > 0:
                clean_lines.append(line)
        
        return '\n'.join(clean_lines)
